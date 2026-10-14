"""Regenerate ``data/sp500_tickers.json`` from Wikipedia's S&P 500 constituents.

Same source as the existing ``sectors`` (#41 added ``sub_industries``):
https://en.wikipedia.org/wiki/List_of_S%26P_500_companies (table id
``constituents``: Symbol, Security, GICS Sector, GICS Sub-Industry, ...).

Usage: ``uv run python -m app.sp500_map [--dry-run] [--path PATH]``.
Exit 0 always on success; prints ``changed=true|false`` and a summary of
added/removed tickers and sector/sub-industry changes. ``--dry-run`` never
writes. Refuses to write a suspiciously small table (< 480 rows).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500_tickers.json"
MIN_ROWS = 480
_UA = "LongMuch/1.0 (https://longmuch.com; sp500 map refresh)"


def _clean(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def parse_constituents(page: str) -> list[dict[str, str]]:
    """Rows of {ticker, name, sector, sub_industry} from the constituents table."""
    start = page.find('id="constituents"')
    if start < 0:
        raise ValueError("constituents table not found")
    end = page.find("</table>", start)
    table = page[start:end]
    rows = re.split(r"<tr[^>]*>", table)
    header = [_clean(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[1], re.S)] if len(rows) > 1 else []
    want = ["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]
    if header[:4] != want:
        raise ValueError(f"unexpected constituents header: {header[:4]}")
    out: list[dict[str, str]] = []
    for row in rows[2:]:
        cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)(?=<t[dh]|$)", row, re.S)]
        if len(cells) >= 4 and cells[0]:
            out.append(
                {"ticker": cells[0].upper(), "name": cells[1], "sector": cells[2], "sub_industry": cells[3]}
            )
    return out


def build_map(rows: list[dict[str, str]], previous: dict[str, Any], today: str) -> dict[str, Any]:
    tickers = sorted({r["ticker"] for r in rows}, key=lambda t: next(i for i, r in enumerate(rows) if r["ticker"] == t))
    by = {r["ticker"]: r for r in rows}
    return {
        "universe": previous.get("universe", "sp500"),
        "note": previous.get(
            "note",
            "Static snapshot of S&P 500 tickers. May lag official index changes. Source: Wikipedia List of S&P 500 companies.",
        ),
        "tickers": tickers,
        "sectors_note": f"GICS sector per ticker, from the same Wikipedia List of S&P 500 companies (retrieved {today}). May lag reclassifications.",
        "sectors": {t: by[t]["sector"] for t in tickers if by[t]["sector"]},
        "sub_industries_note": f"GICS sub-industry per ticker, from the same Wikipedia List of S&P 500 companies (retrieved {today}). May lag reclassifications.",
        "sub_industries": {t: by[t]["sub_industry"] for t in tickers if by[t]["sub_industry"]},
    }


def _content(d: dict[str, Any]) -> tuple[Any, ...]:
    """Compare data only, ignoring retrieval dates in the notes."""
    return (sorted(d.get("tickers") or []), d.get("sectors") or {}, d.get("sub_industries") or {})


def diff_summary(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    o, n = set(old.get("tickers") or []), set(new.get("tickers") or [])
    if n - o:
        lines.append("added: " + ", ".join(sorted(n - o)))
    if o - n:
        lines.append("removed: " + ", ".join(sorted(o - n)))
    for key in ("sectors", "sub_industries"):
        om, nm = old.get(key) or {}, new.get(key) or {}
        changed = sorted(t for t in (set(om) & set(nm)) if om[t] != nm[t])
        if changed:
            lines.append(f"{key} changed: " + "; ".join(f"{t} {om[t]} -> {nm[t]}" for t in changed))
        gained = sorted((set(nm) - set(om)) & o)
        if gained:
            lines.append(f"{key} filled: " + ", ".join(gained))
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", type=Path, default=DATA_PATH)
    ap.add_argument("--html", type=Path, help="parse a saved page instead of fetching")
    args = ap.parse_args(argv)

    if args.html:
        page = args.html.read_text(encoding="utf-8")
    else:
        resp = httpx.get(URL, headers={"User-Agent": _UA}, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        page = resp.text
    rows = parse_constituents(page)
    if len(rows) < MIN_ROWS:
        print(f"refusing: only {len(rows)} rows parsed", file=sys.stderr)
        return 2
    old = json.loads(args.path.read_text(encoding="utf-8")) if args.path.is_file() else {}
    new = build_map(rows, old, dt.date.today().isoformat())
    changed = _content(old) != _content(new)
    print(f"rows={len(rows)} tickers={len(new['tickers'])} sectors={len(new['sectors'])} sub_industries={len(new['sub_industries'])}")
    for line in diff_summary(old, new):
        print(line)
    print(f"changed={'true' if changed else 'false'}")
    if changed and not args.dry_run:
        args.path.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
