"""Statement source for the locked ratio table."""

from __future__ import annotations

import os
import time
from typing import Any

from app import fixture
from app.classification import classify, load_gics
from app.metrics import (
    FIELDS,
    LOCKED_LABELS,
    SCHEMA_VERSION,
    TREASURY_LABEL,
    build_table,
    groups_payload,
)
from app.payback import build_payback
from app.peers import peers_for
from app.sic_peers import sic_peers_for


def _env_force_fixture() -> bool:
    return os.environ.get("HAYSTACK_PREFER_FIXTURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _fixture_dgs30_meta(treasury: dict[int, float]) -> tuple[float | None, str | None]:
    if not treasury:
        return None, None
    last_y = max(treasury.keys())
    rate = float(treasury[last_y])
    return round(rate * 100.0, 2), f"{last_y}-12-31"


def _safe_peers(ticker: str) -> dict[str, Any] | None:
    try:
        gics = peers_for(ticker)
        if gics is not None:
            return gics
        symbol = ticker.upper().strip()
        if {symbol, symbol.replace("-", "."), symbol.replace(".", "-")} & set(load_gics()):
            return None  # S&P 500 name: GICS only, never SIC (#54)
        return sic_peers_for(ticker)  # precomputed map; no SEC request (#54)
    except Exception:  # noqa: BLE001 - peers are optional; never fail analyze
        return None


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 1)


def analyze(
    ticker: str,
    *,
    prefer_fixture: bool = False,
    include_timings: bool = False,
) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 8 or not ticker.replace(".", "").isalnum():
        raise ValueError("invalid ticker")

    t0 = time.perf_counter()
    use_fixture = prefer_fixture or _env_force_fixture()
    if use_fixture:
        years, statements, treasury = fixture.statements_for(ticker)
        prev_close = 100.0
        rows = build_table(years, statements, treasury, previous_close=prev_close)
        pct, as_of = _fixture_dgs30_meta(treasury)
        fixture_rate = float(treasury[max(treasury)]) if treasury else None
        year_labels = [str(y) for y in years]
        company_name = "Apple Inc." if ticker == "AAPL" else None
        out: dict[str, Any] = {
            "ticker": ticker,
            "company_name": company_name,
            "years": year_labels,
            "rows": rows,
            "source": "fixture",
            "status": "success",
            "message": f"{len(LOCKED_LABELS)} locked metrics, {len(years)} years (fixture)",
            "treasury_label": TREASURY_LABEL,
            "treasury_dgs30_pct": pct,
            "treasury_dgs30_as_of": as_of,
            "previous_close": prev_close,
            "previous_close_as_of": None,
            "groups": groups_payload(),
            "schema_version": SCHEMA_VERSION,
            "labels": list(LOCKED_LABELS),
            "cik": "320193" if ticker == "AAPL" else None,
            "payback": build_payback(
                price=prev_close,
                years=year_labels,
                rows=rows,
                treasury_rate_decimal=fixture_rate,
            ),
            "classification": classify(ticker),
            "peers": _safe_peers(ticker),
        }
        if include_timings:
            out["timings"] = {
                "cache_hit": True,
                "cache_source": None,
                "facts_ms": 0.0,
                "metrics_ms": 0.0,
                "quote_ms": 0.0,
                "total_ms": _ms(t0),
            }
        return out

    from app import edgar, fred

    facts_meta: dict[str, Any] = {}
    t_facts = time.perf_counter()
    try:
        years, statements, cik, company_name = edgar.statements_for_ticker(
            ticker,
            meta=facts_meta if include_timings else None,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"edgar fetch failed for {ticker}: {exc}") from exc
    facts_ms = _ms(t_facts)

    if not years:
        raise ValueError(f"no company / no annual facts for {ticker}")

    t_metrics = time.perf_counter()
    try:
        treasury = fred.treasury_for_years(years)
    except Exception:  # noqa: BLE001 - fail-soft: treasury columns blank
        treasury = {}

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
    dgs30_rate: float | None = None
    try:
        latest = fred.latest_dgs30()
        dgs30_pct = float(latest["pct"])
        dgs30_as_of = str(latest["as_of"])
        dgs30_rate = float(latest["rate"])
    except Exception:  # noqa: BLE001, S110 - fail-soft: DGS30 is optional
        pass
    metrics_part_ms = _ms(t_metrics)

    prev_close: float | None = None
    prev_close_as_of: str | None = None
    t_quote = time.perf_counter()
    try:
        from app.quote import previous_close as fetch_previous_close

        quote = fetch_previous_close(ticker)
        if quote:
            prev_close = float(quote["price"])
            as_of_q = quote.get("as_of")
            prev_close_as_of = str(as_of_q) if as_of_q else None
    except Exception:  # noqa: BLE001, S110 - fail-soft: previous close is optional
        pass
    quote_ms = _ms(t_quote)

    t_table = time.perf_counter()
    rows = build_table(years, statements, treasury, previous_close=prev_close)
    metrics_ms = round(metrics_part_ms + _ms(t_table), 1)
    year_labels = [str(y) for y in years]

    out = {
        "ticker": ticker,
        "company_name": company_name,
        "years": year_labels,
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
        "groups": groups_payload(),
        "schema_version": SCHEMA_VERSION,
        "labels": list(LOCKED_LABELS),
        "cik": str(cik) if cik is not None else None,
        "payback": build_payback(
            price=prev_close,
            years=year_labels,
            rows=rows,
            treasury_rate_decimal=dgs30_rate,
        ),
        "classification": classify(ticker, str(cik) if cik is not None else None),
        "peers": _safe_peers(ticker),
    }
    if include_timings:
        cache_source = facts_meta.get("cache_source")
        out["timings"] = {
            "cache_hit": cache_source in ("mem", "disk"),
            "cache_source": cache_source,
            "facts_ms": facts_ms,
            "metrics_ms": metrics_ms,
            "quote_ms": quote_ms,
            "total_ms": _ms(t0),
        }
    return out
