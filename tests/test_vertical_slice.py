from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from docflow.config import Settings
from docflow.pipeline import IngestionPipeline
from docflow.report import export_clean_report


class VerticalSliceTests(unittest.TestCase):
    def make_workbook(self, path: Path, wrong_total: bool = False) -> None:
        wb = Workbook(); ws = wb.active; ws.title = "Data"
        ws.append(["ID", "Quantity", "Cost"])
        ws.append(["A", 2, 10]); ws.append(["B", 3, 15])
        ws.append(["Subtotal", 5, 25 if not wrong_total else 999])
        ws.append(["C", 1, 7]); ws.append(["Grand Total", 6, 32])
        wb.save(path)

    def test_totals_are_excluded_and_reconciled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "input.xlsx"; self.make_workbook(source)
            pipeline = IngestionPipeline(Settings.from_root(root)); result = pipeline.ingest(source)
            self.assertEqual(result.status, "verified")
            rows = result.sheets[0].rows
            self.assertEqual(sum(r.row_type == "data" for r in rows), 3)
            self.assertEqual(sum(r.row_type in ("total", "subtotal") for r in rows), 2)
            self.assertTrue(result.sheets[0].reconciliations)
            self.assertTrue(all(r.status == "pass" for r in result.sheets[0].reconciliations))

    def test_failed_reconciliation_requires_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "wrong.xlsx"; self.make_workbook(source, True)
            result = IngestionPipeline(Settings.from_root(root)).ingest(source)
            self.assertEqual(result.status, "needs_review")
            self.assertTrue(any(r.status == "fail" for r in result.sheets[0].reconciliations))

    def test_export_contains_only_clean_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "input.xlsx"; self.make_workbook(source)
            pipeline = IngestionPipeline(Settings.from_root(root)); result = pipeline.ingest(source)
            target = export_clean_report(pipeline.store, result.import_id, root / "report.xlsx")
            self.assertTrue(target.exists()); self.assertGreater(target.stat().st_size, 1000)


if __name__ == "__main__": unittest.main()
