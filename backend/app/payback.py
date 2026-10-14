"""How-long payback from price and owner earnings per share.

No growth assumption: years = previous close / owner earnings per share.
"""

from __future__ import annotations

from typing import Any

OE_PER_SHARE = "Owner Earnings per Share"


def oe_per_share_from_rows(
    years: list[str], rows: list[dict[str, Any]]
) -> list[float | None]:
    raw: dict[str, Any] = {}
    for row in rows:
        if row.get("metric") == OE_PER_SHARE:
            candidate = row.get("raw") or {}
            if isinstance(candidate, dict):
                raw = candidate
            break
    out: list[float | None] = []
    for year in years:
        value = raw.get(str(year))
        if value is None:
            out.append(None)
            continue
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            out.append(None)
    return out


def average_oe(values: list[float | None], *, window: int = 5) -> float | None:
    """Mean of non-None values inside the leading window. Years are newest-first."""
    present = [value for value in values[:window] if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def payback_years(price: float | None, oe_ps: float | None) -> float | None:
    if price is None or oe_ps is None or oe_ps <= 0:
        return None
    return round(price / oe_ps, 1)


def treasury_payback_years(rate_decimal: float | None) -> float | None:
    if rate_decimal is None or rate_decimal <= 0:
        return None
    return round(1.0 / rate_decimal, 1)


def build_payback(
    *,
    price: float | None,
    years: list[str],
    rows: list[dict[str, Any]],
    treasury_rate_decimal: float | None,
) -> dict[str, Any] | None:
    if price is None:
        return None
    series = oe_per_share_from_rows(years, rows)
    latest = series[0] if series else None
    avg = average_oe(series, window=5)
    return {
        "price": float(price),
        "oe_per_share_latest": latest,
        "oe_per_share_5y_avg": avg,
        "years_at_latest": payback_years(price, latest),
        "years_at_5y_avg": payback_years(price, avg),
        "treasury_years": treasury_payback_years(treasury_rate_decimal),
        "pays_back": not (latest is not None and latest <= 0),
    }
