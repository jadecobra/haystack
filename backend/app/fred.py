"""FRED DGS30 (30-year treasury) yields by calendar year."""

from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "fred"
_CACHE_PATH = _CACHE_DIR / "DGS30.json"
_CACHE_TTL_S = 24 * 3600  # daily

# (mtime, by_year, daily_latest | None)
_mem: tuple[float, dict[int, float], dict[str, Any] | None] | None = None


def _parse_yield(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw or raw == ".":
        return None
    try:
        # FRED CSV is percent (e.g. 4.35); store as decimal fraction.
        return float(raw) / 100.0
    except ValueError:
        return None


def _year_end_or_avg(daily: dict[str, float]) -> dict[int, float]:
    """Map observation dates → per calendar year: prefer last obs of year."""
    by_year: dict[int, list[tuple[str, float]]] = {}
    for date, val in daily.items():
        try:
            year = int(date[:4])
        except (TypeError, ValueError):
            continue
        by_year.setdefault(year, []).append((date, val))
    out: dict[int, float] = {}
    for year, pts in by_year.items():
        pts.sort(key=lambda t: t[0])
        out[year] = pts[-1][1]
    return out


def _daily_latest_from(daily: dict[str, float]) -> dict[str, Any] | None:
    if not daily:
        return None
    date = max(daily.keys())
    return {"date": date, "rate": float(daily[date])}


def _parse_cache_raw(raw: Any) -> tuple[dict[int, float], dict[str, Any] | None]:
    """Accept legacy flat {year: rate} or {"by_year":..., "daily_latest":...}."""
    if not isinstance(raw, dict) or not raw:
        raise ValueError("empty cache")
    if "by_year" in raw:
        by_year = {int(k): float(v) for k, v in dict(raw["by_year"]).items()}
        latest = raw.get("daily_latest")
        daily_latest: dict[str, Any] | None = None
        if isinstance(latest, dict) and latest.get("date") is not None and latest.get("rate") is not None:
            daily_latest = {"date": str(latest["date"]), "rate": float(latest["rate"])}
        return by_year, daily_latest
    # Legacy flat map of year -> rate
    by_year = {int(k): float(v) for k, v in raw.items()}
    return by_year, None


def _write_cache(by_year: dict[int, float], daily_latest: dict[str, Any] | None) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "by_year": {str(k): v for k, v in sorted(by_year.items())},
    }
    if daily_latest is not None:
        payload["daily_latest"] = {
            "date": str(daily_latest["date"]),
            "rate": float(daily_latest["rate"]),
        }
    _CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _fetch_fred_api(api_key: str) -> dict[str, float]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": "DGS30",
        "api_key": api_key,
        "file_type": "json",
        "observation_start": "2000-01-01",
    }
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
    daily: dict[str, float] = {}
    for obs in body.get("observations") or []:
        if not isinstance(obs, dict):
            continue
        date = str(obs.get("date") or "")
        val = _parse_yield(str(obs.get("value") or ""))
        if date and val is not None:
            daily[date] = val
    return daily


def _fetch_fred_csv() -> dict[str, float]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS30"
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text
    daily: dict[str, float] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        date = row.get("observation_date") or row.get("DATE") or ""
        if not date and row:
            date = next(iter(row.values()), "") or ""
        val_raw = row.get("DGS30")
        if val_raw is None:
            keys = [k for k in row.keys() if k and k.lower() not in {"observation_date", "date"}]
            val_raw = row.get(keys[0]) if keys else None
        val = _parse_yield(str(val_raw or ""))
        if date and val is not None:
            daily[str(date)] = val
    return daily


def _ensure_series(*, force: bool = False, need_latest: bool = False) -> tuple[dict[int, float], dict[str, Any] | None]:
    """Load or refresh DGS30 by_year (+ daily_latest when available)."""
    global _mem
    now = time.time()
    if not force and _mem and now - _mem[0] < _CACHE_TTL_S:
        by_year, daily_latest = _mem[1], _mem[2]
        if not need_latest or daily_latest is not None:
            return dict(by_year), (dict(daily_latest) if daily_latest else None)

    if not force and _CACHE_PATH.is_file():
        age = now - _CACHE_PATH.stat().st_mtime
        if age < _CACHE_TTL_S:
            try:
                raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                by_year, daily_latest = _parse_cache_raw(raw)
                if not need_latest or daily_latest is not None:
                    _mem = (now, by_year, daily_latest)
                    return dict(by_year), (dict(daily_latest) if daily_latest else None)
                # Legacy by_year-only cache: fall through to refresh for real as_of.
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

    api_key = (os.environ.get("FRED_API_KEY") or "").strip()
    if api_key:
        daily = _fetch_fred_api(api_key)
    else:
        daily = _fetch_fred_csv()
    by_year = _year_end_or_avg(daily)
    daily_latest = _daily_latest_from(daily)
    _write_cache(by_year, daily_latest)
    _mem = (time.time(), by_year, daily_latest)
    return dict(by_year), (dict(daily_latest) if daily_latest else None)


def fetch_dgs30_by_year(*, force: bool = False) -> dict[int, float]:
    """Return {calendar_year: decimal yield} using daily cache."""
    by_year, _ = _ensure_series(force=force, need_latest=False)
    return by_year


def latest_dgs30() -> dict[str, Any]:
    """Latest DGS30 observation: rate (decimal), pct (display %), as_of (YYYY-MM-DD)."""
    _, daily_latest = _ensure_series(force=False, need_latest=True)
    if not daily_latest:
        raise ValueError("DGS30 daily_latest unavailable")
    rate = float(daily_latest["rate"])
    return {
        "rate": rate,
        "pct": round(rate * 100.0, 2),
        "as_of": str(daily_latest["date"]),
    }


def treasury_for_years(years: list[int]) -> dict[int, float]:
    series = fetch_dgs30_by_year()
    return {y: series[y] for y in years if y in series}
