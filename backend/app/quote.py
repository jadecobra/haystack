"""Previous-close quote and recent stock splits (no API key).

Yahoo chart first. NASDAQ summary if Yahoo fails or returns nothing.
Quote cache 24h (memory + disk); in-flight quote requests coalesce.
Splits cache 24h on disk only. Stale disk is used only if fetches fail.
"""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import Future
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, NamedTuple

import httpx

_UA = "LongMuch/1.0 (contact@longmuch.local)"
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "quotes"
_CACHE_TTL_S = 24 * 3600

_lock = threading.Lock()
_mem: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight: dict[str, Future] = {}


class Split(NamedTuple):
    ex_date: date
    ratio: float


def _cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"{ticker}.json"


def _splits_cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"{ticker}.splits.json"


def _read_json(path: Path, *, max_age_s: float | None) -> Any | None:
    if not path.is_file():
        return None
    if max_age_s is not None:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return None
        if age > max_age_s:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _read_disk(ticker: str, *, max_age_s: float | None) -> dict[str, Any] | None:
    raw = _read_json(_cache_path(ticker), max_age_s=max_age_s)
    if not isinstance(raw, dict) or raw.get("price") is None:
        return None
    return raw


def _write_disk(ticker: str, payload: dict[str, Any]) -> None:
    _write_json(_cache_path(ticker), payload)


def _read_splits_disk(ticker: str, *, max_age_s: float | None) -> list[Split] | None:
    raw = _read_json(_splits_cache_path(ticker), max_age_s=max_age_s)
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
    _write_json(_splits_cache_path(ticker), payload)


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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
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


def _fetch_yahoo_splits(ticker: str) -> list[Split]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    with httpx.Client(timeout=5.0, headers={"User-Agent": _UA}) as client:
        resp = client.get(
            url, params={"range": "2y", "interval": "3mo", "events": "splits"}
        )
        resp.raise_for_status()
        return _parse_yahoo_splits(resp.json())


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


def _fetch_cnbc(ticker: str) -> dict[str, Any] | None:
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
        return _parse_cnbc(resp.json())


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
    symbol = ticker.upper().strip()
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
    """Return recent Yahoo stock splits for ticker; cached 24h on disk, fail-soft to []."""
    symbol = ticker.upper().strip()
    if not symbol:
        return []
    fresh = _read_splits_disk(symbol, max_age_s=_CACHE_TTL_S)
    if fresh is not None:
        return fresh
    try:
        splits = _fetch_yahoo_splits(symbol)
    except (httpx.HTTPError, ValueError):
        stale = _read_splits_disk(symbol, max_age_s=None)
        return stale if stale is not None else []
    try:
        _write_splits_disk(symbol, splits)
    except OSError:
        pass
    return splits
