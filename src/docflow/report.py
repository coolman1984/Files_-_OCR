from __future__ import annotations

from pathlib import Path

import xlsxwriter

from .store import Store


def export_clean_report(store: Store, import_id: int, output: Path) -> Path:
    data = store.get_import(import_id)
    if data is None:
        raise ValueError(f"Import {import_id} does not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output)
    title = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": "#14213D", "align": "center"})
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#2457C5", "border": 1})
    ok = workbook.add_format({"font_color": "#16794B", "bg_color": "#E8F7EF"})
    warn = workbook.add_format({"font_color": "#A64500", "bg_color": "#FFF1E5"})
    summary = workbook.add_worksheet("Summary")
    summary.merge_range("A1:F1", "Document Flow — Verified Extraction Report", title)
    summary.write_row("A3", ["Import ID", "Source file", "Status", "SHA-256", "Sheets", "Generated output"], header)
    summary.write_row("A4", [data["id"], data["file_name"], data["status"], data["sha256"], len(data["sheets"]), output.name])
    summary.set_column("A:A", 12); summary.set_column("B:B", 28); summary.set_column("C:C", 18); summary.set_column("D:D", 68); summary.set_column("E:F", 18)
    used_names: set[str] = {"Summary"}
    for sheet in data["sheets"]:
        base = ("Clean_" + sheet["name"])[:31]
        name = base
        index = 2
        while name in used_names:
            suffix = f"_{index}"; name = base[:31-len(suffix)] + suffix; index += 1
        used_names.add(name)
        ws = workbook.add_worksheet(name)
        columns = ["Source Row", "Image Count", "Image Preview", *sheet["headers"]]
        ws.write_row(0, 0, columns, header)
        image_paths = {item["sha256"]: item["path"] for item in sheet["images"]}
        output_row = 1
        for record in sheet["records"]:
            if record["row_type"] != "data":
                continue
            ws.write(output_row, 0, record["source_row"])
            ws.write(output_row, 1, len(record["image_hashes"]))
            for image_index, image_hash in enumerate(record["image_hashes"][:3]):
                image_path = image_paths.get(image_hash)
                if image_path and Path(image_path).exists():
                    ws.insert_image(output_row, 2, image_path, {
                        "x_scale": 0.32, "y_scale": 0.32,
                        "x_offset": image_index * 42, "y_offset": 2,
                        "object_position": 1,
                    })
                    ws.set_row(output_row, 52)
            for col, key in enumerate(sheet["headers"], start=3):
                ws.write(output_row, col, record["values"].get(key))
            output_row += 1
        ws.autofilter(0, 0, max(0, output_row - 1), len(columns) - 1)
        ws.freeze_panes(1, 3)
        ws.set_column(0, 1, 13); ws.set_column(2, 2, 22); ws.set_column(3, len(columns) - 1, 18)
        audit_name = ("Audit_" + sheet["name"])[:31]
        if audit_name in used_names:
            audit_name = ("Audit_" + str(sheet["id"]))[:31]
        used_names.add(audit_name)
        audit = workbook.add_worksheet(audit_name)
        audit.write_row(0, 0, ["Source Row", "Column", "Written", "Calculated", "Difference", "Status", "Scope"], header)
        for row_index, rec in enumerate(sheet["reconciliations"], start=1):
            fmt = ok if rec["status"] == "pass" else warn
            audit.write_row(row_index, 0, [rec["source_row"], rec["column_name"], rec["written_value"], rec["calculated_value"], rec["difference"], rec["status"], rec["scope"]], fmt)
        audit.set_column("A:G", 20)
    workbook.close()
    return output
