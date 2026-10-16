"""Ratio-of-sums peer/screen columns over the newest annual years (#58)."""

import unittest

from app.screen import _row_or_reason


def _stmt(*, oe, shares, ni, rev, debt, equity, debt_state="positive"):
    return {
        "owner_earnings": oe,
        "shares": shares,
        "net_income": ni,
        "revenue": rev,
        "debt": debt,
        "equity": equity,
        "debt_state": debt_state,
    }


def _row(years, statements, *, price=30.0, ticker="T"):
    row, reason = _row_or_reason(
        ticker,
        years=years,
        statements=statements,
        company_name="Test Co",
        quote={"price": price, "as_of": "2026-01-01"},
    )
    assert reason is None
    assert row is not None
    return row


class TestRatioOfSums(unittest.TestCase):
    def test_five_year_hand_computed_ignores_older_year(self):
        # Newest five: OE/sh 10, 8, 6, 4, 2 → mean 6. Price 30 → yield 0.2, payback 5.
        # NI 10+20+30+40+50 = 150; revenue 100*5 = 500 → margin 0.3.
        # Debt 10*5 = 50; equity 100*5 = 500 → D/E 0.1.
        # 2020 is outside the window.
        statements = {
            2025: _stmt(oe=100, shares=10, ni=10, rev=100, debt=10, equity=100),
            2024: _stmt(oe=80, shares=10, ni=20, rev=100, debt=10, equity=100),
            2023: _stmt(oe=60, shares=10, ni=30, rev=100, debt=10, equity=100),
            2022: _stmt(oe=40, shares=10, ni=40, rev=100, debt=10, equity=100),
            2021: _stmt(oe=20, shares=10, ni=50, rev=100, debt=10, equity=100),
            2020: _stmt(oe=1000, shares=10, ni=999, rev=999, debt=999, equity=999),
        }
        row = _row([2020, 2021, 2022, 2023, 2024, 2025], statements, price=30.0)
        self.assertEqual(row["years"], 5)
        self.assertAlmostEqual(row["oe_per_share"], 6.0)
        self.assertAlmostEqual(row["oe_yield"], 0.2)
        self.assertAlmostEqual(row["payback_years"], 5.0)
        self.assertAlmostEqual(row["ni_margin"], 0.3)
        self.assertAlmostEqual(row["debt_to_equity"], 0.1)
        self.assertNotIn("ni_to_equity", row)
        self.assertEqual(row["fy"], 2025)

    def test_two_available_years(self):
        # OE/sh 4 and 2 → mean 3. Price 12 → yield 0.25, payback 4.
        # NI 8+4 = 12; revenue 40+20 = 60 → margin 0.2.
        # Debt 6+0 = 6; equity 30+10 = 40 → D/E 0.15.
        statements = {
            2024: _stmt(oe=40, shares=10, ni=8, rev=40, debt=6, equity=30),
            2023: _stmt(oe=20, shares=10, ni=4, rev=20, debt=0, equity=10),
        }
        row = _row([2023, 2024], statements, price=12.0)
        self.assertEqual(row["years"], 2)
        self.assertAlmostEqual(row["oe_per_share"], 3.0)
        self.assertAlmostEqual(row["oe_yield"], 0.25)
        self.assertAlmostEqual(row["payback_years"], 4.0)
        self.assertAlmostEqual(row["ni_margin"], 0.2)
        self.assertAlmostEqual(row["debt_to_equity"], 0.15)

    def test_negative_oe_year_pulls_mean_and_nulls_payback(self):
        # OE/sh 5 and -9 → mean -2. Yield -2/20 = -0.1. Payback null.
        statements = {
            2024: _stmt(oe=50, shares=10, ni=1, rev=10, debt=1, equity=10),
            2023: _stmt(oe=-90, shares=10, ni=1, rev=10, debt=1, equity=10),
        }
        row = _row([2024, 2023], statements, price=20.0)
        self.assertEqual(row["years"], 2)
        self.assertAlmostEqual(row["oe_per_share"], -2.0)
        self.assertAlmostEqual(row["oe_yield"], -0.1)
        self.assertIsNone(row["oe_note"])
        self.assertIsNone(row["payback_years"])

    def test_missing_metric_years_are_skipped_for_that_metric_only(self):
        # OE/sh only 2025 (10) and 2023 (6); 2024 has no shares. Mean (10+6)/2 = 8.
        # NI skips 2024 (None): 10+30 = 40. Revenue skips 2023 (None): 100+50 = 150.
        # Margin 40/150. Equity includes the negative year: 100+100-150 = 50.
        # Debt 10+10+10 = 30. D/E 0.6. Window length stays 3.
        statements = {
            2025: _stmt(oe=100, shares=10, ni=10, rev=100, debt=10, equity=100),
            2024: _stmt(oe=50, shares=None, ni=None, rev=50, debt=10, equity=100),
            2023: _stmt(oe=60, shares=10, ni=30, rev=None, debt=10, equity=-150),
        }
        row = _row([2025, 2024, 2023], statements, price=40.0)
        self.assertEqual(row["years"], 3)
        self.assertAlmostEqual(row["oe_per_share"], 8.0)
        self.assertAlmostEqual(row["oe_yield"], 0.2)
        self.assertAlmostEqual(row["ni_margin"], 40 / 150)
        self.assertAlmostEqual(row["debt_to_equity"], 0.6)

    def test_non_positive_revenue_or_equity_sum_is_null(self):
        statements = {
            2024: _stmt(oe=10, shares=10, ni=5, rev=-40, debt=10, equity=-30),
            2023: _stmt(oe=10, shares=10, ni=5, rev=10, debt=10, equity=10),
        }
        row = _row([2024, 2023], statements, price=10.0)
        self.assertIsNone(row["ni_margin"])  # revenue sum -30
        self.assertIsNone(row["debt_to_equity"])  # equity sum -20

    def test_unknown_debt_state_keeps_ratio_null(self):
        statements = {
            2024: _stmt(oe=10, shares=10, ni=5, rev=20, debt=None, equity=40, debt_state="unknown"),
        }
        row = _row([2024], statements, price=10.0)
        self.assertEqual(row["debt_state"], "unknown")
        self.assertIsNone(row["debt_to_equity"])
        self.assertIsNone(row["no_debt"])
