"""SEC companyfacts fetch + FY annual US-GAAP mapping.

Prefer raw httpx to data.sec.gov companyfacts (cacheable JSON by CIK).
edgartools is optional for ticker→CIK; primary resolver uses company_tickers.json.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import date
from concurrent.futures import Future
from pathlib import Path
from statistics import median
from typing import Any

import httpx

from app.tags import TAG_PREFS

_SPLIT_RATIO_LO = 1.0 / 1.15
_SPLIT_RATIO_HI = 1.15
# Largest real splits are ~50:1 (CMG 2024). Outside this band is a unit-scale error.
_SPLIT_ABS_LO = 1.0 / 60.0
_SPLIT_ABS_HI = 60.0

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
        if resp.status_code == 404:
            raise ValueError("unknown ticker / no companyfacts")
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
        raise ValueError(f"unknown ticker / no CIK for {ticker}") from exc
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


def fetch_companyfacts(
    cik: str,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch companyfacts JSON with memory + disk cache and in-flight coalesce.

    When ``meta`` is provided, sets ``meta["cache_source"]`` to
    ``"mem"`` | ``"disk"`` | ``"network"`` without changing cache behavior.
    In-flight waiters inherit the leader's source.
    """
    key = _cik_pad(cik)
    now = time.time()
    with _lock:
        hit = _mem_cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_S:
            if meta is not None:
                meta["cache_source"] = "mem"
            return hit[1]
        fut = _inflight.get(key)
        if fut is not None:
            waiter = fut
        else:
            waiter = None
            future: Future = Future()
            _inflight[key] = future

    if waiter is not None:
        payload, source = waiter.result()
        if meta is not None:
            meta["cache_source"] = source
        return payload

    try:
        disk = _read_disk_cache(key)
        if disk is not None:
            with _lock:
                _mem_cache[key] = (time.time(), disk)
            source = "disk"
            future.set_result((disk, source))
            if meta is not None:
                meta["cache_source"] = source
            return disk
        payload = _fetch_companyfacts_uncached(key)
        _write_disk_cache(key, payload)
        with _lock:
            _mem_cache[key] = (time.time(), payload)
        source = "network"
        future.set_result((payload, source))
        if meta is not None:
            meta["cache_source"] = source
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


def _period_key(entry: dict[str, Any]) -> tuple[Any, Any]:
    """Duration facts: (start, end); instant facts (e.g. shares outstanding): (None, end)."""
    return (entry.get("start"), entry.get("end"))


def _positive_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return num


def _median_by_filed(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """One value per filing date; median when that filing repeats the period."""
    by_filed: dict[str, list[float]] = defaultdict(list)
    for filed, val in rows:
        if filed:
            by_filed[filed].append(val)
    return [
        (filed, median(vals) if len(vals) > 1 else vals[0])
        for filed, vals in by_filed.items()
    ]


class _BasisJump:
    """A basis change that happened after filing ``lo`` and by filing ``hi``."""

    __slots__ = ("lo", "hi", "ratio")

    def __init__(self, lo: str, hi: str, ratio: float) -> None:
        self.lo = lo
        self.hi = hi
        self.ratio = ratio


def _ratio_in_band(ratio: float, target: float = 1.0) -> bool:
    """True when ``ratio`` is within the 1.15 band of ``target``."""
    if ratio <= 0 or target <= 0:
        return False
    rel = ratio / target
    return _SPLIT_RATIO_LO <= rel <= _SPLIT_RATIO_HI


def _filed_span_days(prev: str, new: str) -> int:
    """Calendar days from ``prev`` to ``new``. Unparseable dates sort last."""
    try:
        return (date.fromisoformat(new[:10]) - date.fromisoformat(prev[:10])).days
    except ValueError:
        return 10**9


def _jump_intervals_intersect(lo: str, hi: str, prev: str, new: str) -> bool:
    """(lo, hi] intersects (prev, new]."""
    return lo < new and prev < hi


def _scale_kept_chain(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Filed-order chain with unit-scale errors dropped.

    One median value per filed date. Walk that order and compare each value
    to the previous kept value. A ratio below 1/60 is a shrink-scale error
    (CPRT FY2012 filed 131428000, then 131428) and is dropped; the next filing
    is compared to the last kept value, not to the dropped one. A ratio above
    60 is not a split. It starts a candidate larger scale, because early
    filings are sometimes in thousands and a later filing restates in units
    (NVDA; CPRT FY2014). A second filing on that scale confirms it. If a later
    filing returns to the abandoned scale first, the candidate was a glitch
    and is dropped. Consecutive kept pairs stay inside [1/60, 60].
    """
    kept: list[tuple[str, float]] = []
    abandoned: list[tuple[str, float]] | None = None
    for filed, val in sorted(_median_by_filed(rows)):
        if val <= 0:
            continue
        if not kept:
            kept.append((filed, val))
            continue
        prev_filed, prev_val = kept[-1]
        if not prev_filed < filed or prev_val <= 0:
            continue
        ratio = val / prev_val
        if _SPLIT_ABS_LO <= ratio <= _SPLIT_ABS_HI:
            kept.append((filed, val))
            if len(kept) >= 2:
                abandoned = None
            continue
        if abandoned:
            a_filed, a_val = abandoned[-1]
            if a_val > 0 and a_filed < filed and _SPLIT_ABS_LO <= (val / a_val) <= _SPLIT_ABS_HI:
                kept = [*abandoned, (filed, val)]
                abandoned = None
                continue
        if ratio > _SPLIT_ABS_HI:
            abandoned = kept
            kept = [(filed, val)]
            continue
    return kept


def _collect_basis_pairs(
    entries: list[dict[str, Any]],
) -> tuple[list[tuple[str, str, float]], list[tuple[str, str]]]:
    """Consecutive kept pairs per period: events and same-basis pairs.

    The chain drops shrinks below 1/60 of the previous kept value and does not
    emit a pair across a larger-scale adoption. A remaining pair is same-basis
    inside the 1.15 band, otherwise an event.
    """
    by_period: dict[tuple[Any, Any], list[tuple[str, float]]] = defaultdict(list)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        val = _positive_float(entry.get("val"))
        if val is None:
            continue
        filed = str(entry.get("filed") or "")
        if not filed:
            continue
        by_period[_period_key(entry)].append((filed, val))

    events: list[tuple[str, str, float]] = []
    same_basis: list[tuple[str, str]] = []
    for rows in by_period.values():
        filed_vals = _scale_kept_chain(rows)
        for i in range(1, len(filed_vals)):
            prev, v_prev = filed_vals[i - 1]
            new, v_new = filed_vals[i]
            if v_prev <= 0 or not prev < new:
                continue
            ratio = v_new / v_prev
            if _ratio_in_band(ratio):
                same_basis.append((prev, new))
                continue
            events.append((prev, new, ratio))
    return events, same_basis


def _subset_products_matching(
    intersecting: list[_BasisJump],
    contained: list[_BasisJump],
    ratio: float,
) -> list[list[_BasisJump]]:
    """Subsets of ``intersecting`` that contain ``contained`` and match ``ratio``.

    ``|intersecting| > 10`` does not enumerate: the only candidate is the full set.
    """
    if len(intersecting) > 10:
        product = math.prod(jump.ratio for jump in intersecting) if intersecting else 1.0
        if _ratio_in_band(product, ratio):
            return [list(intersecting)]
        return []

    contained_ids = {id(jump) for jump in contained}
    extras = [jump for jump in intersecting if id(jump) not in contained_ids]
    base = math.prod(jump.ratio for jump in contained) if contained else 1.0
    matches: list[list[_BasisJump]] = []
    n_extra = len(extras)
    for mask in range(1 << n_extra):
        chosen = list(contained)
        product = base
        for bit in range(n_extra):
            if mask & (1 << bit):
                chosen.append(extras[bit])
                product *= extras[bit].ratio
        if _ratio_in_band(product, ratio):
            matches.append(chosen)
            if len(matches) > 1:
                break
    return matches


def _basis_jumps(
    events: list[tuple[str, str, float]],
    same_basis: list[tuple[str, str]],
) -> list[_BasisJump]:
    """Basis-jump intervals from split events, then same-basis narrowing."""
    ordered = sorted(
        events,
        key=lambda item: (abs(math.log(item[2])), _filed_span_days(item[0], item[1]), item[0], item[1]),
    )
    jumps: list[_BasisJump] = []
    for prev, new, ratio in ordered:
        intersecting = [
            jump
            for jump in jumps
            if _jump_intervals_intersect(jump.lo, jump.hi, prev, new)
        ]
        contained = [
            jump
            for jump in intersecting
            if prev <= jump.lo and jump.hi <= new
        ]
        matches = _subset_products_matching(intersecting, contained, ratio)
        if len(matches) == 1:
            for jump in matches[0]:
                lo = max(jump.lo, prev)
                hi = min(jump.hi, new)
                if lo < hi:
                    jump.lo = lo
                    jump.hi = hi
            continue
        if len(matches) > 1:
            continue
        contained_prod = math.prod(jump.ratio for jump in contained) if contained else 1.0
        residual = ratio / contained_prod
        if _ratio_in_band(residual):
            continue
        if prev < new:
            jumps.append(_BasisJump(prev, new, residual))

    for _pass in range(3):
        changed = False
        for jump in jumps:
            for prev, new in same_basis:
                if prev <= jump.lo < new < jump.hi:
                    jump.lo = new
                    changed = True
                elif jump.lo < prev < jump.hi <= new:
                    jump.hi = prev
                    changed = True
        if not changed:
            break
    return jumps


def _split_adjusted_shares_for_tag(
    entries: list[dict[str, Any]],
) -> dict[int, float]:
    """Split-adjust one share tag's annual series (steps a, b, c, e for a single tag)."""
    annual: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not _is_annual(entry):
            continue
        if entry.get("fy") is None:
            continue
        if _positive_float(entry.get("val")) is None:
            continue
        try:
            int(entry["fy"])
        except (TypeError, ValueError):
            continue
        annual.append(entry)
    if not annual:
        return {}

    by_period: dict[tuple[Any, Any], list[tuple[str, float]]] = defaultdict(list)
    for entry in annual:
        val = _positive_float(entry.get("val"))
        if val is None:
            continue
        filed = str(entry.get("filed") or "")
        by_period[_period_key(entry)].append((filed, val))

    # (c) Basis-jump intervals from every positive fact on this tag.
    events, same_basis = _collect_basis_pairs(entries)
    jumps = _basis_jumps(events, same_basis)

    # (a) Period identity: same fy pick as _pick_annual_by_year (max filed, then max end).
    by_fy: dict[int, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for entry in annual:
        year = int(entry["fy"])
        filed = str(entry.get("filed") or "")
        end = str(entry.get("end") or "")
        by_fy[year].append((filed, end, entry))

    out: dict[int, float] = {}
    for year, candidates in by_fy.items():
        candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
        chosen = candidates[0][2]
        rows = by_period.get(_period_key(chosen)) or []
        kept = _scale_kept_chain(rows)
        if not kept:
            continue
        # (b) Latest kept restatement for that exact period key (any fy).
        latest_filed, latest_val = kept[-1]
        if latest_val <= 0:
            continue
        factor = 1.0
        for jump in jumps:
            if latest_filed < jump.hi:
                factor *= jump.ratio
        adjusted = latest_val * factor
        if adjusted > 0:
            out[year] = adjusted
    return out


def split_adjusted_shares(us_gaap: dict[str, Any]) -> dict[int, float]:
    """Annual diluted/basic/outstanding shares on a post-split basis.

    Per tag in TAG_PREFS["shares"] order (same per-year fill semantics as
    _series_for_tags: earlier tag wins a year it has):

    a) Period identity: for year Y, take the entry the existing logic picks for
       fy=Y (annual, max filed then max end) and use its period key (start, end)
       — or (None, end) for instant tags like CommonStockSharesOutstanding.
       Same unit list as today (_unit_entries prefer_shares).
    b) Latest restatement: for that exact period key, build the filed chain
       across ALL annual filings (any fy) and take the latest kept value, so
       restated post-split figures win. Walk filings in filed order (one
       median value per filed date). Drop a value whose ratio to the previous
       kept value is below 1/60, and compare the next filing to that kept
       value rather than to the dropped one. CPRT's FY2012 diluted shares
       were filed as 131428000 and then as 131428; the thousand-fold shrink
       is a source scale error and does not replace the kept value. A ratio
       above 60 is not kept as a jump. It starts a candidate larger scale
       (early filings in thousands, later filings in units). A second filing
       on that scale confirms it; a return to the abandoned scale drops the
       candidate as a glitch. Otherwise the latest kept value is on the
       larger scale.
    c) Basis-jump intervals, from every positive fact on this tag (annual,
       quarterly, YTD, any form). Per period key, build the same kept chain.
       For each consecutive kept pair (p, v_p) -> (n, v_n), r = v_n / v_p.
       The pair is same-basis when 1/1.15 <= r <= 1.15. It is an event
       otherwise (r is already inside 1/60..60). Each restatement pins a
       split to a filing window. A jump
       is {lo, hi, ratio}: the basis changed after filing lo and by filing hi.
       Process events sorted by (abs(log r), n-p) ascending so atomic and
       narrow events come first. For an event (p, n, r), I is the jumps whose
       (lo, hi] intersects (p, n], and C is the jumps in I fully inside
       (p <= lo and hi <= n). Enumerate subsets S of I with C ⊆ S (if |I| > 10,
       the only candidate is S = I) whose product of ratios is within the 1.15
       band of r. Exactly one match: the event is explained by those jumps, and
       each jump in S narrows to lo = max(lo, p), hi = min(hi, n) when lo < hi
       still holds. Several matches: explained, and the window is ambiguous so
       nothing narrows. No match: add a jump (p, n, r / product(C)) unless that
       residual is inside the 1.15 band. A composite restatement (CPRT's FY2023
       10-K moving two prior years by 4 after two separate 2:1 splits) is the
       product of the jumps it spans, so the 4x is not a third split. Then
       narrow with same-basis pairs, repeating until stable for at most 3
       passes: if p <= lo < n < hi, set lo = n (still pre-split at n); if
       lo < p < hi <= n, set hi = p (already post-split at p). For a year whose
       step (b) value was filed on date L, multiply by the product of jump.ratio
       over jumps with L < hi. A value filed on or after hi is already on the
       new basis, so a 10-K that already restated is not multiplied again when
       a later 10-Q restates quarterly comparatives. Split-ratio tags are
       ignored, and there are no per-ticker overrides: a reported ratio that
       never shows up in the share counts is not an adjustment.
    e) Values must stay positive floats; if a tag has no usable data fall
       through to the next tag as today.
    """
    out: dict[int, float] = {}
    for tag in TAG_PREFS["shares"]:
        node = us_gaap.get(tag)
        if not isinstance(node, dict):
            continue
        entries = _unit_entries(node, prefer_shares=True)
        series = _split_adjusted_shares_for_tag(entries)
        for year, val in series.items():
            if year not in out and val > 0:
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


# Explicit 0 on one of these is evidence of no debt. A 0 on a component tag
# is not, by itself: an all-zero partial ladder is treated like no ladder.
_DEBT_TOTAL_TAGS = (
    "LongTermDebt",
    "DebtLongtermAndShorttermCombinedAmount",
    "LongTermDebtAndCapitalLeaseObligations",
    "DebtInstrumentCarryingAmount",
)
_SUPPLEMENTAL_LONG_TAGS = (
    "ConvertibleLongTermNotesPayable",
    "ConvertibleDebtNoncurrent",
    "NotesPayable",
    "SeniorNotes",
    "UnsecuredDebt",
    "UnsecuredLongTermDebt",
    "SecuredDebt",
    "OtherLongTermDebtNoncurrent",
)
_SUPPLEMENTAL_SHORT_TAGS = (
    "OtherShortTermBorrowings",
    "LineOfCredit",
)
# 0.15% of revenue. Interest at or below this stays a zero debt_state;
# strictly above downgrades that year to unknown. See compose_debt.
MATERIAL_INTEREST_PCT_OF_REVENUE = 0.0015
_MATURITY_PREFIX = "LongTermDebtMaturitiesRepaymentsOfPrincipal"


def compose_debt(
    us_gaap: dict[str, Any],
) -> tuple[dict[int, float], dict[int, str]]:
    """Per fiscal year debt total and debt_state from the US-GAAP ladder.

    One annual series per tag (``_series_for_tags`` / ``_pick_annual_by_year``).
    Tags are ``TAG_PREFS["debt_ladder"]``. Same fiscal year only; values are
    never taken from a different year.

    The ladder tags overlap (``SeniorNotes`` ⊂ ``UnsecuredDebt`` ⊂ ``NotesPayable``,
    and likewise for the convertible, secured, and combined-amount concepts).
    Never sum overlapping tags. Only values present that year are used.

    * ``standard`` is the v1 combination, unchanged, and is absent when none of
      its tags are present. Long-term block: if ``LongTermDebt`` is present,
      use it alone (it already includes current maturities). Otherwise
      noncurrent is the first present of ``LongTermDebtNoncurrent`` and
      ``LongTermDebtAndCapitalLeaseObligations``, and current maturities are
      the first present of ``LongTermDebtCurrent`` and
      ``LongTermDebtAndCapitalLeaseObligationsCurrent``. Short-term block:
      ``DebtCurrent`` already includes current maturities and short borrowings,
      so it replaces both — except when ``LongTermDebt`` was used, because
      ``DebtCurrent`` overlaps those current maturities. Then add
      ``ShortTermBorrowings`` if present, else ``CommercialPaper`` (the former
      already includes commercial paper; never add both). So when
      ``LongTermDebt`` is present, standard = LongTermDebt + (ShortTermBorrowings
      or CommercialPaper). Otherwise standard = noncurrent + (DebtCurrent if
      present, else current maturities + (ShortTermBorrowings or CommercialPaper)).
    * ``supplemental`` is the max of the values present among
      ``ConvertibleLongTermNotesPayable``, ``ConvertibleDebtNoncurrent``,
      ``NotesPayable``, ``SeniorNotes``, ``UnsecuredDebt``,
      ``UnsecuredLongTermDebt``, ``SecuredDebt``, ``OtherLongTermDebtNoncurrent``,
      and ``SecuredDebt + UnsecuredDebt`` when both are present, plus the max
      of the values present among ``OtherShortTermBorrowings`` and
      ``LineOfCredit``. Each of those two max terms is included only when at
      least one of its inputs is present. ``supplemental`` is absent when
      neither term is present.
    * ``total`` is the max of the candidates present among
      ``DebtLongtermAndShorttermCombinedAmount``, ``DebtInstrumentCarryingAmount``,
      ``standard``, and ``supplemental``. Taking the max of alternative
      estimates avoids double counting. The result can be a lower bound when
      the filed components are fragmentary (a notes tag may omit other
      borrowings that were not tagged).
    * If no tag from the full ladder is present that year, ``total`` is None
      and that year is omitted from the totals map (debt is None at the
      statement layer).

    ``debt_state`` is ``"positive"`` when total > 0. It is ``"zero"`` only with
    evidence: (a) total == 0 and at least one total tag is explicitly 0 that
    year (``LongTermDebt``, ``DebtLongtermAndShorttermCombinedAmount``,
    ``LongTermDebtAndCapitalLeaseObligations``, ``DebtInstrumentCarryingAmount``);
    or (b) no ladder tag is present that year but us-gaap ``Liabilities`` has
    an annual value that year; or (c) ladder tags are present but every present
    ladder value is 0 and none of those present-zero tags is a total tag. A
    partial zero counts no more and no less than the tag being absent, so (c)
    uses the same state as the no-ladder path: ``"zero"`` when ``Liabilities``
    is reported that FY, otherwise ``"unknown"``. ``total`` stays 0.0 (debt is
    0 on the statement). Otherwise ``"unknown"``. Years with no ladder tag and
    no ``Liabilities`` value are omitted from the state map (callers treat a
    missing year as unknown). A year on path (c) stays in the state map even
    when ``Liabilities`` is absent.

    Two cross-checks downgrade a would-be ``"zero"`` to ``"unknown"``. They
    never change ``"positive"`` or an already ``"unknown"`` year, and they
    never add to the debt total.

    Interest materiality. Per FY, interest is the max of the absolute annual
    values present among ``InterestExpense``, ``InterestExpenseDebt``,
    ``InterestExpenseNonoperating``, and ``InterestPaidNet``
    (``TAG_PREFS["debt_interest"]``). Also include
    ``abs(InterestIncomeExpenseNet)`` when that tag
    (``TAG_PREFS["debt_interest_net"]``) is negative — net interest expense.
    A positive ``InterestIncomeExpenseNet`` is net interest income and is
    ignored. Revenue is the same tag ladder the statements use
    (``_series_for_tags(us_gaap, TAG_PREFS["revenue"])``) for that FY. When
    revenue is present and > 0, interest strictly greater than
    ``MATERIAL_INTEREST_PCT_OF_REVENUE * revenue`` (0.0015, 0.15%) downgrades
    ``"zero"`` to ``"unknown"``; interest at or below the threshold stays
    ``"zero"``. When revenue is missing or <= 0, be conservative: any
    interest > 0 downgrades to ``"unknown"``.

    Hard maturity evidence, with no threshold. If any us-gaap tag whose name
    starts with ``LongTermDebtMaturitiesRepaymentsOfPrincipal``
    (``NextTwelveMonths``, ``InYearTwo`` through ``InYearFive``,
    ``AfterYearFive``, ``RemainderOfFiscalYear``, and the rest of that
    prefix) has an annual value > 0 in that FY, a would-be ``"zero"`` becomes
    ``"unknown"``. Those amounts are not added to the debt total.
    """
    ladder = TAG_PREFS["debt_ladder"]
    series = {tag: _series_for_tags(us_gaap, [tag]) for tag in ladder}
    liabilities = _series_for_tags(us_gaap, ["Liabilities"])
    interest = {
        tag: _series_for_tags(us_gaap, [tag]) for tag in TAG_PREFS["debt_interest"]
    }
    interest_net = _series_for_tags(us_gaap, TAG_PREFS["debt_interest_net"])
    revenue = _series_for_tags(us_gaap, TAG_PREFS["revenue"])
    maturity = {
        name: _pick_annual_by_year(_unit_entries(node))
        for name, node in us_gaap.items()
        if isinstance(name, str)
        and name.startswith(_MATURITY_PREFIX)
        and isinstance(node, dict)
    }

    def _has(tag: str, year: int) -> bool:
        return year in series.get(tag, {})

    def _first(year: int, tags: tuple[str, ...] | list[str]) -> float | None:
        for tag in tags:
            if _has(tag, year):
                return series[tag][year]
        return None

    def _standard(year: int) -> float | None:
        parts: list[float] = []
        if _has("LongTermDebt", year):
            parts.append(series["LongTermDebt"][year])
            short = _first(year, ("ShortTermBorrowings", "CommercialPaper"))
            if short is not None:
                parts.append(short)
        else:
            noncurrent = _first(
                year,
                (
                    "LongTermDebtNoncurrent",
                    "LongTermDebtAndCapitalLeaseObligations",
                ),
            )
            if noncurrent is not None:
                parts.append(noncurrent)
            if _has("DebtCurrent", year):
                parts.append(series["DebtCurrent"][year])
            else:
                current_mat = _first(
                    year,
                    (
                        "LongTermDebtCurrent",
                        "LongTermDebtAndCapitalLeaseObligationsCurrent",
                    ),
                )
                if current_mat is not None:
                    parts.append(current_mat)
                short = _first(year, ("ShortTermBorrowings", "CommercialPaper"))
                if short is not None:
                    parts.append(short)
        if not parts:
            return None
        return sum(parts)

    def _supplemental(year: int) -> float | None:
        long_vals = [
            series[tag][year] for tag in _SUPPLEMENTAL_LONG_TAGS if _has(tag, year)
        ]
        if _has("SecuredDebt", year) and _has("UnsecuredDebt", year):
            long_vals.append(series["SecuredDebt"][year] + series["UnsecuredDebt"][year])
        short_vals = [
            series[tag][year] for tag in _SUPPLEMENTAL_SHORT_TAGS if _has(tag, year)
        ]
        parts: list[float] = []
        if long_vals:
            parts.append(max(long_vals))
        if short_vals:
            parts.append(max(short_vals))
        if not parts:
            return None
        return sum(parts)

    def _interest_amount(year: int) -> float:
        present: list[float] = []
        for by_year in interest.values():
            if year in by_year:
                present.append(abs(by_year[year]))
        net = interest_net.get(year)
        if net is not None and net < 0:
            present.append(abs(net))
        if not present:
            return 0.0
        return max(present)

    def _interest_material(year: int) -> bool:
        amount = _interest_amount(year)
        if amount <= 0:
            return False
        rev = revenue.get(year)
        if rev is None or rev <= 0:
            return True
        return amount > MATERIAL_INTEREST_PCT_OF_REVENUE * rev

    def _maturity_positive(year: int) -> bool:
        return any(by_year.get(year, 0.0) > 0 for by_year in maturity.values())

    years = set(liabilities)
    for by_year in series.values():
        years |= set(by_year)

    totals: dict[int, float] = {}
    states: dict[int, str] = {}
    for year in years:
        ladder_present = any(_has(tag, year) for tag in ladder)
        if not ladder_present:
            state = "zero" if year in liabilities else "unknown"
        else:
            candidates: list[float] = []
            for tag in (
                "DebtLongtermAndShorttermCombinedAmount",
                "DebtInstrumentCarryingAmount",
            ):
                if _has(tag, year):
                    candidates.append(series[tag][year])
            standard = _standard(year)
            if standard is not None:
                candidates.append(standard)
            supplemental = _supplemental(year)
            if supplemental is not None:
                candidates.append(supplemental)
            if not candidates:
                state = "unknown"
            else:
                total = max(candidates)
                totals[year] = total
                present_tags = [tag for tag in ladder if _has(tag, year)]
                present_zero = [
                    tag
                    for tag in present_tags
                    if series[tag][year] == 0
                ]
                all_present_zero = len(present_zero) == len(present_tags)
                zero_on_total = any(tag in _DEBT_TOTAL_TAGS for tag in present_zero)
                if total > 0:
                    state = "positive"
                elif all_present_zero and not zero_on_total:
                    # Partial zeros are the same as a missing ladder.
                    state = "zero" if year in liabilities else "unknown"
                elif total == 0 and zero_on_total:
                    state = "zero"
                else:
                    state = "unknown"
        if state == "zero" and (_interest_material(year) or _maturity_positive(year)):
            state = "unknown"
        states[year] = state
    return totals, states


def map_companyfacts_to_statements(
    companyfacts: dict[str, Any],
) -> tuple[list[int], dict[int, dict[str, float | str | None]]]:
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
    shares = split_adjusted_shares(us_gaap)
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

    debt, debt_states = compose_debt(us_gaap)

    da = _abs_series(_series_for_tags(us_gaap, TAG_PREFS["da"]))
    ocf = _resolve_ocf(us_gaap, net_income, da)
    capex = _compose_capex(us_gaap)
    owner_earnings = _owner_earnings(ocf, capex, da)

    all_years = sorted(
        set(revenue)
        | set(net_income)
        | set(equity)
        | set(assets)
        | set(liabilities)
        | set(debt)
        | set(owner_earnings)
        | set(dividends)
        | set(shares)
        | set(cash),
        reverse=True,
    )
    # Prefer years that have revenue or net_income (core 10-K presence)
    core = [y for y in all_years if y in revenue or y in net_income]
    years = core or all_years

    field_series: dict[str, dict[int, float]] = {
        "revenue": revenue,
        "net_income": net_income,
        "equity": equity,
        "assets": assets,
        "total_liabilities": liabilities,
        "debt": debt,
        "owner_earnings": owner_earnings,
        "dividends": dividends,
        "shares": shares,
        "cash": cash,
    }
    statements: dict[int, dict[str, float | str | None]] = {}
    for y in years:
        row: dict[str, float | str | None] = {
            k: (series[y] if y in series else None) for k, series in field_series.items()
        }
        # Extra key is not a FIELDS member; compute_year ignores it.
        row["debt_state"] = debt_states.get(y, "unknown")
        statements[y] = row
    return years, statements


def entity_name(companyfacts: dict[str, Any]) -> str | None:
    raw = companyfacts.get("entityName")
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name or None


def statements_for_ticker(
    ticker: str,
    *,
    meta: dict[str, Any] | None = None,
) -> tuple[list[int], dict[int, dict[str, float | str | None]], str, str | None]:
    """Resolve ticker → companyfacts → statements.

    Returns (years, statements, cik, company_name).
    Optional ``meta`` is forwarded to ``fetch_companyfacts`` for cache_source.
    """
    cik = resolve_cik(ticker)
    payload = fetch_companyfacts(cik, meta=meta)
    years, statements = map_companyfacts_to_statements(payload)
    if not years:
        raise ValueError(f"unknown ticker / no annual us-gaap facts for {ticker}")
    return years, statements, cik, entity_name(payload)
