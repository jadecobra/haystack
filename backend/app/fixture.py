"""AAPL-shaped 5-year 10-K numbers for local MVP when EDGAR is unavailable.

Figures are rounded public-scale placeholders so the locked ratio table is
computable offline. Not a substitute for live XBRL in production.
"""

from __future__ import annotations

# Approximate AAPL 10-K scale (USD). Years newest-first in the API response.
AAPL_STATEMENTS: dict[int, dict[str, float]] = {
    2024: {
        "revenue": 391_035_000_000,
        "net_income": 93_736_000_000,
        "equity": 56_950_000_000,
        "assets": 364_980_000_000,
        "total_liabilities": 308_030_000_000,
        "debt": 106_629_000_000,
        "owner_earnings": 108_807_000_000,
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
        "owner_earnings": 99_584_000_000,
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
        "owner_earnings": 111_443_000_000,
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
        "owner_earnings": 92_953_000_000,
        "dividends": 14_467_000_000,
        "shares": 16_701_000_000,
        "cash": 34_940_000_000,
    },
    2020: {
        "revenue": 274_515_000_000,
        "net_income": 57_411_000_000,
        "equity": 65_339_000_000,
        "assets": 323_888_000_000,
        "total_liabilities": 258_549_000_000,
        "debt": 112_436_000_000,
        "owner_earnings": 73_365_000_000,
        "dividends": 14_081_000_000,
        "shares": 17_352_000_000,
        "cash": 38_016_000_000,
    },
}

# Approximate calendar-year DGS30 averages.
AAPL_TREASURY: dict[int, float] = {
    2024: 0.0435,
    2023: 0.0402,
    2022: 0.0311,
    2021: 0.0205,
    2020: 0.0156,
}


def statements_for(ticker: str) -> tuple[list[int], dict[int, dict[str, float]], dict[int, float]]:
    years = sorted(AAPL_STATEMENTS.keys(), reverse=True)
    return years, AAPL_STATEMENTS, AAPL_TREASURY
