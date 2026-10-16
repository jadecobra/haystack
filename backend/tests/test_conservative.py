"""Conservative (underestimate) yield, margin, and payback (#59) and screen cache vs seed (#60)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.payback import build_payback
from app.screen import _row_or_reason, load_snapshot


def _stmt(*, oe, shares, ni, rev, debt=1.0, equity=10.0):
    return {
        "owner_earnings": oe,
        "shares": shares,
        "net_income": ni,
        "revenue": rev,
        "debt": debt,
        "equity": equity,
        "debt_state": "positive",
    }


def _row(years, statements, *, price=20.0):
    row, reason = _row_or_reason(
        "T",
        years=years,
        statements=statements,
        company_name="Test Co",
        quote={"price": price, "as_of": "2026-01-01"},
    )
    assert reason is None and row is not None
    return row


class TestConservativeRows(unittest.TestCase):
    def test_growing_earnings_picks_the_lower_average_and_the_longer_payback(self):
        # Latest OE/sh 10, prior 2. Mean 6. Price 20.
        # Yields 0.5 vs 0.3 → cons 0.3 "2y avg".
        # NI 40/100 vs (40+10)/(100+100)=0.25 → cons 0.25 "2y avg".
        # Payback 2 vs 20/6 → longer average.
        statements = {
            2025: _stmt(oe=100, shares=10, ni=40, rev=100),
            2024: _stmt(oe=20, shares=10, ni=10, rev=100),
        }
        row = _row([2024, 2025], statements)
        self.assertAlmostEqual(row["oe_yield"], 0.3)
        self.assertAlmostEqual(row["oe_yield_latest"], 0.5)
        self.assertAlmostEqual(row["oe_yield_cons"], 0.3)
        self.assertEqual(row["oe_yield_basis"], "2y avg")
        self.assertAlmostEqual(row["ni_margin"], 0.25)
        self.assertAlmostEqual(row["ni_margin_latest"], 0.4)
        self.assertAlmostEqual(row["ni_margin_cons"], 0.25)
        self.assertEqual(row["ni_margin_basis"], "2y avg")
        self.assertAlmostEqual(row["payback_years"], 20 / 6)
        self.assertAlmostEqual(row["payback_cons"], 20 / 6)
        self.assertEqual(row["payback_basis"], "2y avg")

    def test_shrinking_earnings_picks_latest(self):
        statements = {
            2025: _stmt(oe=20, shares=10, ni=10, rev=100),
            2024: _stmt(oe=100, shares=10, ni=40, rev=100),
        }
        row = _row([2024, 2025], statements)
        self.assertAlmostEqual(row["oe_yield_latest"], 0.1)
        self.assertAlmostEqual(row["oe_yield"], 0.3)
        self.assertAlmostEqual(row["oe_yield_cons"], 0.1)
        self.assertEqual(row["oe_yield_basis"], "latest")
        self.assertAlmostEqual(row["ni_margin_latest"], 0.1)
        self.assertAlmostEqual(row["ni_margin_cons"], 0.1)
        self.assertEqual(row["ni_margin_basis"], "latest")
        self.assertAlmostEqual(row["payback_cons"], 10.0)
        self.assertEqual(row["payback_basis"], "latest")
        self.assertAlmostEqual(row["payback_years"], 20 / 6)

    def test_non_positive_latest_oe_nulls_payback_cons(self):
        statements = {
            2025: _stmt(oe=-10, shares=10, ni=5, rev=50),
            2024: _stmt(oe=40, shares=10, ni=5, rev=50),
        }
        row = _row([2024, 2025], statements)
        self.assertAlmostEqual(row["oe_per_share"], 1.5)
        self.assertIsNotNone(row["payback_years"])
        self.assertIsNone(row["payback_cons"])
        self.assertIsNone(row["payback_basis"])
        self.assertAlmostEqual(row["oe_yield_latest"], -0.05)
        self.assertEqual(row["oe_yield_basis"], "latest")

    def test_tie_uses_the_average_label(self):
        statements = {
            2025: _stmt(oe=40, shares=10, ni=10, rev=50),
            2024: _stmt(oe=40, shares=10, ni=20, rev=100),
        }
        row = _row([2024, 2025], statements, price=40.0)
        self.assertAlmostEqual(row["oe_yield_latest"], row["oe_yield"])
        self.assertEqual(row["oe_yield_basis"], "2y avg")
        self.assertAlmostEqual(row["ni_margin_latest"], row["ni_margin"])
        self.assertEqual(row["ni_margin_basis"], "2y avg")
        self.assertAlmostEqual(row["payback_cons"], row["payback_years"])
        self.assertEqual(row["payback_basis"], "2y avg")

    def test_only_one_side_present(self):
        # Latest year has no shares, so no latest yield or latest payback.
        # Older year supplies the average.
        statements = {
            2025: _stmt(oe=100, shares=None, ni=None, rev=None),
            2024: _stmt(oe=40, shares=10, ni=10, rev=40),
        }
        row = _row([2024, 2025], statements, price=20.0)
        self.assertIsNone(row["oe_yield_latest"])
        self.assertAlmostEqual(row["oe_yield"], 0.2)
        self.assertAlmostEqual(row["oe_yield_cons"], 0.2)
        self.assertEqual(row["oe_yield_basis"], "2y avg")
        self.assertIsNone(row["ni_margin_latest"])
        self.assertAlmostEqual(row["ni_margin"], 0.25)
        self.assertAlmostEqual(row["ni_margin_cons"], 0.25)
        self.assertEqual(row["ni_margin_basis"], "2y avg")
        self.assertAlmostEqual(row["payback_cons"], row["payback_years"])
        self.assertEqual(row["payback_basis"], "2y avg")

        # Mean OE/sh <= 0 never pays back, so the longer (conservative)
        # payback is null even though the latest year alone would.
        shrinking_mean = {
            2025: _stmt(oe=20, shares=10, ni=1, rev=10),
            2024: _stmt(oe=-40, shares=10, ni=1, rev=10),
        }
        other = _row([2024, 2025], shrinking_mean, price=20.0)
        self.assertIsNone(other["payback_years"])
        self.assertIsNone(other["payback_cons"])
        self.assertIsNone(other["payback_basis"])

    def test_latest_yield_uses_the_same_scale_null(self):
        statements = {2025: _stmt(oe=300, shares=10, ni=1, rev=10)}
        row = _row([2025], statements, price=10.0)
        self.assertIsNone(row["oe_yield"])
        self.assertIsNone(row["oe_yield_latest"])
        self.assertIsNone(row["oe_yield_cons"])
        self.assertIsNone(row["oe_yield_basis"])


class TestPaybackConservative(unittest.TestCase):
    def test_longer_of_latest_and_average(self):
        growing = build_payback(
            price=100.0,
            years=["2025", "2024"],
            rows=[{"metric": "Owner Earnings per Share", "raw": {"2025": 10.0, "2024": 5.0}}],
            treasury_rate_decimal=0.05,
        )
        assert growing is not None
        self.assertEqual(growing["years_at_latest"], 10.0)
        self.assertEqual(growing["years_at_5y_avg"], 13.3)
        self.assertEqual(growing["years_conservative"], 13.3)
        self.assertEqual(growing["conservative_basis"], "2y avg")

        shrinking = build_payback(
            price=100.0,
            years=["2025", "2024"],
            rows=[{"metric": "Owner Earnings per Share", "raw": {"2025": 4.0, "2024": 10.0}}],
            treasury_rate_decimal=None,
        )
        assert shrinking is not None
        self.assertEqual(shrinking["years_conservative"], 25.0)
        self.assertEqual(shrinking["conservative_basis"], "latest")

    def test_tie_and_not_paying_back(self):
        tie = build_payback(
            price=100.0,
            years=["2025", "2024"],
            rows=[{"metric": "Owner Earnings per Share", "raw": {"2025": 10.0, "2024": 10.0}}],
            treasury_rate_decimal=None,
        )
        assert tie is not None
        self.assertEqual(tie["years_conservative"], tie["years_at_latest"])
        self.assertEqual(tie["conservative_basis"], "2y avg")

        dead = build_payback(
            price=50.0,
            years=["2025", "2024"],
            rows=[{"metric": "Owner Earnings per Share", "raw": {"2025": -1.0, "2024": 4.0}}],
            treasury_rate_decimal=0.04,
        )
        assert dead is not None
        self.assertFalse(dead["pays_back"])
        self.assertIsNone(dead["years_conservative"])
        self.assertIsNone(dead["conservative_basis"])


def _snap(built_at, ticker="CACHE"):
    return {
        "universe": "sp500",
        "rows": [{"ticker": ticker, "oe_yield": 0.01}],
        "built_at": built_at,
        "stale": False,
    }


class TestLoadSnapshotPrefersNewerSeed(unittest.TestCase):
    def test_stale_cache_loses_to_newer_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            seed = Path(tmp) / "seed.json"
            public = Path(tmp) / "public.json"
            cache.write_text(json.dumps(_snap("2026-01-01T00:00:00+00:00", "OLD")), encoding="utf-8")
            seed.write_text(json.dumps(_snap("2026-06-01T00:00:00+00:00", "SEED")), encoding="utf-8")
            public.write_text(json.dumps(_snap("2020-01-01T00:00:00+00:00", "PUBLIC")), encoding="utf-8")
            with (
                patch("app.screen.CACHE_PATH", cache),
                patch("app.screen.BACKEND_SEED_PATH", seed),
                patch("app.screen.PUBLIC_SEED_PATH", public),
            ):
                got = load_snapshot()
            assert got is not None
            self.assertEqual(got["rows"][0]["ticker"], "SEED")

    def test_cache_wins_when_built_at_is_at_least_the_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            seed = Path(tmp) / "seed.json"
            cache.write_text(json.dumps(_snap("2026-06-01T00:00:00+00:00", "CACHE")), encoding="utf-8")
            seed.write_text(json.dumps(_snap("2026-06-01T00:00:00+00:00", "SEED")), encoding="utf-8")
            with (
                patch("app.screen.CACHE_PATH", cache),
                patch("app.screen.BACKEND_SEED_PATH", seed),
                patch("app.screen.PUBLIC_SEED_PATH", Path(tmp) / "missing.json"),
            ):
                got = load_snapshot()
            assert got is not None
            self.assertEqual(got["rows"][0]["ticker"], "CACHE")

    def test_unparseable_cache_built_at_uses_the_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            seed = Path(tmp) / "seed.json"
            cache.write_text(json.dumps(_snap("not-a-date", "CACHE")), encoding="utf-8")
            seed.write_text(json.dumps(_snap("2026-06-01T00:00:00+00:00", "SEED")), encoding="utf-8")
            with (
                patch("app.screen.CACHE_PATH", cache),
                patch("app.screen.BACKEND_SEED_PATH", seed),
                patch("app.screen.PUBLIC_SEED_PATH", Path(tmp) / "missing.json"),
            ):
                got = load_snapshot()
            assert got is not None
            self.assertEqual(got["rows"][0]["ticker"], "SEED")

    def test_public_seed_still_fills_in_when_cache_and_backend_seed_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / "public.json"
            public.write_text(json.dumps(_snap("2020-01-01T00:00:00+00:00", "PUBLIC")), encoding="utf-8")
            with (
                patch("app.screen.CACHE_PATH", Path(tmp) / "no-cache.json"),
                patch("app.screen.BACKEND_SEED_PATH", Path(tmp) / "no-seed.json"),
                patch("app.screen.PUBLIC_SEED_PATH", public),
            ):
                got = load_snapshot()
            assert got is not None
            self.assertEqual(got["rows"][0]["ticker"], "PUBLIC")
            self.assertTrue(got["stale"])


class NegativeAverageConservativeTests(unittest.TestCase):
    def test_payback_block_null_when_average_oe_negative(self):
        from app.payback import OE_PER_SHARE

        years = ["2025", "2024", "2023"]
        rows = [{"metric": OE_PER_SHARE, "raw": {"2025": 2.0, "2024": -5.0, "2023": -4.0}}]
        block = build_payback(price=50.0, years=years, rows=rows, treasury_rate_decimal=0.05)
        self.assertEqual(block["years_at_latest"], 25.0)
        self.assertIsNone(block["years_at_5y_avg"])
        self.assertIsNone(block["years_conservative"])
        self.assertIsNone(block["conservative_basis"])
