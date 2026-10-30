"""Cash tag ladder: restricted cash fills blank years and is labeled (#105)."""

from __future__ import annotations

import unittest

from app.edgar import map_companyfacts_to_statements
from app.metrics import build_table
from app.tags import RESTRICTED_CASH_TAG, TAG_PREFS


def _instant(year: int, val: float) -> dict:
    return {
        "end": f"{year}-12-31",
        "val": val,
        "fy": year,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{year + 1}-02-01",
    }


def _shares(year: int, val: float) -> dict:
    return {
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "val": val,
        "fy": year,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{year + 1}-02-01",
    }


def _facts(us_gaap: dict) -> dict:
    return {"facts": {"us-gaap": us_gaap}}


def _cash_row(statements: dict, years: list[int]) -> dict:
    return next(
        row
        for row in build_table(years, statements)
        if row["metric"] == "Cash per Share"
    )


class TestCashTagOrder(unittest.TestCase):
    def test_ladder_keeps_existing_tags_first(self):
        self.assertEqual(
            TAG_PREFS["cash"][:2],
            ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
        )
        self.assertEqual(TAG_PREFS["cash"][-1], RESTRICTED_CASH_TAG)
        self.assertIn("CashAndDueFromBanks", TAG_PREFS["cash"])


class TestRestrictedCashLulu(unittest.TestCase):
    """LULU-shaped: carrying-value cash stops after FY2018; later years use restricted cash."""

    def _payload(self) -> dict:
        carrying = [_instant(2018, 1_000_000_000)]
        restricted = [
            _instant(year, year * 1_000_000_000) for year in range(2021, 2026)
        ]
        shares = [_shares(year, 100_000_000) for year in (2018, *range(2021, 2026))]
        income = [_instant(year, 1) for year in (2018, *range(2021, 2026))]
        # Net income facts are duration in the wild; an instant still fills via
        # _pick_annual_by_year when start is absent.
        return _facts(
            {
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": carrying}},
                RESTRICTED_CASH_TAG: {"units": {"USD": restricted}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {"shares": shares}
                },
                "NetIncomeLoss": {"units": {"USD": income}},
            }
        )

    def test_fy2022_through_fy2025_from_restricted_tag_with_label(self):
        years, statements = map_companyfacts_to_statements(self._payload())
        for year in (2022, 2023, 2024, 2025):
            self.assertEqual(statements[year]["cash"], year * 1_000_000_000)
            self.assertEqual(statements[year]["cash_tag"], RESTRICTED_CASH_TAG)
        row = _cash_row(statements, years)
        for year in (2022, 2023, 2024, 2025):
            self.assertIn("incl. restricted", row["values"][str(year)])
            self.assertNotEqual(row["values"][str(year)], "—")
        self.assertEqual(statements[2018]["cash"], 1_000_000_000)
        self.assertEqual(
            statements[2018]["cash_tag"], "CashAndCashEquivalentsAtCarryingValue"
        )
        self.assertNotIn("incl. restricted", row["values"]["2018"])


class TestCarryingValueUnchanged(unittest.TestCase):
    def test_carrying_value_years_keep_the_same_cash(self):
        years_wanted = [2023, 2024]
        carrying = [_instant(year, 500_000_000 + year) for year in years_wanted]
        # A larger restricted-cash fact must not replace a carrying-value year.
        restricted = [_instant(year, 9_000_000_000) for year in years_wanted]
        shares = [_shares(year, 100_000_000) for year in years_wanted]
        payload = _facts(
            {
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": carrying}},
                RESTRICTED_CASH_TAG: {"units": {"USD": restricted}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {"shares": shares}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [_instant(year, 1) for year in years_wanted]}
                },
            }
        )
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(years[:2], [2024, 2023])
        for year in years_wanted:
            self.assertEqual(statements[year]["cash"], 500_000_000 + year)
            self.assertEqual(
                statements[year]["cash_tag"],
                "CashAndCashEquivalentsAtCarryingValue",
            )
        row = _cash_row(statements, years)
        for year in years_wanted:
            self.assertNotIn("incl. restricted", row["values"][str(year)])
            self.assertEqual(row["raw"][str(year)], (500_000_000 + year) / 100_000_000)
