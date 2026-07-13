# Incremental roadmap

Each item is a releasable vertical slice, not a partially connected component.

## 0.1 — Excel proof path (current)

- XLSX/XLSM upload and immutable source retention
- header detection and row classification
- total/subtotal exclusion and reconciliation
- embedded image extraction, deduplication, lineage, and report preview
- SQLite audit store, local web review, clean Excel export

Operational envelope: moderate-size workbooks on Python 3.10–3.12. Very large
worksheets are deliberately the next slice because they require streaming XML
ingestion and batched database writes rather than pretending an in-memory reader
is safe at factory scale.

## 0.2 — Large Excel vertical slice

- streaming worksheet XML reader for 500k+ rows and wide tables
- batched writes and bounded memory
- drawing/media extraction directly from the XLSX package
- progress, cancellation, resumable imports, and performance acceptance tests

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

