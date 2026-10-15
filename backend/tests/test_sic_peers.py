"""SEC SIC peers for non-S&P tickers (#54)."""

import unittest

from app import sic_peers
from app.sources import _safe_peers


def _co(t, sic, rev=None):
    d = {"t": t, "n": f"{t} Inc", "s": sic}
    if rev is not None:
        d["r"], d["y"] = rev, 2025
    return d


def _m(t, sic, rev_m=None):
    return _co(t, sic, None if rev_m is None else rev_m * 1_000_000)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.cos = {
            "1": _m("BIG", 7372, 900),
            "2": _m("MID", 7372, 500),
            "3": _m("SML", 7372, 100),
            "4": _m("NOREV", 7372),
            "5": _m("TINY", 7372, 50),
            "6": _m("LONE", 4911, 10),
            "7": _m("COUSIN", 4912, 30),
            "8": _m("COUSIN2", 4913, 70),
            "9": _m("SOLO", 1000, 5),
            "10": {"t": "NOSIC", "n": "x"},
        }
        for i in range(11, 21):
            self.cos[str(i)] = _m(f"S{i}", 7372, i)
        sic_peers.rank_peers(self.cos)

    def test_same_sic_by_revenue_top8_excludes_self_and_no_revenue(self):
        p = self.cos["4"]["p"]
        self.assertEqual(self.cos["4"]["b"], "sic")
        self.assertEqual(len(p), sic_peers.MAX_PEERS)
        self.assertEqual(p[:4], ["1", "2", "3", "5"])
        self.assertNotIn("4", self.cos["1"]["p"])
        self.assertNotIn("1", self.cos["1"]["p"])

    def test_widens_to_3digit_group(self):
        self.assertEqual(self.cos["6"]["b"], "sic3")
        self.assertEqual(self.cos["6"]["p"], ["8", "7"])

    def test_blank_with_reason(self):
        self.assertNotIn("p", self.cos["9"])
        self.assertIn("$10M", self.cos["9"]["why"])
        self.assertIn("SIC", self.cos["10"]["why"])

    def test_revenue_floor_drops_small_and_missing(self):
        cos = {
            "1": _co("A", 3571, 50_000_000),
            "2": _co("B", 3571, 10_000_000),  # exactly at the floor: kept
            "3": _co("C", 3571, 9_999_999),  # below: dropped
            "4": _co("D", 3571),  # no revenue: dropped
            "5": _co("E", 3572, 20_000_000),
            "6": _co("F", 3571, 30_000_000),
        }
        sic_peers.rank_peers(cos)
        self.assertEqual(cos["4"]["p"], ["1", "6", "2"])
        self.assertEqual(cos["4"]["b"], "sic")
        # A sees only F and B in 3571 (<3), widens to 357x by revenue; C/D never appear.
        self.assertEqual(cos["1"]["b"], "sic3")
        self.assertEqual(cos["1"]["p"], ["6", "5", "2"])
        for co in cos.values():
            self.assertFalse({"3", "4"} & set(co.get("p") or []))

    def test_committed_map_respects_floor(self):
        data = sic_peers.load()
        cos = data["companies"]
        for co in cos.values():
            for c in co.get("p") or []:
                self.assertGreaterEqual(cos[c]["r"], sic_peers.MIN_REVENUE)


class LatestRevenueTests(unittest.TestCase):
    def test_newest_year_wins_max_tag(self):
        frames = {
            2025: {
                "Revenues": [{"cik": 1, "val": 10, "end": "2025-12-31"}],
                "SalesRevenueNet": [{"cik": 1, "val": 12, "end": "2025-12-31"}],
            },
            2024: {
                "Revenues": [
                    {"cik": 1, "val": 99},
                    {"cik": 2, "val": 7, "end": "2024-06-30"},
                ]
            },
        }
        out = sic_peers.latest_revenue(frames)
        self.assertEqual(out[1], (12.0, 2025, "2025-12-31"))
        self.assertEqual(out[2], (7.0, 2024, "2024-06-30"))


class RuntimeTests(unittest.TestCase):
    def test_lookup_and_block(self):
        cos = {
            "1": _co("AAA", 5651, 9e9),
            "2": _co("BBB", 5651, 5e9),
            "3": _co("CCC", 5651, 1e9),
            "4": _co("DDD", 5651),
        }
        sic_peers.rank_peers(cos)
        data = {
            "tickers": {"DDD": "4", "DDD-P": "4"},
            "companies": cos,
            "sics": {"5651": "Retail-Family Clothing Stores"},
        }
        b = sic_peers.sic_peers_for("ddd.p", data)
        self.assertEqual(b["basis"], "sic")
        self.assertEqual(b["sub_industry"], "Retail-Family Clothing Stores")
        self.assertEqual([p["ticker"] for p in b["peers"]], ["AAA", "BBB", "CCC"])
        self.assertEqual(b["peers"][0]["revenue"], 9e9)
        self.assertIsNone(sic_peers.sic_peers_for("ZZZZ", data))

    def test_committed_map_every_ticker_including_sp500(self):
        for t in ("CRWV", "GME"):
            b = _safe_peers(t)
            self.assertIsNotNone(b, t)
            self.assertIn(b["basis"], ("sic", "sic3"))
            self.assertGreaterEqual(len(b["peers"]), 1)
            self.assertLessEqual(len(b["peers"]), sic_peers.MAX_PEERS)
        for t in ("LULU", "AAPL", "JPM", "BRK.B"):  # S&P 500 too: SIC, not GICS
            self.assertIn(_safe_peers(t)["basis"], ("sic", "sic3"), t)

    def test_no_network_at_lookup(self):
        from app import edgar

        orig = edgar._http_get_json
        edgar._http_get_json = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("SEC fetched")
        )
        try:
            self.assertIsNotNone(_safe_peers("GME"))
        finally:
            edgar._http_get_json = orig


if __name__ == "__main__":
    unittest.main()


class UserAgentTests(unittest.TestCase):
    def test_default_is_sec_compliant_and_blank_env_ignored(self):
        import os
        import re

        from app import edgar

        saved = {
            k: os.environ.pop(k, None)
            for k in ("HAYSTACK_SEC_USER_AGENT", "EDGAR_IDENTITY")
        }
        try:
            os.environ["HAYSTACK_SEC_USER_AGENT"] = (
                ""  # unset GitHub secret expands to ""
            )
            ua = edgar.sec_user_agent()
            self.assertEqual(ua, edgar.DEFAULT_SEC_USER_AGENT)
            self.assertRegex(ua, r"^\S.* [^@\s]+@[^@\s]+\.[a-z]{2,}$")
            self.assertNotIn(".local", ua)
            self.assertIsNotNone(re.match(r"[A-Za-z]", ua))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v
