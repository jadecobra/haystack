"""Locked MVP ratio / per-share table. Order and labels are the product contract."""

from __future__ import annotations

from typing import Any

RATIO_LABELS = [
    "Net Income / Revenue",
    "Net Income / Equity",
    "Net Income / Assets",
    "Net Income / Total Liabilities",
    "Net Income / Debt",
    "Owner Earnings / Revenue",
    "Owner Earnings / Equity",
    "Owner Earnings / Assets",
    "Owner Earnings / Total Liabilities",
    "Owner Earnings / Debt",
    "Owner Earnings / Last Close Price",
    "Dividends / Net Income",
    "Dividends / Owner Earnings",
    "Dividends / Equity",
]

PER_SHARE_LABELS = [
    "Shares Outstanding",
    "Debt per Share",
    "Revenue per Share",
    "Net Income per Share",
    "Owner Earnings per Share",
    "Dividends per Share",
    "Equity per Share",
    "Assets per Share",
    "Cash per Share",
    "Liabilities per Share",
    "Owner Earnings / 30 Year Treasury per Share",
    "30 Year Treasury (DGS30)",
]

LOCKED_LABELS = RATIO_LABELS + PER_SHARE_LABELS
TREASURY_LABEL = "Owner Earnings / 30 Year Treasury per Share"

SCHEMA_VERSION = "6"

FIELDS = (
    "revenue",
    "net_income",
    "equity",
    "assets",
    "total_liabilities",
    "debt",
    "owner_earnings",
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


def _fmt_shares(value: float | None) -> str:
    if value is None:
        return "—"
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.2f}M"
    return f"{sign}{abs_v:,.0f}"


def compute_year(
    stmt: dict[str, Any],
    treasury_yield: float | None,
    previous_close: float | None = None,
) -> dict[str, float | None]:
    s = {k: _num(stmt.get(k)) for k in FIELDS}
    shares = s["shares"]
    ni = s["net_income"]
    owner_earnings = s["owner_earnings"]
    div = s["dividends"]
    oe_ps = _ratio(owner_earnings, shares)
    ty = _num(treasury_yield)
    close = _num(previous_close)
    return {
        "Net Income / Revenue": _ratio(ni, s["revenue"]),
        "Net Income / Equity": _ratio(ni, s["equity"]),
        "Net Income / Assets": _ratio(ni, s["assets"]),
        "Net Income / Total Liabilities": _ratio(ni, s["total_liabilities"]),
        "Net Income / Debt": _ratio(ni, s["debt"]),
        "Owner Earnings / Revenue": _ratio(owner_earnings, s["revenue"]),
        "Owner Earnings / Equity": _ratio(owner_earnings, s["equity"]),
        "Owner Earnings / Assets": _ratio(owner_earnings, s["assets"]),
        "Owner Earnings / Total Liabilities": _ratio(owner_earnings, s["total_liabilities"]),
        "Owner Earnings / Debt": _ratio(owner_earnings, s["debt"]),
        "Owner Earnings / Last Close Price": _ratio(oe_ps, close),
        "Dividends / Net Income": _ratio(div, ni),
        "Dividends / Owner Earnings": _ratio(div, owner_earnings),
        "Dividends / Equity": _ratio(div, s["equity"]),
        "Shares Outstanding": shares,
        "Debt per Share": _ratio(s["debt"], shares),
        "Revenue per Share": _ratio(s["revenue"], shares),
        "Net Income per Share": _ratio(ni, shares),
        "Owner Earnings per Share": oe_ps,
        "Dividends per Share": _ratio(div, shares),
        "Equity per Share": _ratio(s["equity"], shares),
        "Assets per Share": _ratio(s["assets"], shares),
        "Cash per Share": _ratio(s["cash"], shares),
        "Liabilities per Share": _ratio(s["total_liabilities"], shares),
        TREASURY_LABEL: _ratio(oe_ps, ty),
        "30 Year Treasury (DGS30)": ty,
    }


def _fmt_yield(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def format_cell(label: str, value: float | None) -> str:
    if label == "Owner Earnings / Last Close Price":
        return _fmt_yield(value)
    if label in RATIO_LABELS:
        return _fmt_pct(value)
    if label == "Shares Outstanding":
        return _fmt_shares(value)
    if label == "30 Year Treasury (DGS30)":
        return _fmt_yield(value)
    return _fmt_money(value)


def build_table(
    years: list[int],
    statements: dict[int, dict[str, Any]],
    treasury_by_year: dict[int, float] | None = None,
    previous_close: float | None = None,
) -> list[dict[str, Any]]:
    treasury_by_year = treasury_by_year or {}
    computed: dict[int, dict[str, float | None]] = {}
    for year in years:
        computed[year] = compute_year(
            statements.get(year, {}),
            treasury_by_year.get(year),
            previous_close,
        )
    rows = []
    for label in LOCKED_LABELS:
        raw = {str(year): computed[year].get(label) for year in years}
        values = {str(year): format_cell(label, raw[str(year)]) for year in years}
        rows.append({"metric": label, "values": values, "raw": raw})
    return rows
