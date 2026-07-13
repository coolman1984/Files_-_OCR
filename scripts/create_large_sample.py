from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic large workbook fixture")
    parser.add_argument("--rows", type=int, default=500_000)
    parser.add_argument("--output", type=Path, default=Path("samples/large_factory_data.xlsx"))
    args = parser.parse_args()
    if args.rows < 1:
        raise SystemExit("--rows must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Factory Data")
    sheet.append(["Record ID", "Line", "Model", "Quantity", "Cost"])
    quantity_total = 0
    cost_total = 0.0
    for index in range(1, args.rows + 1):
        quantity = index % 11 + 1
        cost = round(index % 97 + 0.25, 2)
        quantity_total += quantity
        cost_total += cost
        sheet.append([f"R-{index:07d}", f"L-{index % 8 + 1}", f"M-{index % 24 + 1}", quantity, cost])
    sheet.append(["Grand Total", None, None, quantity_total, round(cost_total, 2)])
    workbook.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
