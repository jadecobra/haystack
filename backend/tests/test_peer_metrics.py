"""Peer comparison rows for the ticker-page peers table (#56)."""

import unittest

from app import peer_metrics


def _snap_row(ticker: str, **extra):
    row = {
        "ticker": ticker,
        "name": f"{ticker} Inc",
        "oe_yield": 0.05,
        "oe_per_share": 2.0,
        "oe_note": None,
        "price": 40.0,
        "fy": 2025,
        "price_as_of": "2025-01-02",
        "debt": 10.0,
        "debt_state": "positive",
        "payback_years": 20.0,
        "ni_to_equity": 0.15,
        "debt_to_equity": 0.5,
        "no_debt": False,
    }
    row.update(extra)
    return row


def _metric_row(ticker: str, **extra):
    return _snap_row(ticker, **extra)


class TargetsTests(unittest.TestCase):
    def test_excludes_sp500_includes_peers_and_subjects(self):
        cos = {
            "1": {"t": "AAPL", "n": "Apple", "s": 3571, "r": 400e9, "p": ["2", "3"]},
            "2": {"t": "CRWV", "n": "Coreweave", "s": 3571, "r": 2e9},
            "3": {"t": "GME", "n": "GameStop", "s": 5731, "r": 5e9},
            "4": {"t": "TINY", "n": "Tiny", "s": 3571, "r": 1e6, "p": ["2"]},
            "5": {"t": "LONELY", "n": "Lonely", "s": 1000, "r": 50e6},
        }
        data = {"companies": cos, "tickers": {c["t"]: k for k, c in cos.items()}}
        sp500 = {"AAPL"}
        got = peer_metrics.targets(data, sp500)
        # AAPL excluded (S&P). CRWV+GME appear as peers. TINY has p but
        # revenue below floor and is not in anyone's p → excluded. LONELY
        # has no p and is not a peer → excluded.
        self.assertEqual(got, ["CRWV", "GME"])

    def test_subject_with_peers_and_revenue_included(self):
        cos = {
            "1": {"t": "SUBJ", "n": "Subject", "s": 5651, "r": 50e6, "p": ["2"]},
            "2": {"t": "PEER", "n": "Peer", "s": 5651, "r": 80e6},
        }
        data = {"companies": cos}
        self.assertEqual(peer_metrics.targets(data, set()), ["PEER", "SUBJ"])


class BuildTests(unittest.TestCase):
    def test_fail_soft_skips_exceptions_and_exclusions(self):
        def facts(ticker: str):
            if ticker == "BAD":
                raise RuntimeError("boom")
            if ticker == "EMPTY":
                return [], {}, "1", "Empty Co"
            return (
                [2025],
                {
                    2025: {
                        "owner_earnings": 100.0,
                        "shares": 10.0,
                        "equity": 200.0,
                        "net_income": 50.0,
                        "debt": 0.0,
                        "debt_state": "zero",
                    }
                },
                "2",
                "Good Co",
            )

        def quote(ticker: str):
            if ticker == "NOPRICE":
                return None
            return {"price": 20.0, "as_of": "2025-01-02"}

        out = peer_metrics.build(
            ["GOOD", "BAD", "EMPTY", "NOPRICE"],
            fetch_facts=facts,
            fetch_quote=quote,
        )
        self.assertEqual(list(out["rows"]), ["GOOD"])
        self.assertEqual(out["rows"]["GOOD"]["ticker"], "GOOD")
        self.assertEqual(out["rows"]["GOOD"]["name"], "Good Co")
        self.assertIn("note", out)
        self.assertIn("generated", out)


class TableShapeTests(unittest.TestCase):
    def setUp(self):
        self.block = {
            "basis": "sic",
            "group": "Retail",
            "sub_industry": "Retail",
            "fallback": False,
            "total": 2,
            "peers": [
                {"ticker": "CRWV", "name": "Coreweave", "revenue": 2e9},
                {"ticker": "ZZZZ", "name": "Missing Co", "revenue": 1e9},
            ],
            "sic": 3571,
        }
        self.snapshot = {
            "rows": [_snap_row("AAPL", oe_yield=0.03), _snap_row("MSFT", oe_yield=0.04)]
        }
        self.metrics = {
            "rows": {
                "CRWV": _metric_row("CRWV", oe_yield=0.08, name="CoreWeave Inc"),
            }
        }
        self.sic_data = {
            "tickers": {"AAPL": "1"},
            "companies": {"1": {"t": "AAPL", "n": "Apple Inc", "s": 3571, "r": 400e9}},
        }

    def test_current_first_keys_and_flags(self):
        out = peer_metrics.with_rows(
            "AAPL",
            self.block,
            snapshot=self.snapshot,
            metrics=self.metrics,
            sic_data=self.sic_data,
        )
        tickers = [r["ticker"] for r in out["rows"]]
        self.assertEqual(tickers, ["AAPL", "CRWV", "ZZZZ"])
        self.assertEqual([r["current"] for r in out["rows"]], [True, False, False])
        copied = [k for k in peer_metrics.ROW_KEYS if not k.endswith(("_cons", "_basis", "_latest"))]
        for row in out["rows"]:
            for key in copied:
                self.assertIn(key, row)
        dash = out["rows"][2]
        for key in peer_metrics.ROW_KEYS:
            self.assertIn(key, dash)
            self.assertIn("current", row)
            self.assertIn("missing", row)

    def test_sp500_from_snapshot_non_sp_from_metrics(self):
        out = peer_metrics.with_rows(
            "AAPL",
            self.block,
            snapshot=self.snapshot,
            metrics=self.metrics,
            sic_data=self.sic_data,
        )
        aapl, crwv, zzzz = out["rows"]
        self.assertEqual(aapl["oe_yield"], 0.03)
        self.assertIsNone(aapl["missing"])
        self.assertEqual(crwv["oe_yield"], 0.08)
        self.assertEqual(crwv["name"], "CoreWeave Inc")
        self.assertIsNone(crwv["missing"])
        self.assertIsNone(zzzz["oe_yield"])
        self.assertIsNone(zzzz["fy"])
        self.assertEqual(zzzz["debt_state"], "unknown")
        self.assertEqual(zzzz["missing"], peer_metrics.MISSING_REASON)
        self.assertEqual(zzzz["name"], "Missing Co")

    def test_missing_never_dropped(self):
        out = peer_metrics.with_rows(
            "GME",
            {
                **self.block,
                "peers": [{"ticker": "NOSUCH", "name": "No Such"}],
            },
            snapshot={"rows": []},
            metrics={"rows": {}},
            sic_data={"tickers": {}, "companies": {}},
        )
        self.assertEqual(len(out["rows"]), 2)
        for row in out["rows"]:
            self.assertIsNone(row["oe_yield"])
            self.assertIsNone(row["payback_years"])
            self.assertIsNone(row["ni_margin"])
            self.assertIsNone(row["years"])
            self.assertIsNone(row["debt_to_equity"])
            self.assertIsNone(row["fy"])
            self.assertEqual(row["missing"], peer_metrics.MISSING_REASON)


class LoadCacheTests(unittest.TestCase):
    def test_load_empty_file_shape(self):
        peer_metrics.clear_load_cache()
        data = peer_metrics.load()
        self.assertIsInstance(data, dict)
        self.assertIn("rows", data)


if __name__ == "__main__":
    unittest.main()
