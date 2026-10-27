"""Total liabilities when the Liabilities tag is missing (issue #86)."""

from __future__ import annotations

import unittest

from app.edgar import map_companyfacts_to_statements


def _usd(fy: int, val: float) -> dict:
    return {
        "end": f"{fy}-12-31",
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{fy + 1}-02-15",
    }


def _facts(**tags: list[dict]) -> dict:
    us_gaap = {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}
    return {"facts": {"us-gaap": us_gaap}}


class TestMissingLiabilitiesTag(unittest.TestCase):
    def test_residual_with_negative_equity_ignores_current(self):
        # MCD shape: no Liabilities tag, negative equity, current is not the total.
        payload = _facts(
            Revenues=[_usd(2025, 26_000_000_000)],
            Assets=[_usd(2025, 59_500_000_000)],
            StockholdersEquity=[_usd(2025, -1_800_000_000)],
            LiabilitiesAndStockholdersEquity=[_usd(2025, 59_500_000_000)],
            LiabilitiesCurrent=[_usd(2025, 4_360_000_000)],
            LongTermDebt=[_usd(2025, 40_000_000_000)],
        )
        _years, statements = map_companyfacts_to_statements(payload)
        row = statements[2025]
        self.assertEqual(row["total_liabilities"], 61_300_000_000)
        self.assertEqual(row["equity"], -1_800_000_000)
        self.assertGreater(row["total_liabilities"], row["debt"])

    def test_nci_equity_preferred_for_residual(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 1)],
            LiabilitiesAndStockholdersEquity=[_usd(2024, 100)],
            StockholdersEquity=[_usd(2024, 40)],
            StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest=[
                _usd(2024, 45)
            ],
            LongTermDebt=[_usd(2024, 10)],
        )
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2024]["total_liabilities"], 55)
        self.assertEqual(statements[2024]["equity"], 40)

    def test_reported_liabilities_win(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 1)],
            Liabilities=[_usd(2024, 80)],
            LiabilitiesAndStockholdersEquity=[_usd(2024, 100)],
            StockholdersEquity=[_usd(2024, 20)],
            LiabilitiesCurrent=[_usd(2024, 5)],
            LongTermDebt=[_usd(2024, 30)],
        )
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2024]["total_liabilities"], 80)

    def test_neither_path_is_a_dash(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 1)],
            LiabilitiesCurrent=[_usd(2024, 4)],
            StockholdersEquity=[_usd(2024, 10)],
        )
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2024]["total_liabilities"])

    def test_below_debt_is_a_dash_and_warns(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 1)],
            Liabilities=[_usd(2024, 10)],
            LongTermDebt=[_usd(2024, 40)],
        )
        with self.assertLogs("app.edgar", level="WARNING") as logs:
            _years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2024]["total_liabilities"])
        self.assertTrue(any("below debt" in line for line in logs.output))
        self.assertTrue(any("2024" in line for line in logs.output))
