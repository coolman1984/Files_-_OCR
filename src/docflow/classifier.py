from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


TOTAL_WORDS = {
    "total", "totals", "grand total", "subtotal", "sub-total",
    "الإجمالي", "اجمالي", "إجمالي", "المجموع", "المجموع الكلي", "الإجمالي العام",
    "합계", "총계", "소계",
}
SUBTOTAL_WORDS = {"subtotal", "sub-total", "الإجمالي الفرعي", "اجمالي فرعي", "소계"}
GRAND_TOTAL_WORDS = {"grand total", "الإجمالي العام", "المجموع الكلي", "총계"}


@dataclass(frozen=True)
class Classification:
    row_type: str
    reasons: list[str]
    scope: str | None = None


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def contains_term(values: list[Any], terms: set[str]) -> bool:
    text = " | ".join(normalized_text(v) for v in values if v is not None)
    return any(re.search(rf"(^|\W){re.escape(term)}($|\W)", text) for term in terms)


def classify_row(values: list[Any], formulas: list[Any], *, merged: bool = False) -> Classification:
    populated = [v for v in values if v not in (None, "")]
    if not populated:
        return Classification("empty", ["all_cells_empty"])

    formula_text = " ".join(str(v).upper() for v in formulas if isinstance(v, str))
    has_sum_formula = "SUM(" in formula_text or "SUBTOTAL(" in formula_text
    has_total_word = contains_term(values, TOTAL_WORDS)
    if has_total_word or has_sum_formula:
        if contains_term(values, GRAND_TOTAL_WORDS):
            return Classification("total", ["grand_total_label"], "all_preceding_data")
        if contains_term(values, SUBTOTAL_WORDS) or "SUBTOTAL(" in formula_text:
            return Classification("subtotal", ["subtotal_marker"], "current_section")
        return Classification("total", ["total_marker_or_sum_formula"], "current_section")

    numeric_count = sum(isinstance(v, (int, float)) and not isinstance(v, bool) for v in populated)
    if merged and len(populated) <= 2 and numeric_count == 0:
        return Classification("section", ["merged_text_row"])
    if len(populated) == 1 and numeric_count == 0:
        return Classification("section", ["single_text_cell"])
    if numeric_count == 0 and len(populated) <= 2:
        return Classification("uncertain", ["sparse_non_numeric_row"])
    return Classification("data", ["tabular_values"])

