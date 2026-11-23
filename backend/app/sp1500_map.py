"""Regenerate and read ``data/sp1500_map.json`` from Wikipedia S&P 1500 tables."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal

import httpx

IndexId = Literal["sp500", "sp400", "sp600"]


@dataclass(frozen=True)
class IndexSpec:
    index: IndexId
    label: str
    url: str
    min_rows: int


INDEX_SPECS: tuple[IndexSpec, ...] = (
    IndexSpec(
        "sp500",
        "S&P 500",
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        480,
    ),
    IndexSpec(
        "sp400",
        "S&P 400",
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        380,
    ),
    IndexSpec(
        "sp600",
        "S&P 600",
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        570,
    ),
)

_INDEX_BY_ID: dict[str, IndexId] = {spec.index: spec.index for spec in INDEX_SPECS}

_HEADER_ALIASES: dict[str, str] = {
    "symbol": "ticker",
    "ticker symbol": "ticker",
    "security": "name",
    "gics sector": "sector",
    "gics sub-industry": "sub_industry",
}
_REQUIRED_FIELDS = ("ticker", "name", "sector", "sub_industry")


@dataclass(frozen=True)
class ConstituentRow:
    ticker: str
    name: str
    sector: str
    sub_industry: str


@dataclass(frozen=True)
class Constituent:
    ticker: str
    index: IndexId
    sector: str
    sub_industry: str | None


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sp1500_map.json"
_UA = "LongMuch/1.0 (https://longmuch.com; sp1500 map refresh)"
_constituents_mem: dict[str, Constituent] | None = None


def clear_cache() -> None:
    """Clear the in-memory constituent cache."""
    global _constituents_mem
    _constituents_mem = None


def load_constituents(path: Path | None = None) -> dict[str, Constituent]:
    """Read, validate, normalize, and cache S&P 1500 constituents from disk."""
    global _constituents_mem
    if path is None and _constituents_mem is not None:
        return dict(_constituents_mem)
    raw = json.loads((path or DATA_PATH).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("sp1500_map root must be a JSON object")  # noqa: TRY004 - ValueError is the documented schema contract
    items = raw.get("constituents")
    if not isinstance(items, dict):
        raise ValueError("sp1500_map missing constituents mapping")  # noqa: TRY004 - ValueError is the documented schema contract
    out: dict[str, Constituent] = {}
    for raw_ticker, entry in items.items():
        if not isinstance(raw_ticker, str):
            raise ValueError("constituent ticker must be a string")  # noqa: TRY004 - ValueError is the documented schema contract
        ticker = raw_ticker.upper().strip()
        if not ticker:
            raise ValueError("constituent ticker must be non-empty")
        if not isinstance(entry, dict):
            raise ValueError(f"constituent entry for {ticker} must be an object")  # noqa: TRY004 - ValueError is the documented schema contract
        raw_index = entry.get("index")
        index = _INDEX_BY_ID.get(raw_index) if isinstance(raw_index, str) else None
        if index is None:
            raise ValueError(f"invalid index for {ticker}: {raw_index!r}")
        sector_raw = entry.get("sector")
        if not isinstance(sector_raw, str) or not sector_raw.strip():
            raise ValueError(f"invalid sector for {ticker}")
        sub_raw = entry.get("sub_industry")
        if sub_raw is None:
            sub_industry = None
        elif isinstance(sub_raw, str):
            sub_industry = sub_raw.strip() or None
        else:
            raise ValueError(f"invalid sub_industry for {ticker}")
        out[ticker] = Constituent(
            ticker=ticker,
            index=index,
            sector=sector_raw.strip(),
            sub_industry=sub_industry,
        )
    if path is None:
        _constituents_mem = out
    return dict(out)


def index_tickers(index: IndexId = "sp500", path: Path | None = None) -> list[str]:
    """Return ordered, deduplicated canonical tickers belonging to ``index``."""
    return [t for t, c in load_constituents(path).items() if c.index == index]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._sup_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "table":
            attr_map = dict(attrs)
            table: dict[str, Any] = {
                "id": attr_map.get("id"),
                "rows": [],
                "cur_row": None,
                "cur_cell": None,
            }
            self._stack.append(table)
            self.tables.append(table)
            return
        if not self._stack:
            return
        table = self._stack[-1]
        if name == "tr":
            self._flush_cell(table)
            self._flush_row(table)
            table["cur_row"] = []
            self._sup_depth = 0
        elif name in ("th", "td"):
            self._flush_cell(table)
            if table["cur_row"] is None:
                table["cur_row"] = []
            table["cur_cell"] = []
            self._sup_depth = 0
        elif name == "sup" and table["cur_cell"] is not None:
            self._sup_depth += 1

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "sup" and self._sup_depth > 0:
            self._sup_depth -= 1
        elif name == "table" and self._stack:
            table = self._stack.pop()
            self._flush_cell(table)
            self._flush_row(table)
            self._sup_depth = 0
        elif self._stack:
            table = self._stack[-1]
            if name in ("th", "td"):
                self._flush_cell(table)
                self._sup_depth = 0
            elif name == "tr":
                self._flush_cell(table)
                self._flush_row(table)
                self._sup_depth = 0

    def handle_data(self, data: str) -> None:
        if not self._stack or self._sup_depth > 0:
            return
        cur_cell = self._stack[-1]["cur_cell"]
        if cur_cell is not None:
            cur_cell.append(data)

    def _flush_cell(self, table: dict[str, Any]) -> None:
        cur_cell = table["cur_cell"]
        if cur_cell is None:
            return
        if table["cur_row"] is None:
            table["cur_row"] = []
        table["cur_row"].append("".join(cur_cell).strip())
        table["cur_cell"] = None

    def _flush_row(self, table: dict[str, Any]) -> None:
        cur_row = table["cur_row"]
        if cur_row is not None:
            table["rows"].append(cur_row)
            table["cur_row"] = None


def _normalize_header(cell: str) -> str:
    return " ".join(cell.lower().split())


def _parse_rows(rows: list[list[str]]) -> list[ConstituentRow]:
    if not rows:
        raise ValueError("constituents table has no rows")
    col_index: dict[str, int] = {}
    for idx, cell in enumerate(rows[0]):
        field = _HEADER_ALIASES.get(_normalize_header(cell))
        if field and field not in col_index:
            col_index[field] = idx
    missing = [f for f in _REQUIRED_FIELDS if f not in col_index]
    if missing:
        raise ValueError(f"missing required constituent headers: {missing}")

    min_cells = max(col_index.values()) + 1
    out: list[ConstituentRow] = []
    for cells in rows[1:]:
        if len(cells) < min_cells:
            continue
        ticker = cells[col_index["ticker"]].upper()
        name = cells[col_index["name"]]
        sector = cells[col_index["sector"]]
        sub_industry = cells[col_index["sub_industry"]]
        if not ticker or not sector:
            raise ValueError(f"constituent row missing ticker or sector: {cells!r}")
        out.append(
            ConstituentRow(
                ticker=ticker,
                name=name,
                sector=sector,
                sub_industry=sub_industry,
            )
        )
    if not out:
        raise ValueError("no constituent rows parsed")
    return out


def parse_constituents(page: str) -> list[ConstituentRow]:
    """Extract normalized constituent rows from a Wikipedia S&P index page."""
    parser = _TableParser()
    parser.feed(page)
    parser.close()

    for table in parser.tables:
        tid = table.get("id")
        if isinstance(tid, str) and tid.lower() == "constituents":
            return _parse_rows(table["rows"])

    for table in parser.tables:
        try:
            return _parse_rows(table["rows"])
        except ValueError:
            continue
    raise ValueError("constituents table not found")


def fetch_index_rows(spec: IndexSpec, html_path: Path | None = None) -> list[ConstituentRow]:
    """Load and validate one index table, enforcing ``spec.min_rows``."""
    if html_path is not None:
        page = html_path.read_text(encoding="utf-8")
    else:
        resp = httpx.get(spec.url, headers={"User-Agent": _UA}, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        page = resp.text
    rows = parse_constituents(page)
    if len(rows) < spec.min_rows:
        raise ValueError(f"{spec.index}: only {len(rows)} rows parsed (expected >= {spec.min_rows})")
    return rows


def build_map(
    rows_by_index: Mapping[IndexId, Sequence[ConstituentRow]],
    today: str,
) -> tuple[dict[str, Any], list[str]]:
    """Build canonical payload + overlap warnings in ``INDEX_SPECS`` precedence order."""
    constituents: dict[str, dict[str, str | None]] = {}
    seen_index: dict[str, IndexId] = {}
    warnings: list[str] = []

    for spec in INDEX_SPECS:
        for row in rows_by_index.get(spec.index, ()):
            prior = seen_index.get(row.ticker)
            if prior is not None:
                if prior != spec.index:
                    warnings.append(f"overlap: {row.ticker} kept in {prior}, skipped in {spec.index}")
                continue
            seen_index[row.ticker] = spec.index
            constituents[row.ticker] = {
                "index": spec.index,
                "sector": row.sector,
                "sub_industry": row.sub_industry or None,
            }

    payload: dict[str, Any] = {
        "schema_version": 1,
        "note": (
            "Static snapshot of S&P Composite 1500 constituents (S&P 500, S&P 400, S&P 600) "
            "and GICS classifications from Wikipedia. May lag official index changes."
        ),
        "retrieved": today,
        "sources": {spec.index: spec.url for spec in INDEX_SPECS},
        "constituents": constituents,
    }
    return payload, warnings


def _content(payload: dict[str, Any]) -> dict[str, tuple[str, str, str | None]]:
    """Semantic content only (index, sector, sub_industry), ignoring retrieval date."""
    raw = payload.get("constituents")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, tuple[str, str, str | None]] = {}
    for ticker, rec in raw.items():
        if not isinstance(ticker, str) or not isinstance(rec, dict):
            continue
        out[ticker] = (
            str(rec.get("index") or ""),
            str(rec.get("sector") or ""),
            rec.get("sub_industry"),
        )
    return out


def diff_summary(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Human-readable diff lines grouped by index and GICS attribute changes."""
    om = _content(old)
    nm = _content(new)
    lines: list[str] = []

    added_by_index: dict[str, list[str]] = {}
    for ticker in set(nm) - set(om):
        added_by_index.setdefault(nm[ticker][0], []).append(ticker)
    for idx in [s.index for s in INDEX_SPECS] + sorted(set(added_by_index) - set(_INDEX_BY_ID)):
        tickers = added_by_index.get(idx)
        if tickers:
            lines.append(f"added [{idx}]: " + ", ".join(sorted(tickers)))

    removed_by_index: dict[str, list[str]] = {}
    for ticker in set(om) - set(nm):
        removed_by_index.setdefault(om[ticker][0], []).append(ticker)
    for idx in [s.index for s in INDEX_SPECS] + sorted(set(removed_by_index) - set(_INDEX_BY_ID)):
        tickers = removed_by_index.get(idx)
        if tickers:
            lines.append(f"removed [{idx}]: " + ", ".join(sorted(tickers)))

    shared = sorted(set(om) & set(nm))
    moved = [(t, om[t][0], nm[t][0]) for t in shared if om[t][0] != nm[t][0]]
    if moved:
        lines.append("index changed: " + "; ".join(f"{t} {oi} -> {ni}" for t, oi, ni in moved))

    sectors_changed = [(t, om[t][1], nm[t][1]) for t in shared if om[t][1] != nm[t][1]]
    if sectors_changed:
        lines.append(
            "sectors changed: " + "; ".join(f"{t} {os} -> {ns}" for t, os, ns in sectors_changed)
        )

    subs_changed = [(t, om[t][2], nm[t][2]) for t in shared if om[t][2] != nm[t][2]]
    if subs_changed:
        lines.append(
            "sub_industries changed: "
            + "; ".join(f"{t} {os} -> {ns}" for t, os, ns in subs_changed)
        )

    return lines


def write_map(payload: dict[str, Any], path: Path = DATA_PATH) -> None:
    """Atomic temp-file write + clear_cache()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    clear_cache()


def main(argv: list[str] | None = None) -> int:
    """CLI: ``uv run python -m app.sp1500_map [--dry-run] [--path PATH] [--html-sp500 ...]``."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", type=Path, default=DATA_PATH)
    for spec in INDEX_SPECS:
        ap.add_argument(
            f"--html-{spec.index}",
            type=Path,
            default=None,
            help=f"parse saved {spec.label} page instead of fetching",
        )
    args = ap.parse_args(argv)

    rows_by_index: dict[IndexId, list[ConstituentRow]] = {}
    try:
        for spec in INDEX_SPECS:
            html_path = getattr(args, f"html_{spec.index}")
            rows_by_index[spec.index] = fetch_index_rows(spec, html_path=html_path)
    except (ValueError, OSError, httpx.HTTPError) as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 2

    old = json.loads(args.path.read_text(encoding="utf-8")) if args.path.is_file() else {}
    new, warnings = build_map(rows_by_index, dt.date.today().isoformat())
    changed = _content(old) != _content(new)

    counts = {
        spec.index: sum(
            1 for rec in new["constituents"].values() if rec["index"] == spec.index
        )
        for spec in INDEX_SPECS
    }
    total = len(new["constituents"])
    print(" ".join(f"{spec.index}={counts[spec.index]}" for spec in INDEX_SPECS) + f" total={total}")
    for warning in warnings:
        print(warning)
    for line in diff_summary(old, new):
        print(line)
    print(f"changed={'true' if changed else 'false'}")
    if changed and not args.dry_run:
        write_map(new, args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
