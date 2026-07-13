from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .config import Settings
from .excel_reader import parse_workbook
from .models import ImportResult
from .store import Store


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

    def ingest(self, source: str | Path, display_name: str | None = None) -> ImportResult:
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
            sheets = parse_workbook(original_path, self.settings.images_dir)
            failures = sum(r.status == "fail" for s in sheets for r in s.reconciliations)
            uncertain = sum(r.row_type == "uncertain" for s in sheets for r in s.rows)
            status = "needs_review" if failures or uncertain else "verified"
            self.store.finish_import(import_id, sheets, status)
            return ImportResult(import_id, file_name, digest, status, sheets)
        except Exception as exc:
            self.store.fail_import(import_id, str(exc))
            raise
