"""Statement source for the locked ratio table.

Local MVP uses a complete 5-year fixture so Analyze always returns a
computable table (including FCF / 30y Treasury). Live EDGAR XBRL mapping
is behind HAYSTACK_PREFER_FIXTURE=0 once that extractor exists.
"""

from __future__ import annotations

from typing import Any

from app import fixture
from app.metrics import LOCKED_LABELS, build_table


def analyze(ticker: str, *, prefer_fixture: bool = True) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 8 or not ticker.replace(".", "").isalnum():
        raise ValueError("invalid ticker")
    # Live EDGAR mapping is not shipped; fixture is the complete table.
    _ = prefer_fixture
    years, statements, treasury = fixture.statements_for(ticker)
    rows = build_table(years, statements, treasury)
    return {
        "ticker": ticker,
        "years": [str(y) for y in years],
        "rows": rows,
        "source": "fixture",
        "status": "success",
        "message": f"{len(LOCKED_LABELS)} locked metrics, {len(years)} years (fixture)",
        "treasury_label": "FCF / 30 Year Treasury per Share",
    }
