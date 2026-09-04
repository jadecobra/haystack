"""Previous-close quote via Yahoo Finance chart (no API key).

Previous close is a daily figure. Cache 24h (memory + disk) so repeat Analyze
hits for the same ticker do not call Yahoo. In-flight requests coalesce.
Stale disk is used only if Yahoo fails.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_UA = "LongMuch/1.0 (contact@longmuch.local)"
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "quotes"
_CACHE_TTL_S = 24 * 3600

_lock = threading.Lock()
_mem: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight: dict[str, Future] = {}


def _cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"{ticker}.json"


def _read_disk(ticker: str, *, max_age_s: float | None) -> dict[str, Any] | None:
    path = _cache_path(ticker)
    if not path.is_file():
        return None
    if max_age_s is not None:
        age = time.time() - path.stat().st_mtime
        if age > max_age_s:
            return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict) or raw.get("price") is None:
        return None
    return raw


def _write_disk(ticker: str, payload: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


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
        as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    return {"price": price, "as_of": as_of}


def _fetch_yahoo(ticker: str) -> dict[str, Any] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    with httpx.Client(timeout=10.0, headers={"User-Agent": _UA}) as client:
        # 1d range: previousClose is in chart meta; no extra history needed.
        resp = client.get(url, params={"range": "1d", "interval": "1d"})
        resp.raise_for_status()
        return _parse_yahoo(resp.json())


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
        except Exception:
            return None
        return dict(result) if result else None

    try:
        fresh = _read_disk(symbol, max_age_s=_CACHE_TTL_S)
        if fresh is not None:
            with _lock:
                _mem[symbol] = (time.time(), fresh)
            future.set_result(fresh)
            return dict(fresh)

        fetched = _fetch_yahoo(symbol)
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
    except Exception as exc:
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
