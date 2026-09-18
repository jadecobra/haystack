"""S&P 500 owner-earnings-yield screen: static ranked JSON artifact."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_universe(path: Path | None = None) -> list[str]:
    raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    tickers = raw.get("tickers") if isinstance(raw, dict) else raw
    if not isinstance(tickers, list):
        raise ValueError("sp500 ticker list missing tickers[]")
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


def _row_from_facts(
    ticker: str,
    *,
    years: list[int],
    statements: dict[int, dict[str, Any]],
    company_name: str | None,
    quote: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not years:
        return None
    fy = max(years)
    stmt = statements.get(fy) or {}
    if not quote or quote.get("price") is None:
        return None
    try:
        price = float(quote["price"])
    except (TypeError, ValueError):
        return None
    computed = compute_year(stmt, None, previous_close=price)
    oe_yield = computed.get("Owner Earnings / Last Close Price")
    oe_ps = computed.get("Owner Earnings per Share")
    if oe_yield is None or oe_ps is None:
        return None
    # Skip pathological companyfacts units (e.g. shares in millions → OE/share absurd).
    try:
        yv = float(oe_yield)
    except (TypeError, ValueError):
        return None
    if yv > 1.0 or yv < -1.0:
        return None
    as_of = quote.get("as_of")
    return {
        "ticker": ticker,
        "name": company_name,
        "oe_yield": float(oe_yield),
        "oe_per_share": float(oe_ps),
        "price": price,
        "fy": int(fy),
        "price_as_of": str(as_of) if as_of else None,
    }


def rank_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = [r for r in rows if isinstance(r, dict) and r.get("oe_yield") is not None]
    return sorted(valid, key=lambda r: float(r["oe_yield"]), reverse=True)


def build_payload(
    tickers: list[str],
    *,
    fetch_facts: Callable[[str], tuple[list[int], dict[int, dict[str, Any]], str, str | None]],
    fetch_quote: Callable[[str], dict[str, Any] | None],
    built_at: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    price_dates: list[str] = []
    for ticker in tickers:
        try:
            years, statements, _cik, name = fetch_facts(_edgar_symbol(ticker))
            quote = None
            for candidate in _quote_candidates(ticker):
                quote = fetch_quote(candidate)
                if quote:
                    break
            row = _row_from_facts(
                ticker,
                years=years,
                statements=statements,
                company_name=name,
                quote=quote,
            )
        except Exception:
            row = None
        if row is None:
            skipped += 1
            continue
        if row.get("price_as_of"):
            price_dates.append(str(row["price_as_of"]))
        rows.append(row)
    ranked = rank_rows(rows)
    as_of = max(price_dates) if price_dates else None
    stamp = built_at or _now_iso()
    return {
        "universe": UNIVERSE,
        "count": len(ranked),
        "skipped": skipped,
        "built_at": stamp,
        "price_as_of": as_of,
        "stale": False,
        "error": error,
        "caveat": CAVEAT,
        "rows": ranked,
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
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _snapshot_paths() -> list[Path]:
    return [CACHE_PATH, BACKEND_SEED_PATH, PUBLIC_SEED_PATH]


def load_snapshot() -> dict[str, Any] | None:
    for path in _snapshot_paths():
        payload = _read_json(path)
        if payload and isinstance(payload.get("rows"), list):
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
        return payload
    except Exception as exc:
        if not fail_soft:
            raise
        previous = load_snapshot()
        if previous is None:
            raise
        kept = _mark_stale(previous, error=f"rebuild failed: {exc}")
        write_snapshot(kept, also_seed=False)
        return kept


def rebuild_token() -> str:
    return (os.environ.get("SCREEN_REBUILD_TOKEN") or "").strip()
