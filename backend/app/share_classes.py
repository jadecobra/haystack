"""Traded-class equivalent share counts for multi-class issuers (#53).

SEC companyfacts drops dimensional XBRL facts, so for issuers that tag share
counts only per class of stock (StatementClassOfStockAxis) there is no
undimensioned share count and OE/share is blank. The per-class facts are in
each 10-K's own XBRL instance. ``refresh_counts`` reads them from SEC EDGAR
(submissions JSON -> 10-K accession -> filing index -> instance XML) and stores
the extracted numbers, with accession provenance, in
``data/share_class_counts.json``. Analyze and the screen read only that seed;
they never fetch filings at request time.

Per fiscal year (labelled by the 10-K's DocumentPeriodEndDate), shares in
the traded class's terms are:

* diluted weighted-average shares of the traded class, when the filing tags
  them, plus other classes' cover-page counts x ratio unless the map says the
  filer's diluted count already includes their conversion; else
* the sum of dei cover-page counts per class x ratio to the traded class.

Ratios and evidence (accession + section) live in ``data/share_classes.json``.
A class without a ratio leaves the year blank with a reason.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAP_PATH = DATA_DIR / "share_classes.json"
COUNTS_PATH = DATA_DIR / "share_class_counts.json"

_XBRLI = "{http://www.xbrl.org/2003/instance}"
_XBRLDI = "{http://xbrl.org/2006/xbrldi}"
_CLASS_AXIS = "StatementClassOfStockAxis"
_FLOW_TAGS = {
    "WeightedAverageNumberOfDilutedSharesOutstanding": "diluted",
    "WeightedAverageNumberOfSharesOutstandingBasic": "basic",
    "EarningsPerShareBasic": "eps_basic",
    "EarningsPerShareDiluted": "eps_diluted",
}


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_map(path: Path | None = None) -> dict[str, Any]:
    return _load(path or MAP_PATH).get("map") or {}


def load_counts(path: Path | None = None) -> dict[str, Any]:
    return _load(path or COUNTS_PATH).get("filings") or {}


def _key(cik: str | int) -> str:
    return str(int(str(cik)))


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


# --- extraction (refresh time only) -------------------------------------


def parse_instance(xml_bytes: bytes) -> dict[str, Any]:
    """Per-class share facts from one 10-K XBRL instance.

    Keeps dei:EntityCommonStockSharesOutstanding per class (cover page) and,
    for the fiscal-year duration ending on DocumentPeriodEndDate, per-class
    weighted-average shares and EPS. Facts with any non-class dimension are
    ignored. An undimensioned cover count is stored under "" (single class).
    """
    root = ET.fromstring(xml_bytes)
    contexts: dict[str, tuple[str | None, str | None, str | None, bool]] = {}
    for ctx in root.iter(_XBRLI + "context"):
        period = ctx.find(_XBRLI + "period")
        if period is None:
            continue
        start = period.findtext(_XBRLI + "startDate")
        end = period.findtext(_XBRLI + "endDate") or period.findtext(_XBRLI + "instant")
        members = [(m.get("dimension") or "", (m.text or "").strip()) for m in ctx.iter(_XBRLDI + "explicitMember")]
        typed = list(ctx.iter(_XBRLDI + "typedMember"))
        cls = [v for d, v in members if d.endswith(_CLASS_AXIS)]
        other = typed or [d for d, _ in members if not d.endswith(_CLASS_AXIS)]
        contexts[ctx.get("id") or ""] = (start, end, cls[0] if cls else "", bool(other) or len(cls) > 1)
    period_end: str | None = None
    for el in root:
        if el.tag.endswith("}DocumentPeriodEndDate") and el.text:
            period_end = el.text.strip()
            break
    pe = _iso(period_end)
    out: dict[str, Any] = {"period_end": period_end, "cover": {}, "cover_date": None}
    for name in _FLOW_TAGS.values():
        out[name] = {}
    for el in root:
        local = el.tag.rsplit("}", 1)[-1]
        if local != "EntityCommonStockSharesOutstanding" and local not in _FLOW_TAGS:
            continue
        ctx = contexts.get(el.get("contextRef") or "")
        if ctx is None or ctx[3] or el.text is None:
            continue
        start, end, cls, _ = ctx
        try:
            val = float(el.text.strip())
        except ValueError:
            continue
        if local == "EntityCommonStockSharesOutstanding":
            out["cover"][cls] = val
            out["cover_date"] = end
            continue
        s, e = _iso(start), _iso(end)
        if s is None or e is None or pe is None or e != pe or not 300 <= (e - s).days <= 380:
            continue
        out[_FLOW_TAGS[local]][cls] = val
    return out


def _sec_get(url: str) -> Any:
    import httpx

    from app import edgar

    edgar._rate_gate()
    headers = {"User-Agent": edgar.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    with httpx.Client(timeout=120.0, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp


def _instance_name(cik: str, accn_nodash: str) -> str | None:
    idx = _sec_get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/index.json").json()
    names = [i.get("name", "") for i in (idx.get("directory") or {}).get("item") or []]
    xmls = [
        n for n in names
        if n.endswith(".xml") and n != "FilingSummary.xml"
        and not any(n.endswith(s) for s in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml"))
    ]
    htm = [n for n in xmls if n.endswith("_htm.xml")]
    return (htm or xmls or [None])[0]


def refresh_counts(path: Path | None = None, *, limit: int = 12) -> dict[str, Any]:
    """Fetch per-class counts for every mapped issuer's 10-Ks not yet in the seed."""
    path = path or COUNTS_PATH
    seed = _load(path)
    filings: dict[str, Any] = seed.get("filings") or {}
    added: list[str] = []
    for cik, entry in load_map().items():
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
        pages = [(sub.get("filings") or {}).get("recent") or {}]
        rows: list[tuple[str, str]] = []
        older = [f.get("name") for f in (sub.get("filings") or {}).get("files") or [] if f.get("name")]
        while pages:
            page = pages.pop(0)
            rows += [
                (page["accessionNumber"][i], page["form"][i])
                for i in range(len(page.get("form") or []))
                if page["form"][i] in ("10-K", "10-K/A", "10-KT")
            ]
            if len(rows) < limit and older:
                pages.append(_sec_get(f"https://data.sec.gov/submissions/{older.pop(0)}").json())
        rows = rows[:limit]
        have = filings.setdefault(cik, {})
        for accn, form in rows:
            if accn in have:
                continue
            nodash = accn.replace("-", "")
            name = _instance_name(cik, nodash)
            if not name:
                continue
            facts = parse_instance(_sec_get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{name}").content)
            have[accn] = {"form": form, "instance": name, **facts}
            added.append(f"{entry.get('ticker')}:{accn}")
    payload = {
        "note": "Per-class share facts extracted from each 10-K XBRL instance (#53). "
        "Generated by `longmuch share-classes-refresh`; do not hand-edit.",
        "filings": filings,
    }
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"added": added}


# --- application (analyze / screen) ------------------------------------


def _ratio(entry: dict[str, Any], cls: str, filing: dict[str, Any]) -> float | None:
    spec = (entry.get("ratios") or {}).get(cls)
    if isinstance(spec, dict):
        spec = spec.get("ratio")
    if isinstance(spec, (int, float)):
        return float(spec)
    if spec == "eps_basic_ratio":
        eps = filing.get("eps_basic") or {}
        num, den = eps.get(cls), eps.get(entry.get("traded_class"))
        if num and den:
            return float(num) / float(den)
    return None


def equivalent_shares(entry: dict[str, Any], filing: dict[str, Any]) -> tuple[float | None, str]:
    """(traded-class equivalent shares, method or blank reason) for one 10-K.

    Other classes count at their per-class weighted-average basic shares
    when the filing tags them, else their cover-page count, times the ratio.
    ``diluted_includes_other_classes``: true (filer's diluted traded-class
    count is as-converted), false, or "auto" (as-converted only when that
    count already covers basic traded + converted other classes, i.e. not an
    anti-dilutive loss year).
    """
    traded = entry.get("traded_class") or ""
    ignore = set(entry.get("ignore_classes") or [])
    cover = {k: v for k, v in (filing.get("cover") or {}).items() if v and k not in ignore}
    diluted = (filing.get("diluted") or {}).get(traded)
    # Weighted per-class basic counts only pair with a weighted diluted count;
    # the cover-page path stays all point-in-time cover counts.
    basic = (filing.get("basic") or {}) if diluted else {}
    others: dict[str, float] = {}
    for cls in set(cover) | set(basic):
        if cls in ("", traded) or cls in ignore or cls not in (entry.get("ratios") or {}) and cls not in cover:
            continue
        count = basic.get(cls) or cover.get(cls)
        if count:
            others[cls] = float(count)
    converted = 0.0
    missing: str | None = None
    for cls, count in others.items():
        r = _ratio(entry, cls, filing)
        if r is None:
            missing = missing or cls
            continue
        converted += count * r
    mode = entry.get("diluted_includes_other_classes")
    if diluted:
        diluted = float(diluted)
        if mode == "auto":
            base = float((filing.get("basic") or {}).get(traded) or 0.0)
            mode = missing is None and diluted >= base + converted
        if mode is True:
            return diluted, "diluted traded class (as-converted by filer)"
        if missing:
            return None, f"no conversion ratio for {missing}: {_reason(entry, missing)}"
        return diluted + converted, (
            "diluted traded class + other classes x ratio" if others else "diluted traded class"
        )
    if missing:
        return None, f"no conversion ratio for {missing}: {_reason(entry, missing)}"
    single = cover.get(traded) or cover.get("")
    if not single and not others:
        return None, "no per-class share counts in the 10-K XBRL"
    return float(single or 0.0) + converted, "cover-page counts x ratio"


def _reason(entry: dict[str, Any], cls: str) -> str:
    spec = (entry.get("ratios") or {}).get(cls)
    if isinstance(spec, dict) and spec.get("reason"):
        return str(spec["reason"])
    return "class not in data/share_classes.json"


def shares_by_year(cik: str | int) -> dict[int, tuple[float | None, str, str]]:
    """{fiscal year: (shares, method or reason, accession)} for a mapped issuer."""
    from app.edgar import fiscal_year_label

    key = _key(cik)
    entry = load_map().get(key)
    if not entry:
        return {}
    out: dict[int, tuple[float | None, str, str]] = {}
    filings = load_counts().get(key) or {}
    # Older accessions first so an amendment/later filing for the same year wins.
    for accn in sorted(filings, key=lambda a: str(filings[a].get("period_end") or "")):
        filing = filings[accn]
        end = _iso(filing.get("period_end"))
        if end is None or str(filing.get("form")) == "10-KT":
            continue
        shares, how = equivalent_shares(entry, filing)
        out[fiscal_year_label(end)] = (shares, how, accn)
    return out


def apply(cik: str | int, statements: dict[int, dict[str, Any]]) -> None:
    """Fill ``shares`` for years companyfacts left blank; note blanks' reasons."""
    by_year = shares_by_year(cik)
    for year, stmt in statements.items():
        if stmt.get("shares") is not None or year not in by_year:
            continue
        shares, how, accn = by_year[year]
        if shares is not None and shares > 0:
            stmt["shares"] = shares
            stmt["shares_source"] = f"{how}; 10-K {accn}"
        else:
            stmt["shares_note"] = f"{how} (10-K {accn})"
