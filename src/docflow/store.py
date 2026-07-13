from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ImageAsset, ParsedRow, ParsedSheet, Reconciliation


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY, file_name TEXT NOT NULL, sha256 TEXT NOT NULL,
  original_path TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
  error TEXT
);
CREATE TABLE IF NOT EXISTS sheets (
  id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
  name TEXT NOT NULL, header_row INTEGER NOT NULL, headers_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY, sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
  source_row INTEGER NOT NULL, row_type TEXT NOT NULL, values_json TEXT NOT NULL,
  reasons_json TEXT NOT NULL, image_hashes_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
  id INTEGER PRIMARY KEY, sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
  source_row INTEGER NOT NULL, source_column INTEGER NOT NULL, anchor_cell TEXT NOT NULL,
  sha256 TEXT NOT NULL, path TEXT NOT NULL, extension TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reconciliations (
  id INTEGER PRIMARY KEY, sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,
  source_row INTEGER NOT NULL, column_name TEXT NOT NULL,
  written_value REAL, calculated_value REAL, difference REAL,
  status TEXT NOT NULL, scope TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_sheet_type ON records(sheet_id, row_type);
CREATE INDEX IF NOT EXISTS idx_images_hash ON images(sha256);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        return con

    def init(self) -> None:
        with self.connect() as con:
            con.executescript(SCHEMA)

    def begin_import(self, file_name: str, sha256: str, original_path: Path) -> int:
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO imports(file_name,sha256,original_path,status,created_at) VALUES(?,?,?,?,?)",
                (file_name, sha256, str(original_path), "processing", datetime.now(timezone.utc).isoformat()),
            )
            return int(cur.lastrowid)

    def finish_import(self, import_id: int, sheets: list[ParsedSheet], status: str) -> None:
        with self.connect() as con:
            for sheet in sheets:
                cur = con.execute(
                    "INSERT INTO sheets(import_id,name,header_row,headers_json) VALUES(?,?,?,?)",
                    (import_id, sheet.name, sheet.header_row, json.dumps(sheet.headers, ensure_ascii=False)),
                )
                sheet_id = int(cur.lastrowid)
                con.executemany(
                    "INSERT INTO records(sheet_id,source_row,row_type,values_json,reasons_json,image_hashes_json) VALUES(?,?,?,?,?,?)",
                    [
                        (sheet_id, r.source_row, r.row_type,
                         json.dumps(r.values, ensure_ascii=False, default=str),
                         json.dumps(r.reasons, ensure_ascii=False),
                         json.dumps(r.image_hashes))
                        for r in sheet.rows
                    ],
                )
                con.executemany(
                    "INSERT INTO images(sheet_id,source_row,source_column,anchor_cell,sha256,path,extension) VALUES(?,?,?,?,?,?,?)",
                    [(sheet_id, i.source_row, i.source_column, i.anchor_cell, i.sha256, str(i.path), i.extension) for i in sheet.images],
                )
                con.executemany(
                    "INSERT INTO reconciliations(sheet_id,source_row,column_name,written_value,calculated_value,difference,status,scope) VALUES(?,?,?,?,?,?,?,?)",
                    [(sheet_id, r.source_row, r.column, r.written_value, r.calculated_value, r.difference, r.status, r.scope) for r in sheet.reconciliations],
                )
            con.execute("UPDATE imports SET status=? WHERE id=?", (status, import_id))

    def create_sheet(self, import_id: int, name: str, header_row: int, headers: list[str]) -> int:
        with self.connect() as con:
            cursor = con.execute(
                "INSERT INTO sheets(import_id,name,header_row,headers_json) VALUES(?,?,?,?)",
                (import_id, name, header_row, json.dumps(headers, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def insert_records(self, sheet_id: int, records: list[ParsedRow]) -> None:
        if not records:
            return
        with self.connect() as con:
            con.executemany(
                "INSERT INTO records(sheet_id,source_row,row_type,values_json,reasons_json,image_hashes_json) VALUES(?,?,?,?,?,?)",
                [
                    (
                        sheet_id, row.source_row, row.row_type,
                        json.dumps(row.values, ensure_ascii=False, default=str),
                        json.dumps(row.reasons, ensure_ascii=False),
                        json.dumps(row.image_hashes),
                    )
                    for row in records
                ],
            )

    def insert_images(self, sheet_id: int, images: list[ImageAsset]) -> None:
        if not images:
            return
        with self.connect() as con:
            con.executemany(
                "INSERT INTO images(sheet_id,source_row,source_column,anchor_cell,sha256,path,extension) VALUES(?,?,?,?,?,?,?)",
                [(sheet_id, i.source_row, i.source_column, i.anchor_cell, i.sha256, str(i.path), i.extension) for i in images],
            )

    def insert_reconciliations(self, sheet_id: int, records: list[Reconciliation]) -> None:
        if not records:
            return
        with self.connect() as con:
            con.executemany(
                "INSERT INTO reconciliations(sheet_id,source_row,column_name,written_value,calculated_value,difference,status,scope) VALUES(?,?,?,?,?,?,?,?)",
                [(sheet_id, r.source_row, r.column, r.written_value, r.calculated_value, r.difference, r.status, r.scope) for r in records],
            )

    def complete_import(self, import_id: int, status: str) -> None:
        with self.connect() as con:
            con.execute("UPDATE imports SET status=? WHERE id=?", (status, import_id))

    def fail_import(self, import_id: int, error: str) -> None:
        with self.connect() as con:
            con.execute("UPDATE imports SET status='failed', error=? WHERE id=?", (error[:2000], import_id))

    def list_imports(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("""
                SELECT i.*,
                  (SELECT COUNT(*) FROM sheets s WHERE s.import_id=i.id) sheet_count,
                  (SELECT COUNT(*) FROM records r JOIN sheets s ON s.id=r.sheet_id
                    WHERE s.import_id=i.id AND r.row_type='data') data_rows,
                  (SELECT COUNT(*) FROM records r JOIN sheets s ON s.id=r.sheet_id
                    WHERE s.import_id=i.id AND r.row_type IN ('total','subtotal')) total_rows,
                  (SELECT COUNT(*) FROM images im JOIN sheets s ON s.id=im.sheet_id
                    WHERE s.import_id=i.id) image_count
                FROM imports i ORDER BY i.id DESC
            """).fetchall()
            return [dict(row) for row in rows]

    def get_import(self, import_id: int, *, include_records: bool = True) -> dict[str, Any] | None:
        with self.connect() as con:
            imp = con.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
            if not imp:
                return None
            result: dict[str, Any] = dict(imp)
            result["sheets"] = []
            for s in con.execute("SELECT * FROM sheets WHERE import_id=? ORDER BY id", (import_id,)):
                sheet = dict(s)
                sheet["headers"] = json.loads(sheet.pop("headers_json"))
                if include_records:
                    sheet["records"] = []
                    for r in con.execute("SELECT * FROM records WHERE sheet_id=? ORDER BY source_row", (s["id"],)):
                        sheet["records"].append(self._decode_record(r))
                sheet["images"] = [dict(x) for x in con.execute("SELECT * FROM images WHERE sheet_id=?", (s["id"],))]
                sheet["reconciliations"] = [dict(x) for x in con.execute("SELECT * FROM reconciliations WHERE sheet_id=?", (s["id"],))]
                result["sheets"].append(sheet)
            return result

    @staticmethod
    def _decode_record(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["values"] = json.loads(item.pop("values_json"))
        item["reasons"] = json.loads(item.pop("reasons_json"))
        item["image_hashes"] = json.loads(item.pop("image_hashes_json"))
        return item

    def iter_records(self, sheet_id: int, row_type: str | None = None):
        con = self.connect()
        try:
            if row_type:
                cursor = con.execute(
                    "SELECT * FROM records WHERE sheet_id=? AND row_type=? ORDER BY source_row",
                    (sheet_id, row_type),
                )
            else:
                cursor = con.execute("SELECT * FROM records WHERE sheet_id=? ORDER BY source_row", (sheet_id,))
            for row in cursor:
                yield self._decode_record(row)
        finally:
            con.close()

    def import_counts(self, import_id: int) -> dict[str, int]:
        with self.connect() as con:
            row = con.execute("""
                SELECT
                  SUM(CASE WHEN r.row_type='data' THEN 1 ELSE 0 END) data_rows,
                  SUM(CASE WHEN r.row_type IN ('total','subtotal') THEN 1 ELSE 0 END) total_rows,
                  SUM(CASE WHEN r.row_type='uncertain' THEN 1 ELSE 0 END) uncertain_rows,
                  (SELECT COUNT(*) FROM images im JOIN sheets si ON si.id=im.sheet_id WHERE si.import_id=?) image_count,
                  (SELECT COUNT(*) FROM reconciliations rc JOIN sheets sr ON sr.id=rc.sheet_id WHERE sr.import_id=? AND rc.status='fail') failed_checks
                FROM records r JOIN sheets s ON s.id=r.sheet_id WHERE s.import_id=?
            """, (import_id, import_id, import_id)).fetchone()
            return {key: int(row[key] or 0) for key in row.keys()}
