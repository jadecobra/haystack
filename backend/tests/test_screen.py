from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import compute_year
from app.screen import (
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
            prices = {"CHEAP": 10.0, "MID": 50.0, "RICH": 100.0}
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
        cheap = payload["rows"][0]
        self.assertEqual(cheap["ticker"], "CHEAP")
        self.assertAlmostEqual(cheap["oe_per_share"], 40.0)
        self.assertAlmostEqual(cheap["oe_yield"], 4.0)
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

    def test_rank_rows_high_to_low(self):
        ranked = rank_rows(
            [
                {"ticker": "B", "oe_yield": 0.1},
                {"ticker": "A", "oe_yield": 0.5},
                {"ticker": "C", "oe_yield": None},
            ]
        )
        self.assertEqual([r["ticker"] for r in ranked], ["A", "B"])

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
        self.assertEqual(body["rows"][0]["ticker"], "AAPL")

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


if __name__ == "__main__":
    unittest.main()
