"""Ticker sector/industry: GICS (S&P 500) or SEC SIC (everyone else).

GICS sector + sub-industry come from ``backend/data/sp500_tickers.json``
(Wikipedia List of S&P 500 companies — same source as existing ``sectors``).
Non-S&P names use SEC EDGAR submissions JSON (``sic``, ``sicDescription``),
cached under ``backend/.cache/submissions/``. Fail-soft: never raise to callers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_tickers.json"
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "submissions"
_CACHE_TTL_S = 30 * 24 * 3600

_gics_mem: dict[str, dict[str, str | None]] | None = None
_sic_mem: dict[str, tuple[float, dict[str, Any] | None]] = {}

# SIC major-group (first two digits) → SEC/OSHA Division name.
_SIC_DIVISIONS: list[tuple[int, int, str]] = [
    (1, 9, "Agriculture, Forestry & Fishing"),
    (10, 14, "Mining"),
    (15, 17, "Construction"),
    (20, 39, "Manufacturing"),
    (40, 49, "Transportation, Communications & Utilities"),
    (50, 51, "Wholesale Trade"),
    (52, 59, "Retail Trade"),
    (60, 67, "Finance, Insurance & Real Estate"),
    (70, 89, "Services"),
    (91, 99, "Public Administration"),
]


def sic_division(sic: int | str | None) -> str | None:
    """Map a 4-digit (or shorter) SIC code to its Division name."""
    if sic is None:
        return None
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return None
    if code < 0:
        return None
    major = code if code < 100 else code // 100
    for lo, hi, name in _SIC_DIVISIONS:
        if lo <= major <= hi:
            return name
    return None


# SEC Division D finance range. 6798 is REITs, which GICS puts in Real Estate.
FINANCIAL_SIC_LO = 6000
FINANCIAL_SIC_HI = 6799
REIT_SIC = 6798
OE_BASIS_FINANCIAL = "net income (financial)"
_SIC_PEERS_PATH = Path(__file__).resolve().parent.parent / "data" / "sic_peers.json"
_sp500_symbols_mem: set[str] | None = None
_peer_sic_mem: dict[str, int] | None = None


def sp500_symbols() -> set[str]:
    """Tickers listed in ``sp500_tickers.json``, including dot and hyphen forms."""
    global _sp500_symbols_mem
    if _sp500_symbols_mem is not None:
        return set(_sp500_symbols_mem)
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    tickers = raw.get("tickers") if isinstance(raw, dict) else None
    out: set[str] = set()
    if isinstance(tickers, list):
        for item in tickers:
            if not isinstance(item, str):
                continue
            symbol = item.upper().strip()
            if not symbol:
                continue
            out.add(symbol)
            alt = symbol.replace(".", "-") if "." in symbol else symbol.replace("-", ".")
            if alt != symbol:
                out.add(alt)
    _sp500_symbols_mem = out
    return set(out)


def _peer_sic_by_ticker() -> dict[str, int]:
    """Non-S&P ticker → 4-digit SIC from the committed ``sic_peers.json`` map."""
    global _peer_sic_mem
    if _peer_sic_mem is not None:
        return _peer_sic_mem
    out: dict[str, int] = {}
    try:
        raw = json.loads(_SIC_PEERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _peer_sic_mem = out
        return out
    if not isinstance(raw, dict):
        _peer_sic_mem = out
        return out
    tickers = raw.get("tickers") or {}
    companies = raw.get("companies") or {}
    if not isinstance(tickers, dict) or not isinstance(companies, dict):
        _peer_sic_mem = out
        return out
    for ticker, cik in tickers.items():
        if not isinstance(ticker, str):
            continue
        co = companies.get(cik) if isinstance(cik, str) else None
        if not isinstance(co, dict) or co.get("s") is None:
            continue
        try:
            out[ticker.upper().strip()] = int(co["s"])
        except (TypeError, ValueError):
            continue
    _peer_sic_mem = out
    return out


def is_financial_company(ticker: str, sic: int | None = None) -> bool:
    """GICS Financials, or a non-S&P filer in SEC SIC 6000–6799 except REIT 6798.

    A name listed in ``sp500_tickers.json`` uses only its GICS sector. SIC
    never overrides that. Everyone else uses the SIC argument, then the
    committed SIC peer map.
    """
    symbol = ticker.upper().strip()
    if not symbol:
        return False
    if symbol in sp500_symbols():
        hit = load_gics().get(symbol)
        return bool(hit and hit.get("sector") == "Financials")
    code = sic
    if code is None:
        code = _peer_sic_by_ticker().get(symbol)
        if code is None:
            alt = symbol.replace(".", "-") if "." in symbol else symbol.replace("-", ".")
            code = _peer_sic_by_ticker().get(alt)
    if code is None:
        return False
    try:
        parsed = int(code)
    except (TypeError, ValueError):
        return False
    return FINANCIAL_SIC_LO <= parsed <= FINANCIAL_SIC_HI and parsed != REIT_SIC


def load_gics(path: Path | None = None) -> dict[str, dict[str, str | None]]:
    """Ticker → {sector, sub_industry} from ``sp500_tickers.json``."""
    global _gics_mem
    if path is None and _gics_mem is not None:
        return dict(_gics_mem)
    raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    sectors = raw.get("sectors") if isinstance(raw, dict) else None
    subs = raw.get("sub_industries") if isinstance(raw, dict) else None
    if not isinstance(sectors, dict):
        sectors = {}
    if not isinstance(subs, dict):
        subs = {}
    out: dict[str, dict[str, str | None]] = {}
    for key, sector in sectors.items():
        if not isinstance(key, str) or not isinstance(sector, str):
            continue
        symbol = key.upper().strip()
        if not symbol:
            continue
        sub = subs.get(key)
        if not isinstance(sub, str) or not sub.strip():
            sub = None
        else:
            sub = sub.strip()
        out[symbol] = {"sector": sector, "sub_industry": sub}
    # Also index BRK.B ↔ BRK-B style
    for symbol, payload in list(out.items()):
        alt = symbol.replace(".", "-") if "." in symbol else symbol.replace("-", ".")
        if alt != symbol and alt not in out:
            out[alt] = payload
    if path is None:
        _gics_mem = out
    return dict(out)


def _sic_cache_path(cik: str) -> Path:
    pad = f"{int(str(cik).lstrip('0') or '0'):010d}"
    return _CACHE_DIR / f"{pad}.json"


def _read_sic_disk(cik: str, *, max_age_s: float | None) -> dict[str, Any] | None:
    path = _sic_cache_path(cik)
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
    if not isinstance(raw, dict) or raw.get("sic") is None:
        return None
    return raw


def _write_sic_disk(cik: str, payload: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _sic_cache_path(cik)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def fetch_sic(cik: str) -> dict[str, Any] | None:
    """Return {sic: int, sic_description: str} for a CIK, or None."""
    key = str(cik).lstrip("0") or "0"
    now = time.time()
    hit = _sic_mem.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return dict(hit[1]) if hit[1] else None

    fresh = _read_sic_disk(key, max_age_s=_CACHE_TTL_S)
    if fresh is not None:
        result = {
            "sic": int(fresh["sic"]),
            "sic_description": str(fresh.get("sic_description") or "") or None,
        }
        _sic_mem[key] = (now, result)
        return dict(result)

    try:
        from app import edgar

        pad = f"{int(key):010d}"
        url = f"https://data.sec.gov/submissions/CIK{pad}.json"
        body = edgar._http_get_json(url)
        sic_raw = body.get("sic")
        if sic_raw is None:
            raise ValueError("no sic")
        sic = int(str(sic_raw).strip())
        desc = body.get("sicDescription")
        desc_s = str(desc).strip() if desc else None
        result = {"sic": sic, "sic_description": desc_s or None}
        _write_sic_disk(
            key,
            {
                "sic": sic,
                "sic_description": desc_s,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        _sic_mem[key] = (time.time(), result)
        return dict(result)
    except Exception:  # noqa: BLE001 - fail-soft: serve stale SIC cache on any fetch error
        stale = _read_sic_disk(key, max_age_s=None)
        if stale is not None:
            result = {
                "sic": int(stale["sic"]),
                "sic_description": str(stale.get("sic_description") or "") or None,
            }
            _sic_mem[key] = (time.time(), result)
            return dict(result)
        _sic_mem[key] = (time.time(), None)
        return None


def _ticker_candidates(ticker: str) -> list[str]:
    symbol = ticker.upper().strip()
    if not symbol:
        return []
    out = [symbol]
    alt = symbol.replace(".", "-") if "." in symbol else symbol.replace("-", ".")
    if alt != symbol:
        out.append(alt)
    return out


def classify(ticker: str, cik: str | None = None) -> dict[str, Any] | None:
    """Return classification block for analyze, or None."""
    try:
        gics = load_gics()
        for symbol in _ticker_candidates(ticker):
            hit = gics.get(symbol)
            if hit and hit.get("sector"):
                sector = str(hit["sector"])
                industry = hit.get("sub_industry")
                return {
                    "scheme": "gics",
                    "sector": sector,
                    "industry": industry,
                    "sic": None,
                    "sic_description": None,
                    # Sector pages live in the site nav (#65). The subtitle is text.
                    "link": None,
                }

        resolved = cik
        if not resolved:
            from app import edgar

            resolved = edgar.resolve_cik(ticker)
        sic_payload = fetch_sic(resolved) if resolved else None
        if not sic_payload:
            return None
        sic = int(sic_payload["sic"])
        desc = sic_payload.get("sic_description")
        division = sic_division(sic)
        return {
            "scheme": "sic",
            "sector": division,
            "industry": desc,
            "sic": sic,
            "sic_description": desc,
            # Non-S&P names get no comparison link (#43: S&P-only tables,
            # no SIC→GICS mapping).
            "link": None,
        }
    except Exception:  # noqa: BLE001 - classification is optional page decoration
        return None
