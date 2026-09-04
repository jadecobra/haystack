"""Statement source for the locked ratio table.

Prod default: live SEC companyfacts + FRED DGS30 (prefer_fixture=False).
Agents / verify: ?fixture=1, CLI --local, or HAYSTACK_PREFER_FIXTURE=1.
"""

from __future__ import annotations

import os
from typing import Any

from app import fixture
from app.metrics import FIELDS, LOCKED_LABELS, build_table


def _env_force_fixture() -> bool:
    return os.environ.get("HAYSTACK_PREFER_FIXTURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def analyze(ticker: str, *, prefer_fixture: bool = False) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 8 or not ticker.replace(".", "").isalnum():
        raise ValueError("invalid ticker")

    use_fixture = prefer_fixture or _env_force_fixture()
    if use_fixture:
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

    from app import edgar, fred

    try:
        years, statements, cik = edgar.statements_for_ticker(ticker)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"edgar fetch failed for {ticker}: {exc}") from exc

    if not years:
        raise ValueError(f"no company / no annual facts for {ticker}")

    try:
        treasury = fred.treasury_for_years(years)
    except Exception:
        treasury = {}

    rows = build_table(years, statements, treasury)

    gaps: list[str] = []
    for y in years:
        stmt = statements.get(y) or {}
        missing = [f for f in FIELDS if stmt.get(f) is None]
        if missing:
            gaps.append(f"{y}: {','.join(missing)}")
    gap_note = f"; gaps: {'; '.join(gaps)}" if gaps else ""
    missing_ty = [str(y) for y in years if y not in treasury]
    if missing_ty:
        gap_note += f"; treasury missing: {','.join(missing_ty)}"

    return {
        "ticker": ticker,
        "years": [str(y) for y in years],
        "rows": rows,
        "source": "edgar",
        "status": "success",
        "message": (
            f"{len(LOCKED_LABELS)} locked metrics, {len(years)} years "
            f"(edgar CIK {cik}){gap_note}"
        ),
        "treasury_label": "FCF / 30 Year Treasury per Share",
    }
