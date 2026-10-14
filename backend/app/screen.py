"""S&P 500 owner-earnings-yield screen: static ranked JSON artifact."""

from __future__ import annotations

import json
import math
import os
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.metrics import compute_year

UNIVERSE = "sp500"
ARTIFACT_NAME = "sp500-oe-yield.json"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_tickers.json"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "screen"
CACHE_PATH = CACHE_DIR / ARTIFACT_NAME
BACKEND_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / ARTIFACT_NAME
PUBLIC_SEED_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "public"
    / "screen"
    / ARTIFACT_NAME
)
STALE_AFTER_S = 36 * 3600
CAVEAT = (
    "Trailing annual owner earnings per share divided by prior close — "
    "not live, not a growth screen."
)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_sectors(path: Path | None = None) -> dict[str, str]:
    """Ticker → GICS sector from ``sp500_tickers.json`` ``sectors``.

    Tickers absent from the map are non-financial. Callers compare with
    ``== "Financials"``.
    """
    raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    sectors = raw.get("sectors") if isinstance(raw, dict) else None
    if not isinstance(sectors, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in sectors.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        symbol = key.upper().strip()
        if symbol:
            out[symbol] = value
    return out


def load_universe(path: Path | None = None) -> list[str]:
    raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    tickers = raw.get("tickers") if isinstance(raw, dict) else raw
    if not isinstance(tickers, list):
        raise ValueError("sp500 ticker list missing tickers[]")  # noqa: TRY004 - ValueError is the documented contract
    out: list[str] = []
    seen: set[str] = set()
    for item in tickers:
        if not isinstance(item, str):
            continue
        symbol = item.upper().strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def _edgar_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def _quote_candidates(ticker: str) -> list[str]:
    primary = ticker.upper().strip()
    alt = primary.replace(".", "-")
    if alt == primary:
        return [primary]
    return [primary, alt]


# Why a row's OE yield is blank (the row is still kept, #52).
OE_NOTE_NO_OE = "no owner earnings: no operating cash flow with capex or D&A in the latest 10-K year"
OE_NOTE_NO_SHARES = "no share count: no undimensioned diluted, basic or outstanding shares (multi-class issuer)"
OE_NOTE_SCALE = "OE yield outside -100%..100%: companyfacts unit/scale error"
# Why a ticker has no row at all.
EXCLUDE_NO_FACTS = "no SEC annual us-gaap facts (new registrant or not yet in SEC ticker map)"
EXCLUDE_NO_PRICE = "no previous close quote"


def _row_from_facts(
    ticker: str,
    *,
    years: list[int],
    statements: dict[int, dict[str, Any]],
    company_name: str | None,
    quote: dict[str, Any] | None,
) -> dict[str, Any] | None:
    row, _reason = _row_or_reason(
        ticker, years=years, statements=statements, company_name=company_name, quote=quote
    )
    return row


def _row_or_reason(
    ticker: str,
    *,
    years: list[int],
    statements: dict[int, dict[str, Any]],
    company_name: str | None,
    quote: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """A snapshot row, or (None, exclusion reason).

    A ticker with 10-K years and a price always gets a row. When owner
    earnings per share cannot be computed (banks/insurers without capex or
    D&A tags, multi-class share counts, scale errors) the OE columns are
    blank and ``oe_note`` says why; NI/equity and debt/equity still fill.
    """
    if not years:
        return None, EXCLUDE_NO_FACTS
    fy = max(years)
    stmt = statements.get(fy) or {}
    if not quote or quote.get("price") is None:
        return None, EXCLUDE_NO_PRICE
    try:
        price = float(quote["price"])
    except (TypeError, ValueError):
        return None, EXCLUDE_NO_PRICE
    computed = compute_year(stmt, None, previous_close=price)
    oe_yield = _num(computed.get("Owner Earnings / Last Close Price"))
    oe_ps = _num(computed.get("Owner Earnings per Share"))
    note: str | None = None
    if oe_yield is None or oe_ps is None:
        note = OE_NOTE_NO_OE if _num(stmt.get("owner_earnings")) is None else OE_NOTE_NO_SHARES
        oe_yield = oe_ps = None
    elif oe_yield > 1.0 or oe_yield < -1.0:
        note = OE_NOTE_SCALE
        oe_yield = oe_ps = None
    as_of = quote.get("as_of")
    debt, debt_state = _debt_for_row(stmt)
    extra = sector_columns(stmt, price=price, oe_per_share=oe_ps, debt=debt, debt_state=debt_state)
    return {
        "ticker": ticker,
        "name": company_name,
        "oe_yield": oe_yield,
        "oe_per_share": oe_ps,
        "oe_note": note,
        "price": price,
        "fy": int(fy),
        "price_as_of": str(as_of) if as_of else None,
        "debt": debt,
        "debt_state": debt_state,
        **extra,
    }, None


SECTOR_COLUMNS = ("payback_years", "ni_to_equity", "debt_to_equity", "no_debt")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def sector_columns(
    stmt: dict[str, Any],
    *,
    price: float,
    oe_per_share: float | None,
    debt: float | None,
    debt_state: str,
) -> dict[str, Any]:
    """Sector-table columns (#43) from the row's own fiscal year.

    payback_years: price / OE per share (latest FY), only when OE > 0.
    ni_to_equity / debt_to_equity: only when equity > 0, as in the analyze metrics.
    no_debt: True/False from debt_state; None when unknown or n/a (Financials).
    """
    equity = _num(stmt.get("equity"))
    ni = _num(stmt.get("net_income"))
    pos_equity = equity is not None and equity > 0
    return {
        "payback_years": price / oe_per_share if oe_per_share is not None and oe_per_share > 0 else None,
        "ni_to_equity": ni / equity if pos_equity and ni is not None else None,
        "debt_to_equity": debt / equity if pos_equity and debt is not None else None,
        "no_debt": {"zero": True, "positive": False}.get(debt_state),
    }


def column_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Known vs unknown counts per sector-table column, like debt_coverage."""
    out: dict[str, dict[str, int]] = {}
    for col in SECTOR_COLUMNS:
        known = sum(1 for r in rows if r.get(col) is not None)
        out[col] = {"known": known, "unknown": len(rows) - known}
    return out


def _debt_for_row(stmt: dict[str, Any]) -> tuple[float | None, str]:
    """Debt total and state for the row's fiscal year.

    Rows built from older fetch_facts that omit ``debt_state`` derive the
    state from ``stmt["debt"]``: >0 positive, ==0 zero, missing unknown.
    """
    raw = stmt.get("debt")
    debt: float | None
    if raw is None:
        debt = None
    else:
        try:
            debt = float(raw)
        except (TypeError, ValueError):
            debt = None
    state = stmt.get("debt_state")
    if state not in ("zero", "positive", "unknown", "n/a"):
        if debt is None:
            state = "unknown"
        elif debt > 0:
            state = "positive"
        elif debt == 0:
            state = "zero"
        else:
            state = "unknown"
    return debt, state


def debt_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"zero": 0, "positive": 0, "unknown": 0, "n/a": 0}
    unknown_tickers: list[str] = []
    for row in rows:
        state = row.get("debt_state")
        if state not in counts:
            state = "unknown"
        counts[state] += 1
        if state == "unknown":
            ticker = row.get("ticker")
            if isinstance(ticker, str) and ticker:
                unknown_tickers.append(ticker)
    return {
        "zero": counts["zero"],
        "positive": counts["positive"],
        "unknown": counts["unknown"],
        "n/a": counts["n/a"],
        "unknown_tickers": sorted(unknown_tickers),
    }


def log_debt_coverage(payload: dict[str, Any]) -> None:
    """One stderr line for the GitHub Actions run log."""
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return
    cov = meta.get("debt_coverage")
    if not isinstance(cov, dict):
        return
    tickers = cov.get("unknown_tickers") or []
    if not isinstance(tickers, list):
        tickers = []
    names = ",".join(str(t) for t in tickers)
    sys.stderr.write(
        "debt_coverage "
        f"zero={cov.get('zero', 0)} positive={cov.get('positive', 0)} "
        f"unknown={cov.get('unknown', 0)} n/a={cov.get('n/a', 0)} "
        f"unknown_tickers={names}\n"
    )
    cols = meta.get("column_coverage")
    if isinstance(cols, dict):
        parts = " ".join(
            f"{name}={c.get('known', 0)}/{c.get('known', 0) + c.get('unknown', 0)}"
            for name, c in cols.items()
            if isinstance(c, dict)
        )
        sys.stderr.write(f"column_coverage known/total {parts}\n")
    for ex in payload.get("excluded") or []:
        if isinstance(ex, dict):
            sys.stderr.write(f"excluded {ex.get('ticker')}: {ex.get('reason')}\n")
    blanks = [r for r in payload.get("rows") or [] if isinstance(r, dict) and r.get("oe_note")]
    for r in blanks:
        sys.stderr.write(f"blank_oe {r.get('ticker')}: {r.get('oe_note')}\n")


def rank_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """OE yield high to low; rows with a blank OE yield last, by ticker."""
    valid = [r for r in rows if isinstance(r, dict)]
    known = sorted((r for r in valid if r.get("oe_yield") is not None), key=lambda r: float(r["oe_yield"]), reverse=True)
    blank = sorted((r for r in valid if r.get("oe_yield") is None), key=lambda r: str(r.get("ticker")))
    return known + blank


def build_payload(
    tickers: list[str],
    *,
    fetch_facts: Callable[[str], tuple[list[int], dict[int, dict[str, Any]], str, str | None]],
    fetch_quote: Callable[[str], dict[str, Any] | None],
    built_at: str | None = None,
    error: str | None = None,
    sectors: dict[str, str] | None = None,
) -> dict[str, Any]:
    sector_by_ticker = load_sectors() if sectors is None else sectors
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    price_dates: list[str] = []
    for ticker in tickers:
        try:
            years, statements, _cik, name = fetch_facts(_edgar_symbol(ticker))
            quote = None
            for candidate in _quote_candidates(ticker):
                quote = fetch_quote(candidate)
                if quote:
                    break
            row, reason = _row_or_reason(
                ticker,
                years=years,
                statements=statements,
                company_name=name,
                quote=quote,
            )
        except Exception as exc:  # noqa: BLE001 - one bad ticker becomes an exclusion, not a failed build
            row, reason = None, f"{EXCLUDE_NO_FACTS}: {exc}"[:200]
        if row is None:
            excluded.append({"ticker": ticker, "reason": reason or "unknown"})
            continue
        if sector_by_ticker.get(str(row["ticker"]).upper()) == "Financials":
            row["debt_state"] = "n/a"
            row["no_debt"] = None
        if row.get("price_as_of"):
            price_dates.append(str(row["price_as_of"]))
        rows.append(row)
    ranked = rank_rows(rows)
    # GICS on the stored rows too, so the static seed the frontend falls back
    # to can still group sector tables (#43).
    with_gics({"rows": ranked})
    as_of = max(price_dates) if price_dates else None
    stamp = built_at or _now_iso()
    return {
        "universe": UNIVERSE,
        "count": len(ranked),
        "ranked": sum(1 for r in ranked if r.get("oe_yield") is not None),
        "skipped": len(excluded),
        "excluded": excluded,
        "built_at": stamp,
        "price_as_of": as_of,
        "stale": False,
        "error": error,
        "caveat": CAVEAT,
        "rows": ranked,
        "meta": {
            "debt_coverage": debt_coverage(ranked),
            "column_coverage": column_coverage(ranked),
        },
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def _mark_stale(payload: dict[str, Any], *, error: str | None = None) -> dict[str, Any]:
    out = dict(payload)
    out["stale"] = True
    if error:
        note = error
        existing = out.get("error")
        if existing and existing != note:
            note = f"{existing}; {note}"
        out["error"] = note
    return out


def _age_s(payload: dict[str, Any]) -> float | None:
    stamp = payload.get("built_at")
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds()


def _snapshot_paths() -> list[Path]:
    return [CACHE_PATH, BACKEND_SEED_PATH, PUBLIC_SEED_PATH]


def with_gics(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp GICS sector / sub-industry on each row at serve time (#41)."""
    from app.classification import load_gics

    try:
        gics = load_gics()
    except Exception:  # noqa: BLE001 - fail-soft: rows still serve without labels
        return payload
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        hit = gics.get(str(row.get("ticker") or "").upper()) or {}
        row.setdefault("sector", hit.get("sector"))
        row.setdefault("sub_industry", hit.get("sub_industry"))
    return payload


def load_snapshot() -> dict[str, Any] | None:
    for path in _snapshot_paths():
        payload = _read_json(path)
        if payload and isinstance(payload.get("rows"), list):
            payload = with_gics(payload)
            age = _age_s(payload)
            if age is not None and age > STALE_AFTER_S:
                return _mark_stale(payload)
            return payload
    return None


def write_snapshot(payload: dict[str, Any], *, also_seed: bool = False) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(CACHE_PATH)
    if also_seed:
        for dest in (BACKEND_SEED_PATH, PUBLIC_SEED_PATH):
            dest.parent.mkdir(parents=True, exist_ok=True)
            seed_tmp = dest.with_suffix(".tmp")
            seed_tmp.write_text(text, encoding="utf-8")
            seed_tmp.replace(dest)
    return CACHE_PATH


def _live_facts(ticker: str) -> tuple[list[int], dict[int, dict[str, Any]], str, str | None]:
    from app import edgar

    return edgar.statements_for_ticker(ticker)


def _live_quote(ticker: str) -> dict[str, Any] | None:
    from app.quote import previous_close

    return previous_close(ticker)


def screen_build(
    tickers: list[str] | None = None,
    *,
    fail_soft: bool = True,
    also_seed: bool = False,
    fetch_facts: Callable[..., Any] | None = None,
    fetch_quote: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    universe = tickers if tickers is not None else load_universe()
    facts = fetch_facts or _live_facts
    quotes = fetch_quote or _live_quote
    try:
        payload = build_payload(universe, fetch_facts=facts, fetch_quote=quotes)
        if not payload["rows"]:
            raise ValueError("screen produced zero ranked rows")
        write_snapshot(payload, also_seed=also_seed)
        log_debt_coverage(payload)
        return payload
    except Exception as exc:
        if not fail_soft:
            raise
        previous = load_snapshot()
        if previous is None:
            raise
        kept = _mark_stale(previous, error=f"rebuild failed: {exc}")
        write_snapshot(kept, also_seed=False)
        log_debt_coverage(kept)
        return kept


def rebuild_token() -> str:
    return (os.environ.get("SCREEN_REBUILD_TOKEN") or "").strip()
