"""Payback years from price and owner earnings per share."""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.payback import (
    average_oe,
    build_payback,
    payback_years,
    treasury_payback_years,
)


def _oe_rows(by_year: dict[str, float | None]) -> list[dict]:
    return [
        {
            "metric": "Owner Earnings per Share",
            "values": {},
            "raw": by_year,
        }
    ]


class TestPaybackYears(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(payback_years(100.0, 8.0), 12.5)

    def test_zero_oe(self):
        self.assertIsNone(payback_years(100.0, 0.0))

    def test_negative_oe(self):
        self.assertIsNone(payback_years(100.0, -2.0))

    def test_missing_price_or_oe(self):
        self.assertIsNone(payback_years(None, 2.0))
        self.assertIsNone(payback_years(100.0, None))


class TestAverageOe(unittest.TestCase):
    def test_five_years(self):
        self.assertEqual(average_oe([5.0, 4.0, 3.0, 2.0, 1.0]), 3.0)

    def test_sparse_stays_inside_window(self):
        # Leading window has two values; the sixth year is outside the window.
        self.assertEqual(average_oe([None, 4.0, None, None, 2.0, 100.0]), 3.0)

    def test_empty(self):
        self.assertIsNone(average_oe([]))
        self.assertIsNone(average_oe([None, None, None]))


class TestTreasuryPayback(unittest.TestCase):
    def test_positive_rate(self):
        self.assertAlmostEqual(treasury_payback_years(0.0484), round(1 / 0.0484, 1))

    def test_non_positive(self):
        self.assertIsNone(treasury_payback_years(0.0))
        self.assertIsNone(treasury_payback_years(None))
        self.assertIsNone(treasury_payback_years(-0.01))


class TestBuildPayback(unittest.TestCase):
    def test_synthetic_rows(self):
        block = build_payback(
            price=100.0,
            years=["2025", "2024", "2023"],
            rows=_oe_rows({"2025": 10.0, "2024": 5.0, "2023": 5.0}),
            treasury_rate_decimal=0.05,
        )
        assert block is not None
        self.assertEqual(block["oe_per_share_latest"], 10.0)
        self.assertAlmostEqual(block["oe_per_share_5y_avg"], 20.0 / 3.0)
        self.assertEqual(block["years_at_latest"], 10.0)
        self.assertEqual(block["treasury_years"], 20.0)
        self.assertTrue(block["pays_back"])

    def test_missing_price(self):
        self.assertIsNone(
            build_payback(
                price=None,
                years=["2025"],
                rows=_oe_rows({"2025": 1.0}),
                treasury_rate_decimal=0.04,
            )
        )

    def test_negative_latest_does_not_pay_back(self):
        block = build_payback(
            price=50.0,
            years=["2025", "2024"],
            rows=_oe_rows({"2025": -1.0, "2024": 4.0}),
            treasury_rate_decimal=0.04,
        )
        assert block is not None
        self.assertFalse(block["pays_back"])
        self.assertIsNone(block["years_at_latest"])
        self.assertEqual(block["years_at_5y_avg"], payback_years(50.0, 1.5))


class TestAnalyzePaybackContract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_fixture_aapl_payback(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            response = self.client.get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        payback = body["payback"]
        self.assertIsNotNone(payback)
        self.assertEqual(payback["price"], 100.0)
        self.assertGreater(payback["oe_per_share_latest"], 0)
        self.assertAlmostEqual(
            payback["years_at_latest"],
            round(100.0 / payback["oe_per_share_latest"], 1),
        )
        self.assertIsNotNone(payback["years_at_5y_avg"])
        self.assertAlmostEqual(payback["treasury_years"], round(1 / 0.0484, 1))
        self.assertTrue(payback["pays_back"])

    def test_fixture_aapl_payback_values(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            payback = self.client.get("/analyze/AAPL").json()["payback"]
        self.assertEqual(
            set(payback),
            {
                "price",
                "oe_per_share_latest",
                "oe_per_share_5y_avg",
                "years_at_latest",
                "years_at_5y_avg",
                "treasury_years",
                "pays_back",
            },
        )
        self.assertAlmostEqual(payback["oe_per_share_latest"], 6.650, places=2)
        self.assertAlmostEqual(payback["oe_per_share_5y_avg"], 6.495, places=2)
        self.assertEqual(payback["years_at_latest"], 15.0)
        self.assertEqual(payback["years_at_5y_avg"], 15.4)
        self.assertEqual(payback["treasury_years"], 20.7)

    def test_fixture_negative_latest_oe_contract(self):
        from app import fixture

        latest = max(fixture.AAPL_STATEMENTS)
        patched = dict(fixture.AAPL_STATEMENTS[latest], owner_earnings=-1_000_000_000)
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}), mock.patch.dict(
            fixture.AAPL_STATEMENTS, {latest: patched}
        ):
            response = self.client.get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        payback = response.json()["payback"]
        self.assertFalse(payback["pays_back"])
        self.assertLess(payback["oe_per_share_latest"], 0)
        self.assertIsNone(payback["years_at_latest"])
        self.assertEqual(payback["price"], 100.0)
