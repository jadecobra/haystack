"""SEC companyfacts fetch + FY annual US-GAAP mapping.

Prefer raw httpx to data.sec.gov companyfacts (cacheable JSON by CIK).
edgartools is optional for ticker→CIK; primary resolver uses company_tickers.json.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import httpx

from app.tags import TAG_PREFS

# backend/.cache/companyfacts/{cik}.json
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "companyfacts"
_TICKERS_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "company_tickers.json"
_CACHE_TTL_S = 24 * 3600
_MAX_RPS = 8.0
_MIN_INTERVAL = 1.0 / _MAX_RPS

_lock = threading.Lock()
_last_request_ts = 0.0
_mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_inflight: dict[str, Future] = {}
_identity_set = False


def sec_user_agent() -> str:
    return (
        os.environ.get("HAYSTACK_SEC_USER_AGENT")
        or os.environ.get("EDGAR_IDENTITY")
        or "LongMuch contact@longmuch.local"
    )


def _ensure_identity() -> None:
    global _identity_set
    if _identity_set:
        return
    ua = sec_user_agent()
    try:
        import edgar

        edgar.set_identity(ua)
    except Exception:
        pass
    _identity_set = True


def _rate_gate() -> None:
    global _last_request_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_ts)
        if wait > 0:
            time.sleep(wait)
        _last_request_ts = time.monotonic()


def _http_get_json(url: str, *, timeout: float = 60.0) -> dict[str, Any]:
    _ensure_identity()
    _rate_gate()
    headers = {
        "User-Agent": sec_user_agent(),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _normalize_cik(cik: str | int) -> str:
    return str(cik).lstrip("0") or "0"


def _cik_pad(cik: str | int) -> str:
    return f"{int(_normalize_cik(cik)):010d}"


def _load_ticker_map() -> dict[str, str]:
    """ticker upper -> CIK (no leading zeros required)."""
    now = time.time()
    if _TICKERS_CACHE.is_file():
        age = now - _TICKERS_CACHE.stat().st_mtime
        if age < _CACHE_TTL_S:
            try:
                data = json.loads(_TICKERS_CACHE.read_text(encoding="utf-8"))
                return {k: str(v) for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                pass
    raw = _http_get_json("https://www.sec.gov/files/company_tickers.json")
    mapping: dict[str, str] = {}
    if isinstance(raw, dict):
        for row in raw.values():
            if not isinstance(row, dict):
                continue
            t = str(row.get("ticker") or "").upper().strip()
            cik = row.get("cik_str")
            if t and cik is not None:
                mapping[t] = str(cik)
    _TICKERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _TICKERS_CACHE.write_text(json.dumps(mapping), encoding="utf-8")
    return mapping


def resolve_cik(ticker: str) -> str:
    ticker = ticker.upper().strip()
    mapping = _load_ticker_map()
    if ticker in mapping:
        return _normalize_cik(mapping[ticker])
    # Optional edgartools fallback
    _ensure_identity()
    try:
        from edgar import Company

        co = Company(ticker)
        cik = getattr(co, "cik", None) or getattr(co, "CIK", None)
        if cik is not None:
            return _normalize_cik(cik)
    except Exception as exc:
        raise ValueError(f"unknown ticker / no CIK for {ticker}: {exc}") from exc
    raise ValueError(f"unknown ticker / no CIK for {ticker}")


def _cache_path(cik: str) -> Path:
    return _CACHE_DIR / f"{_cik_pad(cik)}.json"


def _read_disk_cache(cik: str) -> dict[str, Any] | None:
    path = _cache_path(cik)
    if not path.is_file():
        return None
    age = time.time() - path.stat().st_mtime
    if age > _CACHE_TTL_S:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_disk_cache(cik: str, payload: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cik)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _fetch_companyfacts_uncached(cik: str) -> dict[str, Any]:
    pad = _cik_pad(cik)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{pad}.json"
    return _http_get_json(url)


def fetch_companyfacts(cik: str) -> dict[str, Any]:
    """Fetch companyfacts JSON with memory + disk cache and in-flight coalesce."""
    key = _cik_pad(cik)
    now = time.time()
    with _lock:
        hit = _mem_cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
        fut = _inflight.get(key)
        if fut is not None:
            waiter = fut
        else:
            waiter = None
            future: Future = Future()
            _inflight[key] = future

    if waiter is not None:
        return waiter.result()

    try:
        disk = _read_disk_cache(key)
        if disk is not None:
            with _lock:
                _mem_cache[key] = (time.time(), disk)
            future.set_result(disk)
            return disk
        payload = _fetch_companyfacts_uncached(key)
        _write_disk_cache(key, payload)
        with _lock:
            _mem_cache[key] = (time.time(), payload)
        future.set_result(payload)
        return payload
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)


def _is_annual(entry: dict[str, Any]) -> bool:
    fp = str(entry.get("fp") or "").upper()
    form = str(entry.get("form") or "").upper()
    if fp == "FY":
        return True
    if "10-K" in form:
        return True
    return False


def _unit_entries(fact_node: dict[str, Any], prefer_shares: bool = False) -> list[dict[str, Any]]:
    units = fact_node.get("units") or {}
    if not isinstance(units, dict):
        return []
    if prefer_shares:
        for key in ("shares", "pure"):
            if key in units and isinstance(units[key], list):
                return list(units[key])
    # Prefer USD, then USD/shares variants, then first list
    for key in ("USD", "USD/shares", "USD/share"):
        if key in units and isinstance(units[key], list):
            return list(units[key])
    for key, vals in units.items():
        if isinstance(vals, list) and vals:
            if prefer_shares and "share" not in key.lower() and key.lower() not in {"pure", "shares"}:
                continue
            return list(vals)
    if prefer_shares:
        # fall back to any
        for vals in units.values():
            if isinstance(vals, list):
                return list(vals)
    return []


def _pick_annual_by_year(entries: list[dict[str, Any]]) -> dict[int, float]:
    """Pick one value per FY: prefer FY/10-K, then latest filed/end."""
    by_year: dict[int, list[tuple[str, str, float]]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        if not _is_annual(e):
            continue
        fy = e.get("fy")
        if fy is None:
            continue
        try:
            year = int(fy)
        except (TypeError, ValueError):
            continue
        val = e.get("val")
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        filed = str(e.get("filed") or "")
        end = str(e.get("end") or "")
        by_year.setdefault(year, []).append((filed, end, num))
    out: dict[int, float] = {}
    for year, candidates in by_year.items():
        candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out[year] = candidates[0][2]
    return out


def _series_for_tags(
    us_gaap: dict[str, Any],
    tags: list[str],
    *,
    prefer_shares: bool = False,
) -> dict[int, float]:
    """Per-year: first preferred tag with an annual value for that year wins.

    Earlier tags in the list only fill years they actually have; later tags
    fill remaining years (so a stale Revenues FY2018 does not block
    RevenueFromContractWithCustomer… for 2020+).
    """
    out: dict[int, float] = {}
    for tag in tags:
        node = us_gaap.get(tag)
        if not isinstance(node, dict):
            continue
        entries = _unit_entries(node, prefer_shares=prefer_shares)
        series = _pick_annual_by_year(entries)
        for year, val in series.items():
            if year not in out:
                out[year] = val
    return out


def _merge_sum_series(a: dict[int, float], b: dict[int, float]) -> dict[int, float]:
    years = set(a) | set(b)
    out: dict[int, float] = {}
    for y in years:
        if y in a and y in b:
            out[y] = a[y] + b[y]
        elif y in a:
            out[y] = a[y]
        else:
            out[y] = b[y]
    return out


def _abs_series(series: dict[int, float]) -> dict[int, float]:
    return {y: abs(v) for y, v in series.items()}


def _compose_capex(us_gaap: dict[str, Any]) -> dict[int, float]:
    """Operating reinvestment cash outflow. Combined tag wins; no PPE+productive double count."""
    combined = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["capex_combined"]))
    ppe = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["capex_ppe"]))
    productive = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["capex_productive"]))
    software = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["capex_software"]))
    years = set(combined) | set(ppe) | set(productive) | set(software)
    out: dict[int, float] = {}
    for y in years:
        if y in combined:
            out[y] = combined[y]
            continue
        parts: list[float] = []
        if y in ppe:
            parts.append(ppe[y])
        elif y in productive:
            parts.append(productive[y])
        if y in software:
            parts.append(software[y])
        if parts:
            out[y] = sum(parts)
    return out


def _delta_nwc(
    year: int,
    ar: dict[int, float],
    inventory: dict[int, float],
    ap: dict[int, float],
) -> float | None:
    prev = year - 1
    terms: list[float] = []
    if year in ar and prev in ar:
        terms.append(ar[year] - ar[prev])
    if year in inventory and prev in inventory:
        terms.append(inventory[year] - inventory[prev])
    if year in ap and prev in ap:
        terms.append(-(ap[year] - ap[prev]))
    if not terms:
        return None
    return sum(terms)


def _resolve_ocf(
    us_gaap: dict[str, Any],
    net_income: dict[int, float],
    da: dict[int, float],
) -> dict[int, float]:
    """Reported OCF, then cash-identity, then NI+D&A−ΔNWC when WC pairs exist."""
    ocf = dict(_series_for_tags(us_gaap, TAG_PREFS["operating_cf"]))
    d_cash = _series_for_tags(us_gaap, TAG_PREFS["change_in_cash"])
    cfi = _series_for_tags(us_gaap, TAG_PREFS["investing_cf"])
    cff = _series_for_tags(us_gaap, TAG_PREFS["financing_cf"])
    fx = _series_for_tags(us_gaap, TAG_PREFS["fx_effect"])
    ar = _series_for_tags(us_gaap, TAG_PREFS["accounts_receivable"])
    inventory = _series_for_tags(us_gaap, TAG_PREFS["inventory"])
    ap = _series_for_tags(us_gaap, TAG_PREFS["accounts_payable"])

    years = (
        set(ocf)
        | set(d_cash)
        | set(cfi)
        | set(cff)
        | set(net_income)
        | set(da)
        | set(ar)
        | set(inventory)
        | set(ap)
    )
    for y in years:
        if y in ocf:
            continue
        if y in d_cash and y in cfi and y in cff:
            ocf[y] = d_cash[y] - cfi[y] - cff[y] - fx.get(y, 0.0)
            continue
        if y in net_income and y in da:
            dnwc = _delta_nwc(y, ar, inventory, ap)
            if dnwc is not None:
                ocf[y] = net_income[y] + da[y] - dnwc
    return ocf


def _owner_earnings(ocf: dict[int, float], capex: dict[int, float], da: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = {}
    for y in ocf:
        has_capex = y in capex
        has_da = y in da
        if not has_capex and not has_da:
            continue
        if has_capex and has_da:
            maint = min(capex[y], da[y])
        elif has_capex:
            maint = capex[y]
        else:
            maint = da[y]
        out[y] = ocf[y] - maint
    return out


def map_companyfacts_to_statements(
    companyfacts: dict[str, Any],
    *,
    max_years: int = 5,
) -> tuple[list[int], dict[int, dict[str, float | None]]]:
    """Map companyfacts JSON → (years newest-first, statements[year][field])."""
    facts = companyfacts.get("facts") or {}
    us_gaap = facts.get("us-gaap") or {}
    if not isinstance(us_gaap, dict) or not us_gaap:
        raise ValueError("companyfacts missing us-gaap facts")

    revenue = _series_for_tags(us_gaap, TAG_PREFS["revenue"])
    net_income = _series_for_tags(us_gaap, TAG_PREFS["net_income"])
    equity = _series_for_tags(us_gaap, TAG_PREFS["equity"])
    assets = _series_for_tags(us_gaap, TAG_PREFS["assets"])
    cash = _series_for_tags(us_gaap, TAG_PREFS["cash"])
    shares = _series_for_tags(us_gaap, TAG_PREFS["shares"], prefer_shares=True)
    dividends = _series_for_tags(us_gaap, TAG_PREFS["dividends"])

    liabilities = _series_for_tags(us_gaap, ["Liabilities"])
    if not liabilities:
        cur = _series_for_tags(us_gaap, TAG_PREFS["liabilities_current"])
        ncur = _series_for_tags(us_gaap, TAG_PREFS["liabilities_noncurrent"])
        if cur or ncur:
            liabilities = _merge_sum_series(cur, ncur)
    if not liabilities:
        lae = _series_for_tags(us_gaap, TAG_PREFS["liabilities_and_equity"])
        if lae and equity:
            liabilities = {
                y: lae[y] - equity[y]
                for y in lae
                if y in equity
            }

    debt = _series_for_tags(
        us_gaap,
        [
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "LongTermDebtAndCapitalLeaseObligations",
        ],
    )
    if not debt:
        dcur = _series_for_tags(us_gaap, TAG_PREFS["debt_current"])
        dlt = _series_for_tags(us_gaap, TAG_PREFS["debt_longterm"])
        if dcur or dlt:
            debt = _merge_sum_series(dcur, dlt)

    da = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["da"]))
    ocf = _resolve_ocf(us_gaap, net_income, da)
    capex = _compose_capex(us_gaap)
    fcf = _owner_earnings(ocf, capex, da)

    all_years = sorted(
        set(revenue)
        | set(net_income)
        | set(equity)
        | set(assets)
        | set(liabilities)
        | set(debt)
        | set(fcf)
        | set(dividends)
        | set(shares)
        | set(cash),
        reverse=True,
    )
    # Prefer years that have revenue or net_income (core 10-K presence)
    core = [y for y in all_years if y in revenue or y in net_income]
    years = (core or all_years)[:max_years]

    field_series: dict[str, dict[int, float]] = {
        "revenue": revenue,
        "net_income": net_income,
        "equity": equity,
        "assets": assets,
        "total_liabilities": liabilities,
        "debt": debt,
        "fcf": fcf,
        "dividends": dividends,
        "shares": shares,
        "cash": cash,
    }
    statements: dict[int, dict[str, float | None]] = {}
    for y in years:
        statements[y] = {
            k: (series[y] if y in series else None) for k, series in field_series.items()
        }
    return years, statements


def statements_for_ticker(
    ticker: str,
    *,
    max_years: int = 5,
) -> tuple[list[int], dict[int, dict[str, float | None]], str]:
    """Resolve ticker → companyfacts → statements. Returns (years, statements, cik)."""
    cik = resolve_cik(ticker)
    payload = fetch_companyfacts(cik)
    years, statements = map_companyfacts_to_statements(payload, max_years=max_years)
    if not years:
        raise ValueError(f"no annual us-gaap facts for {ticker} (CIK {cik})")
    return years, statements, cik
