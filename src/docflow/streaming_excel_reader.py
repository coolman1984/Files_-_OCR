from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .classifier import classify_row
from .models import ImageAsset, ParsedRow, StreamedSheet


REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _relationship_id(element: ET.Element, name: str) -> str | None:
    return element.attrib.get(f"{{{REL_NS}}}{name}")


def _rels_path(part: str) -> str:
    directory, name = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{name}.rels")


def _resolve_target(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relationships(package: zipfile.ZipFile, source_part: str) -> dict[str, str]:
    path = _rels_path(source_part)
    try:
        root = ET.fromstring(package.read(path))
    except KeyError:
        return {}
    return {
        element.attrib["Id"]: _resolve_target(source_part, element.attrib["Target"])
        for element in root
        if "Id" in element.attrib and "Target" in element.attrib
    }


def _store_image(
    package: zipfile.ZipFile,
    media_part: str,
    images_dir: Path,
    sheet_name: str,
    row: int,
    column: int,
) -> ImageAsset:
    raw = package.read(media_part)
    digest = hashlib.sha256(raw).hexdigest()
    extension = Path(media_part).suffix.lower().lstrip(".") or "png"
    if extension == "jpeg":
        extension = "jpg"
    target = images_dir / f"{digest}.{extension}"
    if not target.exists():
        target.write_bytes(raw)
    return ImageAsset(
        sheet=sheet_name,
        source_row=row,
        source_column=column,
        anchor_cell=f"{get_column_letter(column)}{row}",
        sha256=digest,
        path=target,
        extension=extension,
    )


def extract_package_images(path: Path, images_dir: Path) -> dict[str, list[ImageAsset]]:
    """Extract drawing images without loading worksheet cells into memory."""
    images_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[ImageAsset]] = defaultdict(list)
    with zipfile.ZipFile(path) as package:
        workbook_part = "xl/workbook.xml"
        workbook = ET.fromstring(package.read(workbook_part))
        workbook_rels = _relationships(package, workbook_part)
        for sheet in (element for element in workbook.iter() if _local_name(element.tag) == "sheet"):
            sheet_name = sheet.attrib.get("name", "Sheet")
            relation_id = _relationship_id(sheet, "id")
            sheet_part = workbook_rels.get(relation_id or "")
            if not sheet_part:
                continue
            try:
                sheet_xml = ET.fromstring(package.read(sheet_part))
            except KeyError:
                continue
            sheet_rels = _relationships(package, sheet_part)
            drawing_ids = [
                _relationship_id(element, "id")
                for element in sheet_xml.iter()
                if _local_name(element.tag) == "drawing"
            ]
            for drawing_id in drawing_ids:
                drawing_part = sheet_rels.get(drawing_id or "")
                if not drawing_part:
                    continue
                try:
                    drawing = ET.fromstring(package.read(drawing_part))
                except KeyError:
                    continue
                drawing_rels = _relationships(package, drawing_part)
                for anchor in drawing:
                    if _local_name(anchor.tag) not in {"oneCellAnchor", "twoCellAnchor"}:
                        continue
                    origin = next((x for x in anchor if _local_name(x.tag) == "from"), None)
                    if origin is None:
                        continue
                    row_node = next((x for x in origin if _local_name(x.tag) == "row"), None)
                    col_node = next((x for x in origin if _local_name(x.tag) == "col"), None)
                    if row_node is None or col_node is None:
                        continue
                    blip = next((x for x in anchor.iter() if _local_name(x.tag) == "blip"), None)
                    embed_id = _relationship_id(blip, "embed") if blip is not None else None
                    media_part = drawing_rels.get(embed_id or "")
                    if not media_part:
                        continue
                    try:
                        result[sheet_name].append(_store_image(
                            package, media_part, images_dir, sheet_name,
                            int(row_node.text or "0") + 1,
                            int(col_node.text or "0") + 1,
                        ))
                    except (KeyError, ValueError, zipfile.BadZipFile):
                        # Broken drawings remain isolated from valid tabular data.
                        continue
    return dict(result)


def _header_score(values: tuple[Any, ...]) -> float:
    populated = [value for value in values if value not in (None, "")]
    if len(populated) < 2:
        return float("-inf")
    strings = sum(isinstance(value, str) for value in populated)
    unique = len({str(value).strip().lower() for value in populated})
    formulas = sum(isinstance(value, str) and value.startswith("=") for value in populated)
    return len(populated) * 2 + strings + unique * 0.25 - formulas * 3


def _safe_headers(values: tuple[Any, ...]) -> list[str]:
    last = max((index for index, value in enumerate(values, start=1) if value not in (None, "")), default=1)
    seen: dict[str, int] = defaultdict(int)
    headers: list[str] = []
    for column, value in enumerate(values[:last], start=1):
        base = re.sub(r"\s+", " ", str(value).strip()) if value not in (None, "") else f"column_{column}"
        seen[base] += 1
        headers.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return headers


def _sheet_metadata(path: Path, max_columns: int) -> list[tuple[str, int, list[str]]]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_vba=path.suffix.lower() == ".xlsm")
    output: list[tuple[str, int, list[str]]] = []
    try:
        for worksheet in workbook.worksheets:
            best_row, best_values, best_score = 1, tuple(), float("-inf")
            for row_number, values in enumerate(
                worksheet.iter_rows(min_row=1, max_row=40, max_col=max_columns, values_only=True),
                start=1,
            ):
                score = _header_score(values)
                if score > best_score:
                    best_row, best_values, best_score = row_number, values, score
            output.append((worksheet.title, best_row, _safe_headers(best_values)))
    finally:
        workbook.close()
    return output


def stream_workbook(path: Path, images_dir: Path, max_columns: int = 2_048) -> Iterator[StreamedSheet]:
    if not zipfile.is_zipfile(path):
        raise ValueError("The workbook is not a valid XLSX package")
    image_map = extract_package_images(path, images_dir)
    metadata = _sheet_metadata(path, max_columns)
    keep_vba = path.suffix.lower() == ".xlsm"
    formula_book = load_workbook(path, read_only=True, data_only=False, keep_vba=keep_vba)
    value_book = load_workbook(path, read_only=True, data_only=True, keep_vba=keep_vba)
    try:
        for sheet_name, header_row, headers in metadata:
            formula_sheet = formula_book[sheet_name]
            value_sheet = value_book[sheet_name]
            assets = image_map.get(sheet_name, [])
            images_by_row: dict[int, list[str]] = defaultdict(list)
            for asset in assets:
                images_by_row[asset.source_row].append(asset.sha256)

            def rows(
                formula_sheet=formula_sheet,
                value_sheet=value_sheet,
                header_row=header_row,
                headers=headers,
                images_by_row=images_by_row,
            ) -> Iterator[ParsedRow]:
                formulas = formula_sheet.iter_rows(
                    min_row=header_row + 1, max_col=len(headers), values_only=True
                )
                cached = value_sheet.iter_rows(
                    min_row=header_row + 1, max_col=len(headers), values_only=True
                )
                empty = (None,) * len(headers)
                for source_row, pair in enumerate(zip_longest(formulas, cached, fillvalue=empty), start=header_row + 1):
                    formula_values, cached_values = pair
                    effective = [
                        cached_values[index] if cached_values[index] is not None else formula_values[index]
                        for index in range(len(headers))
                    ]
                    classification = classify_row(effective, list(formula_values), merged=False)
                    if classification.row_type == "empty":
                        continue
                    yield ParsedRow(
                        source_row=source_row,
                        row_type=classification.row_type,
                        values=dict(zip(headers, effective)),
                        reasons=classification.reasons,
                        image_hashes=images_by_row.get(source_row, []),
                    )

            yield StreamedSheet(sheet_name, header_row, headers, rows(), assets)
    finally:
        formula_book.close()
        value_book.close()
