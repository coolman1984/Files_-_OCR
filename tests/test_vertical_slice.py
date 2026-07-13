from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from PIL import Image as PillowImage

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

    def test_streaming_path_batches_large_data_and_extracts_images(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "large.xlsx"; photo = root / "photo.png"
            PillowImage.new("RGB", (24, 24), "red").save(photo)
            workbook = Workbook(write_only=False); sheet = workbook.active; sheet.title = "Large Data"
            sheet.append(["ID", "Quantity", "Cost", "Photo"])
            expected_quantity = 0
            expected_cost = 0
            row_count = 6_000
            for index in range(1, row_count + 1):
                quantity = index % 7 + 1; cost = index % 13 + 0.5
                expected_quantity += quantity; expected_cost += cost
                sheet.append([f"R-{index}", quantity, cost, "defect" if index == 25 else None])
            image_bytes = BytesIO(photo.read_bytes())
            image = Image(image_bytes); image.width = 24; image.height = 24; sheet.add_image(image, "D26")
            sheet.append(["Grand Total", expected_quantity, expected_cost, None])
            workbook.save(source)
            settings = Settings.from_root(root)
            settings = replace(settings, streaming_batch_rows=257, streaming_preview_rows=10)
            pipeline = IngestionPipeline(settings)
            result = pipeline.ingest(source, streaming=True)
            self.assertEqual(result.status, "verified")
            self.assertLessEqual(len(result.sheets[0].rows), 10)
            counts = pipeline.store.import_counts(result.import_id)
            self.assertEqual(counts["data_rows"], row_count)
            self.assertEqual(counts["total_rows"], 1)
            self.assertEqual(counts["image_count"], 1)
            self.assertEqual(counts["failed_checks"], 0)
            stored = pipeline.store.get_import(result.import_id, include_records=False)
            self.assertEqual(stored["sheets"][0]["images"][0]["anchor_cell"], "D26")
            target = export_clean_report(pipeline.store, result.import_id, root / "large_report.xlsx")
            self.assertTrue(target.exists())

    def test_streaming_reconciliation_failure_requires_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "wrong-stream.xlsx"; self.make_workbook(source, True)
            pipeline = IngestionPipeline(Settings.from_root(root))
            result = pipeline.ingest(source, streaming=True)
            self.assertEqual(result.status, "needs_review")
            self.assertEqual(pipeline.store.import_counts(result.import_id)["failed_checks"], 1)


if __name__ == "__main__": unittest.main()
