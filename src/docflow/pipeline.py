from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .config import Settings
from .excel_reader import parse_workbook
from .models import ImportResult, ParsedSheet, Reconciliation
from .store import Store
from .streaming_excel_reader import stream_workbook


ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class IngestionPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_dirs()
        self.store = Store(settings.db_path)
        self.store.init()

    def ingest(
        self,
        source: str | Path,
        display_name: str | None = None,
        *,
        streaming: bool | None = None,
    ) -> ImportResult:
        source_path = Path(source)
        if source_path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError("Only .xlsx and .xlsm files are supported in this release")
        size = source_path.stat().st_size
        if size > self.settings.max_upload_bytes:
            raise ValueError("Workbook exceeds the configured upload limit")
        digest = _sha256(source_path)
        original_path = self.settings.originals_dir / f"{digest}{source_path.suffix.lower()}"
        if not original_path.exists():
            shutil.copy2(source_path, original_path)
        file_name = display_name or source_path.name
        import_id = self.store.begin_import(file_name, digest, original_path)
        try:
            use_streaming = size >= self.settings.streaming_threshold_bytes if streaming is None else streaming
            if use_streaming:
                return self._ingest_streaming(import_id, file_name, digest, original_path)
            sheets = parse_workbook(original_path, self.settings.images_dir)
            failures = sum(r.status == "fail" for s in sheets for r in s.reconciliations)
            uncertain = sum(r.row_type == "uncertain" for s in sheets for r in s.rows)
            status = "needs_review" if failures or uncertain else "verified"
            self.store.finish_import(import_id, sheets, status)
            return ImportResult(import_id, file_name, digest, status, sheets)
        except Exception as exc:
            self.store.fail_import(import_id, str(exc))
            raise

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", "").strip())
            except ValueError:
                return None
        return None

    def _ingest_streaming(
        self,
        import_id: int,
        file_name: str,
        digest: str,
        original_path: Path,
    ) -> ImportResult:
        parsed_sheets: list[ParsedSheet] = []
        failure_count = 0
        uncertain_count = 0
        for sheet in stream_workbook(original_path, self.settings.images_dir, self.settings.max_columns):
            sheet_id = self.store.create_sheet(import_id, sheet.name, sheet.header_row, sheet.headers)
            self.store.insert_images(sheet_id, sheet.images)
            all_sums: dict[str, float] = {}
            all_counts: dict[str, int] = {}
            section_sums: dict[str, float] = {}
            section_counts: dict[str, int] = {}
            batch = []
            preview = []
            reconciliations: list[Reconciliation] = []
            for row in sheet.rows:
                if len(preview) < self.settings.streaming_preview_rows:
                    preview.append(row)
                if row.row_type == "uncertain":
                    uncertain_count += 1
                elif row.row_type == "section":
                    section_sums.clear(); section_counts.clear()
                elif row.row_type == "data":
                    for header in sheet.headers:
                        value = self._number(row.values.get(header))
                        if value is None:
                            continue
                        all_sums[header] = all_sums.get(header, 0.0) + value
                        all_counts[header] = all_counts.get(header, 0) + 1
                        section_sums[header] = section_sums.get(header, 0.0) + value
                        section_counts[header] = section_counts.get(header, 0) + 1
                elif row.row_type in {"total", "subtotal"}:
                    is_grand = "grand_total_label" in row.reasons
                    scope = "all_preceding_data" if is_grand else "current_section"
                    sums = all_sums if is_grand else section_sums
                    counts = all_counts if is_grand else section_counts
                    for header in sheet.headers:
                        written = self._number(row.values.get(header))
                        if written is None or counts.get(header, 0) == 0:
                            continue
                        calculated = round(sums.get(header, 0.0), 8)
                        difference = round(written - calculated, 8)
                        tolerance = max(0.01, abs(written) * 0.000001)
                        status = "pass" if abs(difference) <= tolerance else "fail"
                        failure_count += status == "fail"
                        reconciliations.append(Reconciliation(
                            sheet.name, row.source_row, header, written,
                            calculated, difference, status, scope,
                        ))
                    if not is_grand:
                        section_sums.clear(); section_counts.clear()
                batch.append(row)
                if len(batch) >= self.settings.streaming_batch_rows:
                    self.store.insert_records(sheet_id, batch)
                    batch.clear()
            self.store.insert_records(sheet_id, batch)
            self.store.insert_reconciliations(sheet_id, reconciliations)
            parsed_sheets.append(ParsedSheet(
                sheet.name, sheet.header_row, sheet.headers, preview,
                sheet.images, reconciliations,
            ))
        status = "needs_review" if failure_count or uncertain_count else "verified"
        self.store.complete_import(import_id, status)
        return ImportResult(import_id, file_name, digest, status, parsed_sheets)
