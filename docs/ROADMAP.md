# Incremental roadmap

Each item is a releasable vertical slice, not a partially connected component.

## 0.1 — Excel proof path (complete)

- XLSX/XLSM upload and immutable source retention
- header detection and row classification
- total/subtotal exclusion and reconciliation
- embedded image extraction, deduplication, lineage, and report preview
- SQLite audit store, local web review, clean Excel export

This original path remains available for small workbooks and regression coverage.

## 0.2 — Large Excel vertical slice (current)

- bounded-memory worksheet reader for 500k+ rows and wide tables
- configurable batched database writes
- drawing/media extraction directly from the XLSX package
- bounded-memory review and clean-report export
- automatic activation for workbooks of 8 MB or larger, plus a force flag

Job progress, cancellation, and resumable imports are the next operational slice.

## 0.3 — Mapping and drift vertical slice

- saved column mappings, type contracts, and mapping versions
- confidence/review screen and schema drift alerts
- deterministic reuse; external agent only when a new layout is unknown

## 0.4 — Document/OCR vertical slice

- PDF/image ingestion adapter
- selectable Docling/PaddleOCR engines
- English/Korean evaluation set, page/cell lineage, and confidence gates

## 0.5 — Mail and approval vertical slice

- EML body, header, attachment, and approval-page capture
- thread/document linkage and searchable evidence

## 0.6 — Agent control vertical slice

- stable tool contracts, MCP server, task manifests, dry-run, and approval gates
- the platform stays usable without an AI model
