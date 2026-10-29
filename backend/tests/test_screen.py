from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import screen
from app.classification import OE_BASIS_FINANCIAL, is_financial_company
from app.main import app
from app.metrics import compute_year
from app.screen import (
    OE_NOTE_NO_NI,
    build_payload,
    load_universe,
    rank_rows,
    screen_build,
    write_snapshot,
)


def _stmt(*, oe: float, shares: float) -> dict:
    return {
        "revenue": 100.0,
        "net_income": 10.0,
        "equity": 50.0,
        "assets": 80.0,
        "total_liabilities": 30.0,
        "debt": 20.0,
        "owner_earnings": oe,
        "dividends": 1.0,
        "shares": shares,
        "cash": 5.0,
    }


class ScreenRankingTests(unittest.TestCase):
    def test_universe_is_sp500_uppercase(self):
        tickers = load_universe()
        self.assertGreaterEqual(len(tickers), 500)
        self.assertLessEqual(len(tickers), 510)
        self.assertEqual(tickers, [t.upper() for t in tickers])
        self.assertIn("AAPL", tickers)
        self.assertNotIn("IWM", tickers)

    def test_yield_matches_analyze_ratio_and_ranks_high_to_low(self):
        stmt = _stmt(oe=200.0, shares=10.0)
        close = 50.0
        expected = compute_year(stmt, None, previous_close=close)[
            "Owner Earnings / Last Close Price"
        ]
        self.assertAlmostEqual(expected, (200.0 / 10.0) / 50.0)

        def facts(ticker: str):
            table = {
                "CHEAP": ( [2024], {2024: _stmt(oe=400.0, shares=10.0)}, "1", "Cheap Co" ),
                "MID": ( [2024], {2024: _stmt(oe=200.0, shares=10.0)}, "2", "Mid Co" ),
                "RICH": ( [2023], {2023: _stmt(oe=50.0, shares=10.0)}, "3", "Rich Co" ),
                "SKIP": ( [2024], {2024: _stmt(oe=100.0, shares=10.0)}, "4", "Skip Co" ),
            }
            return table[ticker]

        def quote(ticker: str):
            if ticker == "SKIP":
                return None
            prices = {"CHEAP": 100.0, "MID": 100.0, "RICH": 100.0}
            return {"price": prices[ticker], "as_of": "2026-09-16"}

        payload = build_payload(
            ["RICH", "CHEAP", "SKIP", "MID"],
            fetch_facts=facts,
            fetch_quote=quote,
            built_at="2026-09-17T02:00:00+00:00",
        )
        tickers = [r["ticker"] for r in payload["rows"]]
        self.assertEqual(tickers, ["CHEAP", "MID", "RICH"])
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["universe"], "sp500")
        # Legacy fixtures omit debt_state; 20.0 debt defaults to positive.
        self.assertEqual(payload["rows"][0]["debt"], 20.0)
        self.assertEqual(payload["rows"][0]["debt_state"], "positive")
        self.assertEqual(
            payload["meta"]["debt_coverage"],
            {
                "zero": 0,
                "positive": 3,
                "unknown": 0,
                "n/a": 0,
                "unknown_tickers": [],
            },
        )
        cheap = payload["rows"][0]
        self.assertEqual(cheap["ticker"], "CHEAP")
        self.assertAlmostEqual(cheap["oe_per_share"], 40.0)
        self.assertAlmostEqual(cheap["oe_yield"], 0.4)
        self.assertEqual(cheap["fy"], 2024)
        self.assertEqual(cheap["price_as_of"], "2026-09-16")
        self.assertEqual(payload["price_as_of"], "2026-09-16")
        for key in (
            "ticker",
            "name",
            "oe_yield",
            "oe_per_share",
            "price",
            "fy",
            "price_as_of",
        ):
            self.assertIn(key, cheap)

    def test_debt_coverage_counts_and_unknown_tickers(self):
        def facts(ticker: str):
            by_ticker = {
                "ZERO": (_stmt(oe=100.0, shares=10.0) | {"debt": 0.0, "debt_state": "zero"}),
                "LEV": (_stmt(oe=300.0, shares=10.0) | {"debt": 50.0, "debt_state": "positive"}),
                "NONE": (_stmt(oe=200.0, shares=10.0) | {"debt": None}),
                "OLDZERO": (_stmt(oe=50.0, shares=10.0) | {"debt": 0.0}),
            }
            stmt = by_ticker[ticker]
            return ([2024], {2024: stmt}, "1", ticker)

        def quote(_ticker: str):
            return {"price": 100.0, "as_of": "2026-09-16"}

        payload = build_payload(
            ["NONE", "LEV", "ZERO", "OLDZERO"],
            fetch_facts=facts,
            fetch_quote=quote,
            built_at="2026-09-17T02:00:00+00:00",
        )
        by_ticker = {row["ticker"]: row for row in payload["rows"]}
        self.assertEqual(by_ticker["ZERO"]["debt"], 0.0)
        self.assertEqual(by_ticker["ZERO"]["debt_state"], "zero")
        self.assertEqual(by_ticker["LEV"]["debt_state"], "positive")
        self.assertIsNone(by_ticker["NONE"]["debt"])
        self.assertEqual(by_ticker["NONE"]["debt_state"], "unknown")
        self.assertEqual(by_ticker["OLDZERO"]["debt_state"], "zero")
        self.assertEqual(
            payload["meta"]["debt_coverage"],
            {
                "zero": 2,
                "positive": 1,
                "unknown": 1,
                "n/a": 0,
                "unknown_tickers": ["NONE"],
            },
        )

    def test_financials_sector_is_debt_na(self):
        def facts(ticker: str):
            stmt = _stmt(oe=100.0, shares=10.0) | {
                "debt": 40.0,
                "debt_state": "positive",
            }
            return [2024], {2024: stmt}, "1", ticker

        def quote(_ticker: str):
            return {"price": 100.0, "as_of": "2026-09-16"}

        payload = build_payload(
            ["JPM", "AAPL", "ORPHAN"],
            fetch_facts=facts,
            fetch_quote=quote,
            built_at="2026-09-17T02:00:00+00:00",
            sectors={"JPM": "Financials", "AAPL": "Information Technology"},
        )
        by_ticker = {row["ticker"]: row for row in payload["rows"]}
        self.assertEqual(by_ticker["JPM"]["debt"], 40.0)
        self.assertEqual(by_ticker["JPM"]["debt_state"], "n/a")
        self.assertEqual(by_ticker["AAPL"]["debt_state"], "positive")
        # Missing from the sectors map stays non-financial.
        self.assertEqual(by_ticker["ORPHAN"]["debt_state"], "positive")
        self.assertEqual(payload["meta"]["debt_coverage"]["n/a"], 1)
        self.assertEqual(payload["meta"]["debt_coverage"]["positive"], 2)

    def test_skips_pathological_yield(self):
        def facts(ticker: str):
            return [2024], {2024: _stmt(oe=400.0, shares=10.0)}, "1", "Bad Co"

        def quote(ticker: str):
            return {"price": 10.0, "as_of": "2026-09-16"}  # yield 4.0 → blank OE

        payload = build_payload(
            ["BAD"],
            fetch_facts=facts,
            fetch_quote=quote,
            built_at="2026-09-17T02:00:00+00:00",
        )
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["ranked"], 0)
        self.assertEqual(payload["skipped"], 0)
        row = payload["rows"][0]
        self.assertIsNone(row["oe_yield"])
        self.assertIsNone(row["payback_years"])
        self.assertIn("scale", row["oe_note"])

    def test_financial_net_income_basis_keeps_yield_window(self):
        self.assertTrue(is_financial_company("JPM"))
        self.assertTrue(is_financial_company("NOTINSP500", sic=6021))
        self.assertTrue(is_financial_company("NOTINSP500", sic=6799))
        self.assertFalse(is_financial_company("NOTINSP500", sic=6798))
        self.assertFalse(is_financial_company("NOTINSP500", sic=5812))
        self.assertFalse(is_financial_company("AAPL"))
        self.assertFalse(is_financial_company("AAPL", sic=6021))

        def facts(ticker: str):
            if ticker == "NONI":
                missing = _stmt(oe=0.0, shares=10.0) | {"net_income": None, "owner_earnings": None}
                return [2024], {2024: missing}, "2", "No NI Bank"
            # JPM: latest yield 10%, two-year mean 25% → conservative "latest".
            # AAPL: latest yield 40%, two-year mean 25% → conservative "2y avg".
            if ticker == "AAPL":
                latest = _stmt(oe=400.0, shares=10.0) | {"net_income": 400.0}
                prior = _stmt(oe=100.0, shares=10.0) | {"net_income": 100.0}
                return [2024, 2023], {2024: latest, 2023: prior}, "3", "Apple"
            latest = _stmt(oe=100.0, shares=10.0) | {"net_income": 100.0}
            prior = _stmt(oe=400.0, shares=10.0) | {"net_income": 400.0}
            return [2024, 2023], {2024: latest, 2023: prior}, "1", "JPMorgan"

        def quote(_ticker: str):
            return {"price": 100.0, "as_of": "2026-09-16"}

        payload = build_payload(
            ["JPM", "NONI", "AAPL"],
            fetch_facts=facts,
            fetch_quote=quote,
            built_at="2026-09-17T02:00:00+00:00",
            sectors={"JPM": "Financials", "NONI": "Financials", "AAPL": "Information Technology"},
        )
        by_ticker = {row["ticker"]: row for row in payload["rows"]}
        jpm = by_ticker["JPM"]
        self.assertEqual(jpm["oe_basis_note"], OE_BASIS_FINANCIAL)
        self.assertEqual(jpm["oe_yield_basis"], "latest")
        self.assertAlmostEqual(jpm["oe_yield_cons"], 0.10)
        self.assertAlmostEqual(jpm["oe_yield"], 0.25)
        self.assertIsNone(jpm["oe_note"])
        self.assertIsNone(by_ticker["AAPL"]["oe_basis_note"])
        self.assertEqual(by_ticker["AAPL"]["oe_yield_basis"], "2y avg")
        noni = by_ticker["NONI"]
        self.assertIsNone(noni["oe_yield"])
        self.assertEqual(noni["oe_note"], OE_NOTE_NO_NI)
        self.assertEqual(noni["oe_basis_note"], OE_BASIS_FINANCIAL)
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["ranked"] + sum(1 for r in payload["rows"] if r["oe_yield"] is None), payload["count"])

    def test_non_sp_financial_sic_sets_basis_note(self):
        def facts(_ticker: str):
            latest = _stmt(oe=50.0, shares=10.0) | {"net_income": 50.0}
            prior = _stmt(oe=200.0, shares=10.0) | {"net_income": 200.0}
            return [2024, 2023], {2024: latest, 2023: prior}, "1", "Regional Bank"

        def quote(_ticker: str):
            return {"price": 25.0, "as_of": "2026-09-16"}

        with patch("app.classification.is_financial_company", return_value=True):
            payload = build_payload(
                ["REGNAL"],
                fetch_facts=facts,
                fetch_quote=quote,
                built_at="2026-09-17T02:00:00+00:00",
                sectors={},
            )
        row = payload["rows"][0]
        self.assertEqual(row["oe_basis_note"], OE_BASIS_FINANCIAL)
        self.assertEqual(row["oe_yield_basis"], "latest")
        self.assertAlmostEqual(row["oe_yield_cons"], 0.2)

    def test_rank_rows_high_to_low(self):
        ranked = rank_rows(
            [
                {"ticker": "B", "oe_yield": 0.1},
                {"ticker": "A", "oe_yield": 0.5},
                {"ticker": "C", "oe_yield": None},
            ]
        )
        self.assertEqual([r["ticker"] for r in ranked], ["A", "B", "C"])

    def test_fail_soft_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "sp500-oe-yield.json"
            prior = {
                "universe": "sp500",
                "count": 1,
                "rows": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "oe_yield": 0.04,
                        "oe_per_share": 6.0,
                        "price": 150.0,
                        "fy": 2024,
                        "price_as_of": "2026-09-16",
                    }
                ],
                "built_at": "2026-09-16T22:00:00+00:00",
                "stale": False,
                "error": None,
            }
            cache.write_text(json.dumps(prior), encoding="utf-8")

            def boom(_ticker: str):
                raise RuntimeError("network down")

            with (
                patch("app.screen.CACHE_PATH", cache),
                patch("app.screen.CACHE_DIR", Path(tmp)),
                patch("app.screen.BACKEND_SEED_PATH", Path(tmp) / "missing-seed.json"),
                patch("app.screen.PUBLIC_SEED_PATH", Path(tmp) / "missing-public.json"),
            ):
                kept = screen_build(
                    ["AAPL"],
                    fail_soft=True,
                    fetch_facts=boom,
                    fetch_quote=lambda _t: {"price": 1.0, "as_of": "2026-09-16"},
                )
            self.assertTrue(kept["stale"])
            self.assertEqual(kept["rows"][0]["ticker"], "AAPL")
            self.assertIn("rebuild failed", kept["error"])


class ScreenApiTests(unittest.TestCase):
    def test_get_serves_seed_shape(self):
        client = TestClient(app)
        response = client.get("/screen/sp500-oe-yield")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["universe"], "sp500")
        self.assertIsInstance(body["rows"], list)
        self.assertGreaterEqual(len(body["rows"]), 1)
        self.assertIn("built_at", body)
        row0 = body["rows"][0]
        for key in ("ticker", "oe_yield", "oe_per_share", "price", "fy"):
            self.assertIn(key, row0)

    def test_rebuild_requires_token(self):
        client = TestClient(app)
        response = client.post("/screen/sp500-oe-yield/rebuild")
        self.assertEqual(response.status_code, 403)

    def test_rebuild_with_token_uses_fail_soft(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "sp500-oe-yield.json"
            write_snapshot_payload = {
                "universe": "sp500",
                "count": 1,
                "skipped": 0,
                "built_at": "2026-09-16T22:00:00+00:00",
                "price_as_of": "2026-09-16",
                "stale": False,
                "error": None,
                "rows": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "oe_yield": 0.04,
                        "oe_per_share": 6.0,
                        "price": 150.0,
                        "fy": 2024,
                        "price_as_of": "2026-09-16",
                    }
                ],
            }
            with (
                patch("app.screen.CACHE_PATH", cache),
                patch("app.screen.CACHE_DIR", Path(tmp)),
                patch("app.screen.BACKEND_SEED_PATH", Path(tmp) / "seed.json"),
                patch("app.screen.PUBLIC_SEED_PATH", Path(tmp) / "public.json"),
                patch.dict(os.environ, {"SCREEN_REBUILD_TOKEN": "secret"}, clear=False),
            ):
                write_snapshot(write_snapshot_payload)

                def boom(_t: str):
                    raise RuntimeError("no net")

                with (
                    patch("app.screen._live_facts", boom),
                    patch("app.screen._live_quote", lambda _t: None),
                ):
                    client = TestClient(app)
                    response = client.post(
                        "/screen/sp500-oe-yield/rebuild",
                        headers={"Authorization": "Bearer secret"},
                    )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get("stale"))




class TestSectorColumns(unittest.TestCase):
    def test_columns_and_coverage(self):
        from app.screen import column_coverage, sector_columns

        cols = sector_columns(
            {2024: {"equity": 200.0, "net_income": 50.0, "revenue": 100.0, "debt": 100.0}},
            years=[2024], price=100.0, oe_per_share=5.0, debt_state="positive",
        )
        self.assertEqual(cols["payback_years"], 20.0)
        self.assertEqual(cols["ni_margin"], 0.5)
        self.assertEqual(cols["debt_to_equity"], 0.5)
        self.assertIs(cols["no_debt"], False)
        self.assertEqual(cols["years"], 1)
        neg = sector_columns(
            {2024: {"equity": -10.0, "net_income": 5.0, "revenue": 20.0}},
            years=[2024], price=100.0, oe_per_share=-1.0, debt_state="unknown",
        )
        self.assertIsNone(neg["payback_years"])
        self.assertEqual(neg["ni_margin"], 0.25)
        self.assertIsNone(neg["debt_to_equity"])
        self.assertIsNone(neg["no_debt"])
        self.assertEqual(neg["years"], 1)
        zero = sector_columns(
            {2024: {"equity": 10.0, "net_income": 1.0, "revenue": 10.0, "debt": 0.0}},
            years=[2024], price=10.0, oe_per_share=1.0, debt_state="zero",
        )
        self.assertTrue(zero["no_debt"])
        self.assertEqual(zero["debt_to_equity"], 0.0)
        cov = column_coverage([cols, neg])
        self.assertEqual(cov["payback_years"], {"known": 1, "unknown": 1})
        self.assertEqual(cov["no_debt"], {"known": 1, "unknown": 1})


class ScreenCoverageTests(unittest.TestCase):
    """#52: every S&P map ticker gets a row or an explicit exclusion reason."""

    def test_bank_without_oe_is_a_row_with_blanks(self):
        stmt = {
            "net_income": 57048e6, "equity": 362438e6, "shares": 2781.5e6,
            "revenue": 182447e6, "debt": 400e9, "owner_earnings": None,
        }

        payload = build_payload(
            ["JPM", "MULTI", "NEW", "NOQ"],
            fetch_facts=lambda t: {
                "JPM": ([2025], {2025: stmt}, "19617", "JPMorgan Chase & Co"),
                "MULTI": ([2025], {2025: {**stmt, "owner_earnings": 5e9, "shares": None}}, "1", "Multi"),
                "NEW": ([], {}, "2", "New"),
                "NOQ": ([2025], {2025: stmt}, "3", "NoQuote"),
            }[t],
            fetch_quote=lambda t: None if t == "NOQ" else {"price": 331.43, "as_of": "2026-10-14"},
            sectors={"JPM": "Financials"},
            built_at="2026-10-14T22:00:00+00:00",
        )
        rows = {r["ticker"]: r for r in payload["rows"]}
        jpm = rows["JPM"]
        self.assertIsNone(jpm["oe_yield"])
        self.assertIsNone(jpm["payback_years"])
        self.assertAlmostEqual(jpm["ni_margin"], 57048 / 182447)
        self.assertEqual(jpm["years"], 1)
        self.assertNotIn("ni_to_equity", jpm)
        self.assertEqual(jpm["debt_state"], "n/a")
        self.assertIn("no owner earnings", jpm["oe_note"])
        self.assertIn("no share count", rows["MULTI"]["oe_note"])
        self.assertEqual(
            {e["ticker"]: e["reason"] for e in payload["excluded"]},
            {"NEW": screen.EXCLUDE_NO_FACTS, "NOQ": screen.EXCLUDE_NO_PRICE},
        )
        self.assertEqual(payload["count"] + payload["skipped"], 4)

    def test_snapshot_covers_every_map_ticker(self):
        snap = json.loads(screen.BACKEND_SEED_PATH.read_text(encoding="utf-8"))
        if "excluded" not in snap:
            self.skipTest("snapshot predates #52 exclusion reasons")
        have = {r["ticker"] for r in snap["rows"]} | {e["ticker"] for e in snap["excluded"]}
        self.assertEqual(set(load_universe()) - have, set())
        for e in snap["excluded"]:
            self.assertTrue(e.get("reason"), e)

    def test_snapshot_jpm_row_golden(self):
        snap = json.loads(screen.BACKEND_SEED_PATH.read_text(encoding="utf-8"))
        if "excluded" not in snap:
            self.skipTest("snapshot predates #52 exclusion reasons")
        jpm = next(r for r in snap["rows"] if r["ticker"] == "JPM")
        self.assertEqual(jpm["sector"], "Financials")
        self.assertEqual(jpm["sub_industry"], "Diversified Banks")
        self.assertGreaterEqual(jpm["fy"], 2025)
        if "ni_margin" in jpm:  # #58: up-to-5y NI / revenue margin
            self.assertGreater(jpm["ni_margin"], 0.15)
            self.assertLess(jpm["ni_margin"], 0.50)
        else:  # seed predates #58
            self.assertGreater(jpm["ni_to_equity"], 0.10)
            self.assertLess(jpm["ni_to_equity"], 0.25)


if __name__ == "__main__":
    unittest.main()
