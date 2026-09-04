"""Locked MVP ratio / per-share table. Order and labels are the product contract."""

from __future__ import annotations

from typing import Any

RATIO_LABELS = [
    "Net Income / Revenue",
    "Net Income / Equity",
    "Net Income / Assets",
    "Net Income / Total Liabilities",
    "Net Income / Debt",
    "FCF / Revenue",
    "FCF / Equity",
    "FCF / Assets",
    "FCF / Total Liabilities",
    "FCF / Debt",
    "Dividends / Net Income",
    "Dividends / FCF",
    "Dividends / Equity",
]

PER_SHARE_LABELS = [
    "Debt per Share",
    "Revenue per Share",
    "Net Income per Share",
    "FCF per Share",
    "Dividends per Share",
    "Equity per Share",
    "Assets per Share",
    "Cash per Share",
    "Liabilities per Share",
    "FCF / 30 Year Treasury per Share",
]

LOCKED_LABELS = RATIO_LABELS + PER_SHARE_LABELS

# Bump when AnalysisResponse fields or row shape change. GET /contract exposes this.
SCHEMA_VERSION = "1"

FIELDS = (
    "revenue",
    "net_income",
    "equity",
    "assets",
    "total_liabilities",
    "debt",
    "fcf",
    "dividends",
    "shares",
    "cash",
)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.2f}M"
    return f"{sign}${abs_v:.2f}"


def compute_year(stmt: dict[str, Any], treasury_yield: float | None) -> dict[str, float | None]:
    s = {k: _num(stmt.get(k)) for k in FIELDS}
    shares = s["shares"]
    ni = s["net_income"]
    fcf = s["fcf"]
    div = s["dividends"]
    fcf_ps = _ratio(fcf, shares)
    ty = _num(treasury_yield)
    return {
        "Net Income / Revenue": _ratio(ni, s["revenue"]),
        "Net Income / Equity": _ratio(ni, s["equity"]),
        "Net Income / Assets": _ratio(ni, s["assets"]),
        "Net Income / Total Liabilities": _ratio(ni, s["total_liabilities"]),
        "Net Income / Debt": _ratio(ni, s["debt"]),
        "FCF / Revenue": _ratio(fcf, s["revenue"]),
        "FCF / Equity": _ratio(fcf, s["equity"]),
        "FCF / Assets": _ratio(fcf, s["assets"]),
        "FCF / Total Liabilities": _ratio(fcf, s["total_liabilities"]),
        "FCF / Debt": _ratio(fcf, s["debt"]),
        "Dividends / Net Income": _ratio(div, ni),
        "Dividends / FCF": _ratio(div, fcf),
        "Dividends / Equity": _ratio(div, s["equity"]),
        "Debt per Share": _ratio(s["debt"], shares),
        "Revenue per Share": _ratio(s["revenue"], shares),
        "Net Income per Share": _ratio(ni, shares),
        "FCF per Share": fcf_ps,
        "Dividends per Share": _ratio(div, shares),
        "Equity per Share": _ratio(s["equity"], shares),
        "Assets per Share": _ratio(s["assets"], shares),
        "Cash per Share": _ratio(s["cash"], shares),
        "Liabilities per Share": _ratio(s["total_liabilities"], shares),
        "FCF / 30 Year Treasury per Share": _ratio(fcf_ps, ty),
    }


def format_cell(label: str, value: float | None) -> str:
    if label in RATIO_LABELS:
        return _fmt_pct(value)
    return _fmt_money(value)


def build_table(
    years: list[int],
    statements: dict[int, dict[str, Any]],
    treasury_by_year: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    treasury_by_year = treasury_by_year or {}
    computed: dict[int, dict[str, float | None]] = {}
    for year in years:
        computed[year] = compute_year(statements.get(year, {}), treasury_by_year.get(year))
    rows = []
    for label in LOCKED_LABELS:
        values = {str(year): format_cell(label, computed[year].get(label)) for year in years}
        rows.append({"metric": label, "values": values})
    return rows
