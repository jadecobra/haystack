"""Ordered US-GAAP tag preference lists per locked statement field."""

from __future__ import annotations

# Keys align with app.metrics.FIELDS (plus FCF component tags).
TAG_PREFS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
        "LiabilitiesNoncurrent",  # used with current for sum fallback in edgar
        "LiabilitiesCurrent",
    ],
    "debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtCurrent",
        "DebtCurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
    ],
    "shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
    ],
    "dividends": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "Dividends",
        "PaymentsOfDividendsCommonStockAndPreferredStockAndUnits",
    ],
    # FCF components — not FIELDS keys; edgar composes fcf from these.
    "operating_cf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    ],
    # Helpers for liabilities / debt composition
    "liabilities_and_equity": [
        "LiabilitiesAndStockholdersEquity",
    ],
    "liabilities_current": [
        "LiabilitiesCurrent",
    ],
    "liabilities_noncurrent": [
        "LiabilitiesNoncurrent",
    ],
    "debt_current": [
        "DebtCurrent",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
    ],
    "debt_longterm": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
}
