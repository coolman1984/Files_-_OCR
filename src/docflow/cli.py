from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .pipeline import IngestionPipeline
from .report import export_clean_report
from .web import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="docflow", description="Auditable factory document pipeline")
    parser.add_argument("--root", default=".", help="Runtime data root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    ingest = commands.add_parser("import-file"); ingest.add_argument("path")
    export = commands.add_parser("export"); export.add_argument("import_id", type=int); export.add_argument("--output")
    web = commands.add_parser("serve"); web.add_argument("--host", default="127.0.0.1"); web.add_argument("--port", type=int, default=8765)
    commands.add_parser("list")
    args = parser.parse_args()
    settings = Settings.from_root(args.root)
    pipeline = IngestionPipeline(settings)
    if args.command == "init": print(f"Initialized: {settings.db_path}")
    elif args.command == "import-file":
        result = pipeline.ingest(args.path); print(f"Import #{result.import_id}: {result.status} ({len(result.sheets)} sheets)")
    elif args.command == "export":
        target = Path(args.output) if args.output else settings.exports_dir / f"clean_report_{args.import_id}.xlsx"
        print(export_clean_report(pipeline.store, args.import_id, target))
    elif args.command == "list":
        for item in pipeline.store.list_imports(): print(f"#{item['id']} {item['status']}: {item['file_name']}")
    elif args.command == "serve": serve(settings, args.host, args.port)


if __name__ == "__main__": main()

