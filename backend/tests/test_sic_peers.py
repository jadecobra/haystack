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
        # D sees A, F, B in 3571 (3 < 5 clear the floor): widens to 357x by revenue.
        self.assertEqual(cos["4"]["p"], ["1", "6", "5", "2"])
        self.assertEqual(cos["4"]["b"], "sic3")
        # A sees only F and B in 3571, widens too; C/D never appear.
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


class WidenThresholdTests(unittest.TestCase):
    def test_five_same_sic_stays_four_widens(self):
        self.assertEqual(sic_peers.MIN_PEERS, 5)
        five = {str(i): _co(f"T{i}", 2834, (i + 1) * 20_000_000) for i in range(6)}
        five["99"] = _co("COUSIN", 2836, 9_000_000_000)
        sic_peers.rank_peers(five)
        self.assertEqual(five["0"]["b"], "sic")  # 5 others in 2834
        self.assertNotIn("99", five["0"]["p"])
        four = {str(i): _co(f"T{i}", 2834, (i + 1) * 20_000_000) for i in range(5)}
        four["98"] = _co("SMALL", 2834, 5_000_000)  # below floor: does not count
        four["99"] = _co("COUSIN", 2836, 9_000_000_000)
        sic_peers.rank_peers(four)
        self.assertEqual(four["0"]["b"], "sic3")  # only 4 others clear the floor
        self.assertEqual(four["0"]["p"][0], "99")
        self.assertNotIn("98", four["0"]["p"])


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
            "5": _co("EEE", 5651, 9e6),  # below the floor
            "6": _co("FFF", 5652, 2e9),  # 3-digit cousin
        }
        sic_peers.rank_peers(cos)
        data = {
            "tickers": {"DDD": "4", "DDD-P": "4"},
            "companies": cos,
            "sics": {"5651": "Retail-Family Clothing Stores"},
        }
        b = sic_peers.sic_peers_for("ddd.p", data)
        self.assertEqual(b["basis"], "sic3")  # 3 same-SIC peers < MIN_PEERS (5)
        self.assertEqual(b["group"], "SIC 565x")
        self.assertEqual(b["sub_industry"], "Retail-Family Clothing Stores")
        self.assertEqual(
            [p["ticker"] for p in b["peers"]], ["AAA", "BBB", "FFF", "CCC"]
        )
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


class ApiContractTests(unittest.TestCase):
    def test_fixture_aapl_peers_shape(self):
        import os
        from unittest import mock

        from fastapi.testclient import TestClient

        from app.main import app

        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            r = TestClient(app).get("/analyze/AAPL")
        self.assertEqual(r.status_code, 200)
        p = r.json()["peers"]
        self.assertEqual(p["basis"], "sic")
        self.assertEqual(p["sic"], 3571)
        self.assertEqual(p["total"], len(p["peers"]))
        self.assertNotIn("AAPL", [x["ticker"] for x in p["peers"]])
        self.assertTrue(all(x["revenue"] >= sic_peers.MIN_REVENUE for x in p["peers"]))


class SecDiskCacheTests(unittest.TestCase):
    def test_submissions_and_frames_round_trip_without_a_second_fetch(self):
        import json
        import tempfile

        calls: list[str] = []

        def fetch(url: str):
            calls.append(url)
            return {"url": url, "sic": "7372"}

        sub = sic_peers.SUBMISSIONS_URL.format(cik=320193)
        frame = sic_peers.FRAMES_URL.format(tag="Revenues", year=2025)
        other = sic_peers.TICKERS_URL
        with tempfile.TemporaryDirectory() as tmp:
            cached = sic_peers.disk_cached_fetch(fetch, sic_peers.Path(tmp))
            self.assertEqual(cached(sub)["sic"], "7372")
            self.assertEqual(cached(frame)["url"], frame)
            self.assertEqual(cached(other)["url"], other)
            self.assertEqual(cached(other)["url"], other)
            self.assertEqual(cached(sub)["sic"], "7372")
            self.assertEqual(cached(frame)["url"], frame)
            self.assertEqual(calls, [sub, frame, other, other])
            written = json.loads(
                (sic_peers.Path(tmp) / "submissions" / "CIK0000320193.json").read_text()
            )
            self.assertEqual(written["sic"], "7372")
            self.assertTrue(
                (sic_peers.Path(tmp) / "frames" / "Revenues-CY2025.json").is_file()
            )

    def test_corrupt_cache_refetches(self):
        import tempfile

        calls: list[str] = []

        def fetch(url: str):
            calls.append(url)
            return {"ok": True}

        sub = sic_peers.SUBMISSIONS_URL.format(cik=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = sic_peers.Path(tmp) / "submissions" / "CIK0000000001.json"
            path.parent.mkdir()
            path.write_text("not-json", encoding="utf-8")
            cached = sic_peers.disk_cached_fetch(fetch, sic_peers.Path(tmp))
            self.assertEqual(cached(sub), {"ok": True})
            self.assertEqual(calls, [sub])
