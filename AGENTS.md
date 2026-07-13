# Agent Guide — Document Flow

## Product invariant

Every release must remain a complete working path from input to verified output.
Do not merge a feature that breaks existing ingestion, lineage, reconciliation,
review, or export behavior.

## Current vertical slice

`Excel workbook -> row classification -> image extraction -> SQLite -> reconciliation -> web review -> clean Excel export`

## Architecture boundaries

- `excel_reader.py`: source adapter; no database or web concerns.
- `classifier.py`: deterministic row classification; no file I/O.
- `store.py`: persistence and query boundary.
- `pipeline.py`: orchestration and status gate.
- `report.py`: output adapter.
- `web.py` and `cli.py`: user/agent entry points only.

Future OCR, PDF, email, DuckDB, and MCP work must be added as adapters. Do not
place vendor-specific logic in the pipeline or UI.

## Non-negotiable data rules

1. Never modify the source workbook.
2. Preserve file, sheet, row, cell/anchor, and image fingerprints.
3. Never include total/subtotal rows as facts.
4. Treat uncertain rows and reconciliation failures as `needs_review`.
5. Do not let a corrupt image destroy otherwise valid tabular extraction.
6. All schema changes require forward migrations before production deployment.
7. New behavior requires a regression test plus a realistic fixture.

## Commands

```bash
python3 scripts/create_sample.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m docflow import-file samples/factory_defects.xlsx
PYTHONPATH=src python3 -m docflow serve --port 8765
```

## Definition of done for a new vertical slice

- A real input reaches a useful downloadable output.
- Errors are visible and do not silently change facts.
- Source lineage is queryable.
- Previous tests still pass.
- The sample fixture and README demonstrate the result offline.

