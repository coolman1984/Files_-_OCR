# Files & OCR

## Document Flow — Excel Vertical Slice

An offline-first, working vertical slice for factory Excel ingestion:

1. Upload an `.xlsx` or `.xlsm` workbook.
2. Detect headers and classify data, total, subtotal, section, empty, and uncertain rows.
3. Extract embedded images and link them to their source row/cell.
4. Store auditable records in SQLite.
5. Reconcile calculated numeric totals against totals written in the workbook.
6. Review the run in a local web UI and export a clean Excel report.

The core pipeline does not depend on the web UI or an AI model. Future OCR, PDF,
email, DuckDB, and MCP adapters can be added without changing its contracts.

## Quick start

```bash
python3 scripts/create_sample.py
PYTHONPATH=src python3 -m docflow.cli import-file samples/factory_defects.xlsx
PYTHONPATH=src python3 -m docflow.cli serve --port 8765
```

Open `http://127.0.0.1:8765`.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Data safety

- Original workbooks are copied unchanged into `data/originals/` using a SHA-256 name.
- Extracted images are fingerprinted and deduplicated under `data/images/`.
- Every stored row retains workbook, sheet, and source-row lineage.
- Total and subtotal rows are never included as data records.
- A reconciliation failure is visible and prevents a run from being marked verified.
