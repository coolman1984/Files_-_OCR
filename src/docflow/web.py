from __future__ import annotations

import cgi
import html
import re
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings
from .pipeline import IngestionPipeline
from .report import export_clean_report


CSS = """
:root{--navy:#0b1739;--blue:#2859d6;--ice:#f4f7fc;--ink:#18213b;--green:#16815a;--amber:#b85a00;--red:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--ice);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{background:linear-gradient(120deg,var(--navy),#183d8f);color:white;padding:30px max(5vw,24px)}
header h1{margin:0;font-size:28px}header p{opacity:.8;margin:6px 0 0}.wrap{max-width:1180px;margin:28px auto;padding:0 22px}
.card{background:white;border:1px solid #dde5f3;border-radius:16px;padding:22px;margin-bottom:20px;box-shadow:0 8px 28px #1b3d7210}
.upload{display:flex;gap:12px;align-items:center;flex-wrap:wrap}input[type=file]{padding:12px;background:#f7f9fd;border:1px dashed #94a7ca;border-radius:10px}
button,.button{background:var(--blue);color:white;border:0;border-radius:9px;padding:11px 18px;font-weight:700;text-decoration:none;cursor:pointer}
table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid #e7ecf5;text-align:left}th{color:#52627e;font-size:12px;text-transform:uppercase}
.pill{display:inline-block;border-radius:99px;padding:4px 9px;font-size:12px;font-weight:700}.verified,.pass{background:#e7f7ef;color:var(--green)}.needs_review{background:#fff0df;color:var(--amber)}.failed,.fail{background:#feeceb;color:var(--red)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}.metric{background:#f7f9fd;border-radius:12px;padding:15px}.metric b{display:block;font-size:24px;color:var(--navy)}
.muted{color:#6d7890}.error{background:#feeceb;color:#8d1912;padding:12px;border-radius:10px}.scroll{overflow:auto}
"""


def page(body: str, title: str = "Document Flow") -> bytes:
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{html.escape(title)}</title><style>{CSS}</style></head><body><header><h1>Document Flow</h1><p>Auditable Excel extraction, image lineage, and reconciliation</p></header><main class='wrap'>{body}</main></body></html>".encode()


class AppHandler(BaseHTTPRequestHandler):
    pipeline: IngestionPipeline

    def send_html(self, body: str, status: int = 200) -> None:
        payload = page(body)
        self.send_response(status); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            imports = self.pipeline.store.list_imports()
            rows = "".join(f"<tr><td><a href='/imports/{r['id']}'>#{r['id']}</a></td><td>{html.escape(r['file_name'])}</td><td><span class='pill {r['status']}'>{r['status']}</span></td><td>{r.get('sheet_count') or 0}</td><td>{r.get('data_rows') or 0}</td><td>{r.get('total_rows') or 0}</td><td>{r.get('image_count') or 0}</td></tr>" for r in imports)
            self.send_html(f"<section class='card'><h2>Import a workbook</h2><form class='upload' method='post' action='/upload' enctype='multipart/form-data'><input type='file' name='workbook' accept='.xlsx,.xlsm' required><button>Run extraction</button></form><p class='muted'>Original files remain unchanged. Total rows are audit evidence, never data.</p></section><section class='card scroll'><h2>Import history</h2><table><thead><tr><th>ID</th><th>File</th><th>Status</th><th>Sheets</th><th>Data rows</th><th>Total rows</th><th>Images</th></tr></thead><tbody>{rows or '<tr><td colspan=7>No imports yet.</td></tr>'}</tbody></table></section>")
            return
        match = re.fullmatch(r"/imports/(\d+)", path)
        if match:
            data = self.pipeline.store.get_import(int(match.group(1)))
            if not data: self.send_error(404); return
            data_rows = sum(r["row_type"] == "data" for s in data["sheets"] for r in s["records"])
            excluded = sum(r["row_type"] in ("total","subtotal") for s in data["sheets"] for r in s["records"])
            uncertain = sum(r["row_type"] == "uncertain" for s in data["sheets"] for r in s["records"])
            images = sum(len(s["images"]) for s in data["sheets"])
            fails = sum(r["status"] == "fail" for s in data["sheets"] for r in s["reconciliations"])
            audits = "".join(f"<tr><td>{html.escape(s['name'])}</td><td>{r['source_row']}</td><td>{html.escape(r['column_name'])}</td><td>{r['written_value']}</td><td>{r['calculated_value']}</td><td>{r['difference']}</td><td><span class='pill {r['status']}'>{r['status']}</span></td></tr>" for s in data["sheets"] for r in s["reconciliations"])
            self.send_html(f"<section class='card'><a href='/'>← All imports</a><h2>{html.escape(data['file_name'])}</h2><p><span class='pill {data['status']}'>{data['status']}</span></p><div class='metrics'><div class='metric'><b>{data_rows}</b>clean data rows</div><div class='metric'><b>{excluded}</b>excluded totals</div><div class='metric'><b>{images}</b>linked images</div><div class='metric'><b>{uncertain}</b>review rows</div><div class='metric'><b>{fails}</b>failed checks</div></div><p><a class='button' href='/exports/{data['id']}'>Export clean report</a></p></section><section class='card scroll'><h2>Reconciliation evidence</h2><table><thead><tr><th>Sheet</th><th>Row</th><th>Column</th><th>Written</th><th>Calculated</th><th>Difference</th><th>Status</th></tr></thead><tbody>{audits or '<tr><td colspan=7>No numeric total rows found.</td></tr>'}</tbody></table></section>")
            return
        match = re.fullmatch(r"/exports/(\d+)", path)
        if match:
            import_id = int(match.group(1)); target = self.pipeline.settings.exports_dir / f"clean_report_{import_id}.xlsx"
            try: export_clean_report(self.pipeline.store, import_id, target)
            except ValueError: self.send_error(404); return
            payload = target.read_bytes(); self.send_response(200); self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"); self.send_header("Content-Disposition", f'attachment; filename="{target.name}"'); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/upload": self.send_error(404); return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > self.pipeline.settings.max_upload_bytes + 1024 * 1024:
            self.send_html("<div class='error'>Invalid or oversized upload.</div>", 413); return
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD":"POST", "CONTENT_TYPE":self.headers.get("Content-Type", "")})
        item = form["workbook"] if "workbook" in form else None
        if item is None or not getattr(item, "filename", ""):
            self.send_html("<div class='error'>Choose a workbook.</div>", 400); return
        safe_name = Path(item.filename).name
        suffix = Path(safe_name).suffix.lower()
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                remaining = self.pipeline.settings.max_upload_bytes
                while True:
                    chunk = item.file.read(min(1024 * 1024, remaining + 1))
                    if not chunk: break
                    remaining -= len(chunk)
                    if remaining < 0: raise ValueError("Upload exceeds limit")
                    tmp.write(chunk)
                temp_path = Path(tmp.name)
            result = self.pipeline.ingest(temp_path, safe_name)
            temp_path.unlink(missing_ok=True)
            self.send_response(HTTPStatus.SEE_OTHER); self.send_header("Location", f"/imports/{result.import_id}"); self.end_headers()
        except Exception as exc:
            self.send_html(f"<div class='error'>Import failed: {html.escape(str(exc))}</div><p><a href='/'>Return</a></p>", 400)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[web] {self.address_string()} {fmt % args}")


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 8765) -> None:
    pipeline = IngestionPipeline(settings)
    handler = type("ConfiguredHandler", (AppHandler,), {"pipeline": pipeline})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Document Flow running at http://{host}:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

