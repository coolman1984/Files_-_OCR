from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageAsset:
    sheet: str
    source_row: int
    source_column: int
    anchor_cell: str
    sha256: str
    path: Path
    extension: str


@dataclass
class ParsedRow:
    source_row: int
    row_type: str
    values: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    image_hashes: list[str] = field(default_factory=list)


@dataclass
class Reconciliation:
    sheet: str
    source_row: int
    column: str
    written_value: float | None
    calculated_value: float | None
    difference: float | None
    status: str
    scope: str


@dataclass
class ParsedSheet:
    name: str
    header_row: int
    headers: list[str]
    rows: list[ParsedRow]
    images: list[ImageAsset]
    reconciliations: list[Reconciliation]


@dataclass
class ImportResult:
    import_id: int
    file_name: str
    sha256: str
    status: str
    sheets: list[ParsedSheet]

