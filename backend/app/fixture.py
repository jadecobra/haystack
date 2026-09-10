"""AAPL-shaped 10-K numbers for local MVP when EDGAR is unavailable.

Kept at five years for agents; live EDGAR is the product path and returns
every mapped annual year. Figures are rounded public-scale placeholders so
the locked ratio table is computable offline. Not a substitute for live XBRL.

owner_earnings is OCF − min(|capex|, D&A) via edgar._owner_earnings, not
reported free cash flow. FY2025 is the first year in this window where D&A
is the maintenance term (capex is larger).
"""

from __future__ import annotations

from app.edgar import _owner_earnings

# AAPL FY USD from companyfacts (same tags as edgar). Newest fiscal year first.
AAPL_OCF: dict[int, float] = {
    2025: 111_482_000_000,
    2024: 118_254_000_000,
    2023: 110_543_000_000,
    2022: 122_151_000_000,
    2021: 104_038_000_000,
}
AAPL_CAPEX: dict[int, float] = {
    2025: 12_715_000_000,
    2024: 9_447_000_000,
    2023: 10_959_000_000,
    2022: 10_708_000_000,
    2021: 11_085_000_000,
}
AAPL_DA: dict[int, float] = {
    2025: 11_698_000_000,
    2024: 11_445_000_000,
    2023: 11_519_000_000,
    2022: 11_104_000_000,
    2021: 11_284_000_000,
}
_AAPL_OWNER_EARNINGS = _owner_earnings(AAPL_OCF, AAPL_CAPEX, AAPL_DA)

# Approximate AAPL 10-K scale (USD). Years newest-first in the API response.
AAPL_STATEMENTS: dict[int, dict[str, float]] = {
    2025: {
        "revenue": 416_161_000_000,
        "net_income": 112_010_000_000,
        "equity": 73_733_000_000,
        "assets": 359_241_000_000,
        "total_liabilities": 285_508_000_000,
        "debt": 90_678_000_000,
        "owner_earnings": _AAPL_OWNER_EARNINGS[2025],
        "dividends": 15_421_000_000,
        "shares": 15_005_000_000,
        "cash": 35_934_000_000,
    },
    2024: {
        "revenue": 391_035_000_000,
        "net_income": 93_736_000_000,
        "equity": 56_950_000_000,
        "assets": 364_980_000_000,
        "total_liabilities": 308_030_000_000,
        "debt": 106_629_000_000,
        "owner_earnings": _AAPL_OWNER_EARNINGS[2024],
        "dividends": 15_234_000_000,
        "shares": 15_334_000_000,
        "cash": 29_943_000_000,
    },
    2023: {
        "revenue": 383_285_000_000,
        "net_income": 96_995_000_000,
        "equity": 62_146_000_000,
        "assets": 352_583_000_000,
        "total_liabilities": 290_437_000_000,
        "debt": 111_088_000_000,
        "owner_earnings": _AAPL_OWNER_EARNINGS[2023],
        "dividends": 15_025_000_000,
        "shares": 15_744_000_000,
        "cash": 29_965_000_000,
    },
    2022: {
        "revenue": 394_328_000_000,
        "net_income": 99_803_000_000,
        "equity": 50_672_000_000,
        "assets": 352_755_000_000,
        "total_liabilities": 302_083_000_000,
        "debt": 120_069_000_000,
        "owner_earnings": _AAPL_OWNER_EARNINGS[2022],
        "dividends": 14_841_000_000,
        "shares": 16_303_000_000,
        "cash": 23_646_000_000,
    },
    2021: {
        "revenue": 365_817_000_000,
        "net_income": 94_680_000_000,
        "equity": 63_090_000_000,
        "assets": 351_002_000_000,
        "total_liabilities": 287_912_000_000,
        "debt": 124_719_000_000,
        "owner_earnings": _AAPL_OWNER_EARNINGS[2021],
        "dividends": 14_467_000_000,
        "shares": 16_701_000_000,
        "cash": 34_940_000_000,
    },
}

# Approximate calendar-year DGS30 averages (2025 is FRED year-end).
AAPL_TREASURY: dict[int, float] = {
    2025: 0.0484,
    2024: 0.0435,
    2023: 0.0402,
    2022: 0.0311,
    2021: 0.0205,
}


def statements_for(ticker: str) -> tuple[list[int], dict[int, dict[str, float]], dict[int, float]]:
    years = sorted(AAPL_STATEMENTS.keys(), reverse=True)
    return years, AAPL_STATEMENTS, AAPL_TREASURY
