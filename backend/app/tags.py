"""Ordered US-GAAP tag preference lists per locked statement field."""

from __future__ import annotations

# Declared/paid common DPS. edgar composes a dividends candidate from these
# times as-reported shares; see ``_compose_dividends``.
DPS_TAGS = [
    "CommonStockDividendsPerShareDeclared",
    "CommonStockDividendsPerShareCashPaid",
]

# Keys align with app.metrics.FIELDS (plus owner-earnings component tags).
TAG_PREFS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueGoodsNet",
        # Last. Fills a year only when no earlier revenue tag has an annual value.
        "RevenueFromContractWithCustomerIncludingAssessedTax",
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
    # Ladder for compose_debt. One series per tag; combination rules live in edgar.
    # Overlapping concepts. compose_debt never sums them; see its docstring.
    "debt_ladder": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "ConvertibleLongTermNotesPayable",
        "ConvertibleDebtNoncurrent",
        "NotesPayable",
        "SeniorNotes",
        "UnsecuredDebt",
        "SecuredDebt",
        "UnsecuredLongTermDebt",
        "OtherLongTermDebtNoncurrent",
        "DebtLongtermAndShorttermCombinedAmount",
        "DebtInstrumentCarryingAmount",
        "OtherShortTermBorrowings",
        "LineOfCredit",
    ],
    # Not debt totals. compose_debt takes abs of the annual value present
    # for the interest-materiality cross-check; see its docstring.
    "debt_interest": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestExpenseNonoperating",
        "InterestPaidNet",
    ],
    # Signed net. Only a negative annual value (net interest expense) counts,
    # as abs(value). A positive value is net interest income and is ignored.
    "debt_interest_net": [
        "InterestIncomeExpenseNet",
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
        # Last: cash-flow ordinary dividends. Fills only years no tag above has.
        # JNJ tags its cash-flow dividends only as PaymentsOfOrdinaryDividends
        # (no PaymentsOfDividends* / Dividends), so DPS was blank every year.
        "PaymentsOfOrdinaryDividends",
    ],
    "dividends_per_share": DPS_TAGS,
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
}
