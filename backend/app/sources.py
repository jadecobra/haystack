"""Statement source for the locked ratio table.

Prod default: live SEC companyfacts + FRED DGS30 (prefer_fixture=False).
Agents / verify: ?fixture=1, CLI --local, or HAYSTACK_PREFER_FIXTURE=1.
"""

from __future__ import annotations

import os
from typing import Any

from app import fixture
from app.metrics import FIELDS, LOCKED_LABELS, TREASURY_LABEL, build_table


def _env_force_fixture() -> bool:
    return os.environ.get("HAYSTACK_PREFER_FIXTURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _fixture_dgs30_meta(treasury: dict[int, float]) -> tuple[float | None, str | None]:
    """Display pct + year-end as_of from last fixture treasury year."""
    if not treasury:
        return None, None
    last_y = max(treasury.keys())
    rate = float(treasury[last_y])
    return round(rate * 100.0, 2), f"{last_y}-12-31"


def analyze(ticker: str, *, prefer_fixture: bool = False) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 8 or not ticker.replace(".", "").isalnum():
        raise ValueError("invalid ticker")

    use_fixture = prefer_fixture or _env_force_fixture()
    if use_fixture:
        years, statements, treasury = fixture.statements_for(ticker)
        rows = build_table(years, statements, treasury)
        pct, as_of = _fixture_dgs30_meta(treasury)
        return {
            "ticker": ticker,
            "years": [str(y) for y in years],
            "rows": rows,
            "source": "fixture",
            "status": "success",
            "message": f"{len(LOCKED_LABELS)} locked metrics, {len(years)} years (fixture)",
            "treasury_label": TREASURY_LABEL,
            "treasury_dgs30_pct": pct,
            "treasury_dgs30_as_of": as_of,
            "previous_close": 100.0,
            "previous_close_as_of": None,
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

    dgs30_pct: float | None = None
    dgs30_as_of: str | None = None
    try:
        latest = fred.latest_dgs30()
        dgs30_pct = float(latest["pct"])
        dgs30_as_of = str(latest["as_of"])
    except Exception:
        pass

    prev_close: float | None = None
    prev_close_as_of: str | None = None
    try:
        from app.quote import previous_close as fetch_previous_close

        quote = fetch_previous_close(ticker)
        if quote:
            prev_close = float(quote["price"])
            as_of_q = quote.get("as_of")
            prev_close_as_of = str(as_of_q) if as_of_q else None
    except Exception:
        pass

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
        "treasury_label": TREASURY_LABEL,
        "treasury_dgs30_pct": dgs30_pct,
        "treasury_dgs30_as_of": dgs30_as_of,
        "previous_close": prev_close,
        "previous_close_as_of": prev_close_as_of,
    }
