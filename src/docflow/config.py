from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    originals_dir: Path
    images_dir: Path
    exports_dir: Path
    db_path: Path
    max_upload_bytes: int = 250 * 1024 * 1024

    @classmethod
    def from_root(cls, root: str | Path | None = None) -> "Settings":
        base = Path(root or ".").resolve()
        data = base / "data"
        return cls(
            root=base,
            data_dir=data,
            originals_dir=data / "originals",
            images_dir=data / "images",
            exports_dir=base / "exports",
            db_path=data / "docflow.sqlite3",
        )

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.originals_dir, self.images_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)

