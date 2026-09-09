"""Ordered US-GAAP tag preference lists per locked statement field."""

from __future__ import annotations

# Keys align with app.metrics.FIELDS (plus owner-earnings component tags).
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
    # Owner earnings components — not FIELDS keys; edgar composes owner_earnings from these.
    "operating_cf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex_combined": [
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    ],
    "capex_ppe": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    "capex_productive": [
        "PaymentsToAcquireProductiveAssets",
    ],
    "capex_software": [
        "PaymentsToDevelopSoftware",
        "PaymentsToAcquireSoftware",
        "PaymentsForSoftware",
    ],
    "da": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "change_in_cash": [
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
        "IncreaseDecreaseInCashAndCashEquivalents",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    ],
    "investing_cf": [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ],
    "financing_cf": [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ],
    "fx_effect": [
        "EffectOfExchangeRateOnCashAndCashEquivalents",
        "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "accounts_receivable": [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
        "AccountsReceivableGrossCurrent",
    ],
    "inventory": [
        "InventoryNet",
        "InventoryFinishedGoods",
    ],
    "accounts_payable": [
        "AccountsPayableCurrent",
        "AccountsPayable",
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
