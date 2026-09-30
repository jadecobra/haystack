"""Golden cases for the non-overlapping debt ladder."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.edgar import compose_debt, map_companyfacts_to_statements


def _usd(fy: int, val: float) -> dict:
    return {
        "end": f"{fy}-12-31",
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{fy + 1}-02-01",
    }


def _gaap(**tags: list[dict]) -> dict:
    return {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}


class TestComposeDebt(unittest.TestCase):
    def test_zero_debt_from_liabilities_without_ladder_tags(self):
        # Known zero-debt style: balance sheet exists, no debt concepts filed.
        totals, states = compose_debt(_gaap(Liabilities=[_usd(2024, 500.0)]))
        self.assertNotIn(2024, totals)
        self.assertEqual(states[2024], "zero")

    def test_explicit_long_term_debt_zero(self):
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                LongTermDebt=[_usd(2024, 0.0)],
            )
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertEqual(states[2024], "zero")

    def test_levered_long_term_does_not_double_count_debt_current(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebt=[_usd(2024, 100.0)],
                ShortTermBorrowings=[_usd(2024, 7.0)],
                DebtCurrent=[_usd(2024, 40.0)],
                CommercialPaper=[_usd(2024, 3.0)],
            )
        )
        # LongTermDebt already includes current maturities; DebtCurrent is
        # skipped. ShortTermBorrowings already includes commercial paper.
        self.assertEqual(totals[2024], 107.0)
        self.assertEqual(states[2024], "positive")

    def test_noncurrent_plus_current_maturities(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebtNoncurrent=[_usd(2024, 80.0)],
                LongTermDebtCurrent=[_usd(2024, 20.0)],
                CommercialPaper=[_usd(2024, 3.0)],
            )
        )
        self.assertEqual(totals[2024], 103.0)
        self.assertEqual(states[2024], "positive")

    def test_debt_current_replaces_maturities_and_short_borrowings(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebtNoncurrent=[_usd(2024, 80.0)],
                LongTermDebtCurrent=[_usd(2024, 20.0)],
                DebtCurrent=[_usd(2024, 40.0)],
                ShortTermBorrowings=[_usd(2024, 9.0)],
            )
        )
        self.assertEqual(totals[2024], 120.0)
        self.assertEqual(states[2024], "positive")

    def test_unknown_when_no_debt_tags_and_no_liabilities(self):
        totals, states = compose_debt(_gaap(Revenues=[_usd(2024, 10.0)]))
        self.assertEqual(totals, {})
        self.assertEqual(states, {})


class TestComposeDebtRealGoldens(unittest.TestCase):
    """Trimmed live companyfacts (ladder tags + Liabilities, FY2025 annual only)."""

    FIXTURES = Path(__file__).resolve().parent / "fixtures"

    def _load(self, name: str) -> dict:
        return json.loads((self.FIXTURES / name).read_text(encoding="utf-8"))

    def test_cmg_known_zero_debt(self):
        # Chipotle FY2025 10-K: LongTermDebt explicitly 0, Liabilities 6.16B.
        payload = self._load("cmg_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], 0.0)
        self.assertEqual(states[2025], "zero")
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2025]["debt"], 0.0)
        self.assertEqual(statements[2025]["debt_state"], "zero")

    def test_aapl_levered_no_double_count(self):
        # Apple FY2025: LongTermDebt 90.678B (= noncurrent 78.328B + current
        # 12.350B, not added again) + CommercialPaper 7.979B = 98.657B.
        payload = self._load("aapl_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], 98_657_000_000.0)
        self.assertEqual(states[2025], "positive")

    def test_unknown_path_through_statements(self):
        payload = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {"units": {"USD": [_usd(2024, 10.0)]}},
                }
            }
        }
        years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2024]["debt"])
        self.assertEqual(statements[2024]["debt_state"], "unknown")
