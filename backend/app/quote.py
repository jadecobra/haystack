"""Previous-close quote and recent stock splits (no API key).

Quote: Yahoo chart, then NASDAQ summary, then CNBC quote.
Splits: Yahoo chart (query1, then query2), then CNBC quote EventData.
Quote cache 24h (memory + disk); in-flight quote requests coalesce.
Splits cache 24h on disk only. Stale disk is used only if fetches fail.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from concurrent.futures import Future
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import httpx

logger = logging.getLogger(__name__)

_UA = "LongMuch/1.0 (contact@longmuch.local)"
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "quotes"
_CACHE_TTL_S = 24 * 3600
_SYMBOL_RE = re.compile(r"^[A-Z0-9]+(?:[.-][A-Z0-9]+)*$")

_lock = threading.Lock()
_mem: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight: dict[str, Future] = {}


def clear_mem_cache() -> None:
    """Clear the in-memory quote cache."""
    with _lock:
        _mem.clear()


class Split(NamedTuple):
    ex_date: date
    ratio: float


def _normalize_symbol(ticker: str) -> str | None:
    symbol = ticker.upper().strip()
    if not symbol or not _SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def _yahoo_symbol(symbol: str) -> str:
    return symbol.replace(".", "-")


def _read_json(filename: str, *, max_age_s: float | None) -> Any | None:
    base = os.path.normpath(os.path.abspath(_CACHE_DIR))
    target = os.path.normpath(os.path.join(base, filename))
    if not target.startswith(base + os.sep):
        return None
    if not os.path.isfile(target):
        return None
    if max_age_s is not None:
        try:
            age = time.time() - os.stat(target).st_mtime
        except OSError:
            return None
        if age > max_age_s:
            return None
    try:
        with open(target, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(filename: str, payload: Any) -> None:
    base = os.path.normpath(os.path.abspath(_CACHE_DIR))
    target = os.path.normpath(os.path.join(base, filename))
    if not target.startswith(base + os.sep):
        raise ValueError("invalid cache path")
    os.makedirs(base, exist_ok=True)
    tmp = f"{target}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, target)


def _read_disk(ticker: str, *, max_age_s: float | None) -> dict[str, Any] | None:
    raw = _read_json(f"{ticker}.json", max_age_s=max_age_s)
    if not isinstance(raw, dict) or raw.get("price") is None:
        return None
    return raw


def _write_disk(ticker: str, payload: dict[str, Any]) -> None:
    _write_json(f"{ticker}.json", payload)


def _read_splits_disk(ticker: str, *, max_age_s: float | None) -> list[Split] | None:
    raw = _read_json(f"{ticker}.splits.json", max_age_s=max_age_s)
    if not isinstance(raw, list):
        return None
    splits: list[Split] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        raw_ratio = item.get("ratio")
        if raw_ratio is None or isinstance(raw_ratio, bool):
            return None
        try:
            ex_date = date.fromisoformat(str(item["ex_date"]))
            ratio = float(raw_ratio)
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(ratio) or ratio <= 0:
            return None
        splits.append(Split(ex_date, ratio))
    return splits


def _write_splits_disk(ticker: str, splits: list[Split]) -> None:
    payload = [{"ex_date": s.ex_date.isoformat(), "ratio": s.ratio} for s in splits]
    _write_json(f"{ticker}.splits.json", payload)


def _parse_yahoo(payload: dict[str, Any]) -> dict[str, Any] | None:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None
    meta = results[0].get("meta") or {}
    raw = meta.get("previousClose")
    if raw is None:
        raw = meta.get("chartPreviousClose")
    if raw is None:
        return None
    try:
        price = round(float(raw), 2)
    except (TypeError, ValueError):
        return None
    as_of = None
    ts = meta.get("regularMarketTime")
    if isinstance(ts, (int, float)):
        as_of = datetime.fromtimestamp(int(ts), tz=UTC).date().isoformat()
    return {"price": price, "as_of": as_of}


def _fetch_yahoo(ticker: str) -> dict[str, Any] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_yahoo_symbol(ticker)}"
    with httpx.Client(timeout=5.0, headers={"User-Agent": _UA}) as client:
        resp = client.get(url, params={"range": "1d", "interval": "1d"})
        resp.raise_for_status()
        return _parse_yahoo(resp.json())


def _parse_yahoo_splits(payload: dict[str, Any]) -> list[Split]:
    if not isinstance(payload, dict):
        return []
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        return []
    results = chart.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return []
    events = results[0].get("events")
    if not isinstance(events, dict):
        return []
    raw_splits = events.get("splits")
    if not isinstance(raw_splits, dict):
        return []
    out: list[Split] = []
    for entry in raw_splits.values():
        if not isinstance(entry, dict):
            continue
        raw_date = entry.get("date")
        raw_num = entry.get("numerator")
        raw_den = entry.get("denominator")
        if (
            raw_date is None
            or isinstance(raw_date, bool)
            or raw_num is None
            or isinstance(raw_num, bool)
            or raw_den is None
            or isinstance(raw_den, bool)
        ):
            continue
        try:
            ex_date = datetime.fromtimestamp(int(raw_date), tz=UTC).date()
            num = float(raw_num)
            den = float(raw_den)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        if not (math.isfinite(num) and math.isfinite(den)) or num <= 0 or den <= 0:
            continue
        ratio = num / den
        if not math.isfinite(ratio) or ratio <= 0:
            continue
        out.append(Split(ex_date, ratio))
    out.sort(key=lambda s: s.ex_date)
    return out


def _fetch_yahoo_splits(
    ticker: str, *, host: str = "query1.finance.yahoo.com"
) -> list[Split] | None:
    url = f"https://{host}/v8/finance/chart/{_yahoo_symbol(ticker)}"
    with httpx.Client(timeout=5.0, headers={"User-Agent": _UA}) as client:
        resp = client.get(
            url, params={"range": "2y", "interval": "3mo", "events": "splits"}
        )
        resp.raise_for_status()
        payload = resp.json()
    if not isinstance(payload, dict):
        return None
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        return None
    results = chart.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return None
    return _parse_yahoo_splits(payload)


def _parse_nasdaq(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data") or {}
    summary = data.get("summaryData") or {}
    raw = (summary.get("PreviousClose") or {}).get("value")
    if raw is None:
        return None
    text = str(raw).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        price = round(float(text), 2)
    except (TypeError, ValueError):
        return None
    return {"price": price, "as_of": None}


def _fetch_nasdaq(ticker: str) -> dict[str, Any] | None:
    url = f"https://api.nasdaq.com/api/quote/{ticker}/summary"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com",
    }
    with httpx.Client(timeout=5.0, headers=headers) as client:
        resp = client.get(url, params={"assetclass": "stocks"})
        resp.raise_for_status()
        return _parse_nasdaq(resp.json())


def _parse_cnbc(payload: dict[str, Any]) -> dict[str, Any] | None:
    quotes = (payload.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
    if not quotes or not isinstance(quotes[0], dict):
        return None
    q = quotes[0]
    raw = q.get("previous_day_closing")
    if raw is None:
        return None
    text = str(raw).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        price = round(float(text), 2)
    except (TypeError, ValueError):
        return None
    as_of = None
    last_time = q.get("last_time")
    if isinstance(last_time, str) and len(last_time) >= 10:
        try:
            as_of = date.fromisoformat(last_time[:10]).isoformat()
        except ValueError:
            as_of = None
    return {"price": price, "as_of": as_of}


def _fetch_cnbc_payload(ticker: str) -> Any:
    cnbc_symbol = ticker.replace("-", ".")
    url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
    params = {
        "symbols": cnbc_symbol,
        "requestMethod": "itv",
        "noform": "1",
        "partnerId": "2",
        "fund": "1",
        "exthrs": "1",
        "output": "json",
        "events": "1",
    }
    with httpx.Client(timeout=5.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _fetch_cnbc(ticker: str) -> dict[str, Any] | None:
    return _parse_cnbc(_fetch_cnbc_payload(ticker))


def _parse_cnbc_splits(
    payload: dict[str, Any], *, today: date | None = None
) -> list[Split] | None:
    if not isinstance(payload, dict):
        return None
    formatted = payload.get("FormattedQuoteResult")
    quotes = formatted.get("FormattedQuote") if isinstance(formatted, dict) else None
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        return None
    q = quotes[0]
    event_data = q.get("EventData") or {}
    if not isinstance(event_data, dict):
        return []
    raw_ex = event_data.get("split_ex_date")
    raw_factor = event_data.get("split_factor")
    if not isinstance(raw_ex, str) or not raw_ex.strip():
        return []
    if raw_factor is None or isinstance(raw_factor, bool):
        return []
    try:
        ex_date = datetime.strptime(raw_ex.strip(), "%m/%d/%Y").date()
        factor = float(raw_factor)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(factor) or factor <= 0:
        return []
    ratio = 1.0 / factor
    if not math.isfinite(ratio) or ratio <= 0:
        return []
    cutoff = (today or date.today()) + timedelta(days=3)
    if ex_date > cutoff:
        return []
    return [Split(ex_date, ratio)]


def _fetch_cnbc_splits(ticker: str) -> list[Split] | None:
    return _parse_cnbc_splits(_fetch_cnbc_payload(ticker))


def _fetch_splits(ticker: str) -> tuple[list[Split] | None, list[str]]:
    errors: list[str] = []
    for name, fetcher in (
        (
            "yahoo_query1",
            lambda s: _fetch_yahoo_splits(s, host="query1.finance.yahoo.com"),
        ),
        (
            "yahoo_query2",
            lambda s: _fetch_yahoo_splits(s, host="query2.finance.yahoo.com"),
        ),
        ("cnbc", _fetch_cnbc_splits),
    ):
        try:
            result = fetcher(ticker)
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"{name}: {type(exc).__name__}")
            continue
        if result is not None:
            return result, errors
        errors.append(f"{name}: empty")
    return None, errors


def _fetch_quote(ticker: str) -> dict[str, Any] | None:
    for fetcher in (_fetch_yahoo, _fetch_nasdaq, _fetch_cnbc):
        try:
            result = fetcher(ticker)
        except Exception:  # noqa: BLE001 - fail-soft: try next quote source
            result = None
        if result is not None:
            return result
    return None


def previous_close(ticker: str) -> dict[str, Any] | None:
    """Return {price, as_of} for the last completed session, or None on failure."""
    symbol = _normalize_symbol(ticker)
    if not symbol:
        return None

    now = time.time()
    with _lock:
        hit = _mem.get(symbol)
        if hit and now - hit[0] < _CACHE_TTL_S:
            return dict(hit[1])
        fut = _inflight.get(symbol)
        if fut is not None:
            waiter = fut
        else:
            waiter = None
            future: Future = Future()
            _inflight[symbol] = future

    if waiter is not None:
        try:
            result = waiter.result()
        except Exception:  # noqa: BLE001 - fail-soft: coalesced waiter gets no quote
            return None
        return dict(result) if result else None

    try:
        fresh = _read_disk(symbol, max_age_s=_CACHE_TTL_S)
        if fresh is not None:
            with _lock:
                _mem[symbol] = (time.time(), fresh)
            future.set_result(fresh)
            return dict(fresh)

        fetched = _fetch_quote(symbol)
        if fetched is not None:
            _write_disk(symbol, fetched)
            with _lock:
                _mem[symbol] = (time.time(), fetched)
            future.set_result(fetched)
            return dict(fetched)

        stale = _read_disk(symbol, max_age_s=None)
        if stale is not None:
            with _lock:
                _mem[symbol] = (time.time(), stale)
            future.set_result(stale)
            return dict(stale)

        future.set_result(None)
        return None
    except Exception as exc:  # noqa: BLE001 - fail-soft: serve stale quote cache
        stale = _read_disk(symbol, max_age_s=None)
        if stale is not None:
            with _lock:
                _mem[symbol] = (time.time(), stale)
            future.set_result(stale)
            return dict(stale)
        future.set_exception(exc)
        return None
    finally:
        with _lock:
            _inflight.pop(symbol, None)


def recent_splits(ticker: str) -> list[Split]:
    """Return recent stock splits for ticker; cached 24h on disk, fail-soft to []."""
    symbol = _normalize_symbol(ticker)
    if not symbol:
        return []
    fresh = _read_splits_disk(symbol, max_age_s=_CACHE_TTL_S)
    if fresh is not None:
        return fresh
    splits, errors = _fetch_splits(symbol)
    if splits is None:
        stale = _read_splits_disk(symbol, max_age_s=None)
        safe_symbol = symbol.replace("\r", "").replace("\n", "")
        logger.warning(
            "all split sources failed for %s (%s); %s",
            safe_symbol,
            ", ".join(errors),
            "using stale cache" if stale is not None else "no cache available",
        )
        return stale if stale is not None else []
    try:
        _write_splits_disk(symbol, splits)
    except OSError:
        pass
    return splits
