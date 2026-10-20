"""Peers for non-S&P tickers from all SEC filers by SIC (#54).

Precomputed monthly into ``data/sic_peers.json``; analyze reads only that
file (no SEC request at page load).

Build (``uv run python -m app.sic_peers [--dry-run]``):

1. Universe: every CIK in SEC ``company_tickers_exchange.json``. The first
   ticker listed for a CIK is its primary ticker; other tickers (share
   classes, preferreds) map to the same company.
2. SIC: each CIK's ``sic`` / ``sicDescription`` from the EDGAR submissions
   JSON (rate-gated like the rest of the EDGAR client).
3. Latest annual revenue: SEC XBRL frames (one request per tag and calendar
   year, built from the same companyfacts data analyze uses) for the
   revenue tags in ``REVENUE_TAGS``, years ``CY{Y}`` newest first. A
   company's revenue is the largest of those tags in its newest year with
   any value.
4. Peers: other companies with the same 4-digit SIC whose latest revenue is
   at least ``MIN_REVENUE`` ($10M; no revenue or below it is dropped),
   by revenue (high to low), top ``MAX_PEERS``. With fewer than
   ``MIN_PEERS`` same-SIC peers, widen to the 3-digit SIC group (the whole
   group by revenue, top ``MAX_PEERS``). No SIC or no peers
   with revenue: no peers, with the reason.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sic_peers.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY{year}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
)
MAX_PEERS = 10
MIN_PEERS = 5  # fewer same-SIC peers clearing the floor widens to the 3-digit group
MIN_REVENUE = (
    10_000_000  # USD; peer candidates below this (or with no revenue) are dropped
)
MIN_COMPANIES = 5000  # refuse to write a suspiciously small universe
# SEC submissions + XBRL frames for the monthly rebuild. GitHub Actions
# caches this directory for the calendar month (SIC_PEERS_SEC_CACHE overrides).
_SEC_CACHE_ENV = "SIC_PEERS_SEC_CACHE"
SEC_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "sic_peers_sec"


def sec_cache_dir() -> Path:
    raw = os.environ.get(_SEC_CACHE_ENV, "").strip()
    return Path(raw) if raw else SEC_CACHE_DIR


def sec_cache_rel(url: str) -> str | None:
    """Relative cache path for a submissions or frames URL, else None."""
    name = url.rsplit("/", 1)[-1]
    if "/submissions/CIK" in url and name.startswith("CIK") and name.endswith(".json"):
        cik = name[3:-5]
        if cik.isdigit() and len(cik) == 10:
            return f"submissions/{name}"
    marker = "/frames/us-gaap/"
    if marker in url and "/USD/CY" in url and url.endswith(".json"):
        tag, _, year_part = url.split(marker, 1)[1].partition("/USD/CY")
        year = year_part[: -len(".json")]
        if tag and "/" not in tag and year.isdigit() and len(year) == 4:
            return f"frames/{tag}-CY{year}.json"
    return None


def disk_cached_fetch(fetch_json: Any, cache_dir: Path) -> Any:
    """Return fetch_json wrapped so submissions and frames are read/written on disk.

    A hit does not call fetch_json (the SEC rate gate and User-Agent stay on
    the miss path only). Other URLs always go to the network.
    """

    def fetch(url: str) -> Any:
        rel = sec_cache_rel(url)
        if rel is None:
            return fetch_json(url)
        path = cache_dir / rel
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = None
            if isinstance(cached, dict):
                return cached
        data = fetch_json(url)
        if isinstance(data, dict):
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        return data

    return fetch


# --- build ----------------------------------------------------------------


def latest_revenue(
    frames: dict[int, dict[str, list[dict[str, Any]]]],
) -> dict[int, tuple[float, int, str]]:
    """{cik: (revenue, year, period end)} from frames[year][tag] rows."""
    out: dict[int, tuple[float, int, str]] = {}
    for year in sorted(frames, reverse=True):
        best: dict[int, tuple[float, int, str]] = {}
        for rows in frames[year].values():
            for row in rows:
                try:
                    cik, val = int(row["cik"]), float(row["val"])
                except (KeyError, TypeError, ValueError):
                    continue
                if val <= 0 or cik in out:
                    continue
                if cik not in best or val > best[cik][0]:
                    best[cik] = (val, year, str(row.get("end") or ""))
        out.update(best)
    return out


def rank_peers(companies: dict[str, dict[str, Any]]) -> None:
    """Fill ``p`` (peer CIKs), ``b`` (basis) and ``why`` on each company in place."""
    by_sic: dict[int, list[str]] = {}
    for cik, co in companies.items():
        if co.get("s") is not None and float(co.get("r") or 0) >= MIN_REVENUE:
            by_sic.setdefault(int(co["s"]), []).append(cik)
    for ciks in by_sic.values():
        ciks.sort(
            key=lambda c: (-float(companies[c]["r"]), companies[c].get("t") or "")
        )
    by_sic3: dict[int, list[str]] = {}
    for sic, ciks in by_sic.items():
        by_sic3.setdefault(sic // 10, []).extend(ciks)
    for ciks in by_sic3.values():
        ciks.sort(
            key=lambda c: (-float(companies[c]["r"]), companies[c].get("t") or "")
        )
    for cik, co in companies.items():
        co.pop("p", None)
        co.pop("b", None)
        co.pop("why", None)
        sic = co.get("s")
        if sic is None:
            co["why"] = "no SIC code in SEC submissions"
            continue
        same = [c for c in by_sic.get(int(sic), []) if c != cik]
        if len(same) >= MIN_PEERS:
            co["p"], co["b"] = same[:MAX_PEERS], "sic"
            continue
        group = [c for c in by_sic3.get(int(sic) // 10, []) if c != cik]
        if not group:
            co["why"] = (
                "no other SEC filer in this SIC group reports annual revenue of at least $10M"
            )
            continue
        co["p"], co["b"] = (
            group[:MAX_PEERS],
            "sic3" if len(group) > len(same) else "sic",
        )


def build(
    *, fetch_json: Any, years: tuple[int, ...] | None = None, log: Any = None
) -> dict[str, Any]:
    today = dt.date.today()
    years = years or (today.year, today.year - 1, today.year - 2)
    tick = fetch_json(TICKERS_URL)
    fields = tick["fields"]
    i_cik, i_name, i_t = (
        fields.index("cik"),
        fields.index("name"),
        fields.index("ticker"),
    )
    companies: dict[str, dict[str, Any]] = {}
    tickers: dict[str, str] = {}
    for row in tick["data"]:
        cik, ticker = str(int(row[i_cik])), str(row[i_t] or "").upper().strip()
        if not ticker:
            continue
        tickers.setdefault(ticker, cik)
        companies.setdefault(cik, {"t": ticker, "n": row[i_name]})
    frames: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for year in years:
        for tag in REVENUE_TAGS:
            try:
                frames.setdefault(year, {})[tag] = (
                    fetch_json(FRAMES_URL.format(tag=tag, year=year)).get("data") or []
                )
            except Exception as exc:  # noqa: BLE001 - a missing frame just has no rows
                if log:
                    log(f"frame {tag} CY{year}: {exc}")
    revenue = latest_revenue(frames)
    sics: dict[str, str] = {}
    for n, (cik, co) in enumerate(companies.items(), 1):
        if rev := revenue.get(int(cik)):
            co["r"], co["y"], co["e"] = rev[0], rev[1], rev[2]
        try:
            sub = fetch_json(SUBMISSIONS_URL.format(cik=int(cik)))
            sic = int(str(sub.get("sic") or "").strip())
        except Exception:  # noqa: BLE001 - no SIC: company gets no peers, with a reason
            sic = None
        if sic:
            co["s"] = sic
            desc = (sub.get("sicDescription") or "").strip()
            if desc:
                sics[str(sic)] = desc
        if log and n % 500 == 0:
            log(f"sic {n}/{len(companies)}")
    rank_peers(companies)
    return {
        "note": "Non-S&P peers by SEC SIC (#54): same 4-digit SIC ranked by latest annual revenue, "
        "revenue >= $10M, top 10; fewer than 5 widens to the 3-digit SIC group. Generated by `python -m app.sic_peers`; do not hand-edit.",
        "generated": today.isoformat(),
        "revenue_years": list(years),
        "sics": dict(sorted(sics.items())),
        "tickers": dict(sorted(tickers.items())),
        "companies": companies,
    }


def _content(d: dict[str, Any]) -> tuple[Any, ...]:
    return (d.get("tickers"), d.get("companies"), d.get("sics"))


def diff_summary(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    oc, nc = old.get("companies") or {}, new.get("companies") or {}
    added = sorted(set(nc) - set(oc))
    removed = sorted(set(oc) - set(nc))
    peers_changed = sum(
        1 for c in set(oc) & set(nc) if oc[c].get("p") != nc[c].get("p")
    )
    widened = sum(1 for c in nc.values() if c.get("b") == "sic3")
    return [
        f"companies: {len(nc)} (+{len(added)} / -{len(removed)})",
        f"with revenue: {sum(1 for c in nc.values() if c.get('r'))}",
        f"peer candidates (>= $10M): {sum(1 for c in nc.values() if float(c.get('r') or 0) >= MIN_REVENUE)}",
        f"with peers: {sum(1 for c in nc.values() if c.get('p'))}; widened to 3-digit SIC: {widened}",
        f"peer lists changed: {peers_changed}",
    ]


def main(argv: list[str] | None = None) -> int:
    from app import edgar, peer_metrics
    from app.screen import load_universe

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-metrics", action="store_true")
    ap.add_argument("--path", type=Path, default=DATA_PATH)
    ap.add_argument("--metrics-path", type=Path, default=peer_metrics.DATA_PATH)
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        sys.stderr.write(msg + "\n")

    new = build(
        fetch_json=disk_cached_fetch(edgar._http_get_json, sec_cache_dir()),
        log=log,
    )
    if len(new["companies"]) < MIN_COMPANIES:
        raise SystemExit(f"refusing to write: only {len(new['companies'])} companies")
    try:
        old = json.loads(args.path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        old = {}
    sic_changed = _content(old) != _content(new)

    metrics_changed = False
    metrics_n = 0
    if not args.skip_metrics:
        try:
            old_metrics = json.loads(args.metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old_metrics = {}
        if not isinstance(old_metrics, dict):
            old_metrics = {}
        tickers = peer_metrics.targets(new, load_universe())
        new_metrics = peer_metrics.build(tickers, log=log)
        metrics_n = len(new_metrics.get("rows") or {})
        metrics_changed = (old_metrics.get("rows") or {}) != (
            new_metrics.get("rows") or {}
        )
        if metrics_changed and not args.dry_run:
            peer_metrics.write(new_metrics, args.metrics_path)
            peer_metrics.clear_load_cache()
    else:
        try:
            metrics_n = len(
                json.loads(args.metrics_path.read_text(encoding="utf-8")).get("rows") or {}
            )
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            metrics_n = 0

    changed = sic_changed or metrics_changed
    print(f"changed={'true' if changed else 'false'}")
    for line in diff_summary(old, new):
        print(line)
    print(f"metrics_changed={'true' if metrics_changed else 'false'}")
    print(f"metrics rows: {metrics_n}")
    if sic_changed and not args.dry_run:
        args.path.write_text(
            json.dumps(new, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


# --- runtime (analyze) ----------------------------------------------------


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> dict[str, Any]:
    try:
        raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def sic_peers_for(
    ticker: str, data: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Peers block for a non-S&P ticker from the precomputed map, or None."""
    data = load() if data is None else data
    tickers, companies = data.get("tickers") or {}, data.get("companies") or {}
    symbol = ticker.upper().strip()
    cik = (
        tickers.get(symbol)
        or tickers.get(symbol.replace(".", "-"))
        or tickers.get(symbol.replace("-", "."))
    )
    co = companies.get(cik or "")
    if not co:
        return None
    sic = co.get("s")
    desc = (data.get("sics") or {}).get(str(sic)) if sic is not None else None
    peers = [
        {
            "ticker": companies[c]["t"],
            "name": companies[c].get("n"),
            "revenue": companies[c].get("r"),
            "revenue_fy": companies[c].get("y"),
            "sic": companies[c].get("s"),
        }
        for c in co.get("p") or []
        if c in companies
    ]
    basis = co.get("b") or "sic"
    group = desc or (f"SIC {sic}" if sic is not None else "")
    if basis == "sic3" and sic is not None:
        group = f"SIC {int(sic) // 10}x"
    return {
        "basis": basis,
        "group": group,
        "sub_industry": desc or "",
        "fallback": basis == "sic3",
        "total": len(peers),
        "peers": peers,
        "sic": sic,
        "reason": co.get("why"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
