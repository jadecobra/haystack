"""Golden / mapping tests for SEC companyfacts → statements."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from unittest import mock

from app.tags import TAG_PREFS
from app.edgar import (
    entity_name,
    map_companyfacts_to_statements,
    split_adjusted_shares,
    _http_get_json,
    _is_annual,
    _series_for_tags,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNIPPET = FIXTURES / "aapl_companyfacts_snippet.json"
CPRT_SHARES = FIXTURES / "cprt_shares_companyfacts.json"
CPRT_REVENUE = FIXTURES / "cprt_revenue_companyfacts.json"
NVDA_SHARES = FIXTURES / "nvda_shares_companyfacts.json"

AAPL_BALLPARK = {
    2024: {"revenue": (380e9, 410e9), "net_income": (85e9, 105e9)},
    2023: {"revenue": (370e9, 400e9), "net_income": (90e9, 105e9)},
}
MSFT_BALLPARK = {
    2024: {"revenue": (220e9, 260e9), "net_income": (80e9, 100e9)},
    2023: {"revenue": (200e9, 230e9), "net_income": (65e9, 85e9)},
}


def _in_range(val, lo, hi) -> bool:
    return val is not None and lo <= val <= hi


class TestTagMappingSnippet(unittest.TestCase):
    def test_snippet_entity_name(self):
        payload = json.loads(SNIPPET.read_text(encoding="utf-8"))
        self.assertEqual(entity_name(payload), "Apple Inc.")
        self.assertIsNone(entity_name({}))
        self.assertIsNone(entity_name({"entityName": "  "}))

    def test_map_snippet_annual_only(self):
        payload = json.loads(SNIPPET.read_text(encoding="utf-8"))
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(years[:2], [2024, 2023])
        s24 = statements[2024]
        self.assertEqual(s24["revenue"], 391035000000)
        self.assertEqual(s24["net_income"], 93736000000)
        self.assertEqual(s24["equity"], 56950000000)
        self.assertEqual(s24["assets"], 364980000000)
        self.assertEqual(s24["total_liabilities"], 308030000000)
        self.assertEqual(s24["cash"], 29943000000)
        self.assertEqual(s24["dividends"], 15234000000)
        self.assertEqual(s24["owner_earnings"], 118254000000 - 9447000000)
        self.assertAlmostEqual(s24["shares"], 15340883000)
        self.assertNotEqual(s24["revenue"], 85777000000)

    def test_missing_tag_is_null(self):
        payload = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2024-12-31",
                                    "val": 100,
                                    "fy": 2024,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2025-01-01",
                                }
                            ]
                        }
                    }
                }
            }
        }
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(years, [2024])
        self.assertEqual(statements[2024]["net_income"], 100)
        self.assertIsNone(statements[2024]["revenue"])
        self.assertIsNone(statements[2024]["owner_earnings"])

    def test_map_returns_all_core_years(self):
        usd = [
            {
                "end": f"{y}-12-31",
                "val": float(y),
                "fy": y,
                "fp": "FY",
                "form": "10-K",
                "filed": f"{y + 1}-01-01",
            }
            for y in range(2015, 2025)
        ]
        payload = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": usd}},
                    "NetIncomeLoss": {"units": {"USD": usd}},
                }
            }
        }
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(years, list(range(2024, 2014, -1)))
        self.assertEqual(len(statements), 10)


class TestLiveGolden(unittest.TestCase):
    def _live_or_skip(self, ticker: str):
        from app import edgar

        cik_map = {"AAPL": "320193", "MSFT": "789019"}
        cache = edgar._cache_path(cik_map.get(ticker, "0"))
        try:
            return edgar.statements_for_ticker(ticker)
        except Exception as exc:
            if cache.is_file():
                raise
            self.skipTest(f"network/edgar unavailable for {ticker}: {exc}")

    def test_aapl_live_ballpark(self):
        years, statements, cik, company_name = self._live_or_skip("AAPL")
        self.assertTrue(cik)
        self.assertEqual(company_name, "Apple Inc.")
        self.assertGreater(len(years), 5)
        checked = 0
        for y, fields in AAPL_BALLPARK.items():
            if y not in statements:
                continue
            for field, (lo, hi) in fields.items():
                val = statements[y].get(field)
                self.assertTrue(
                    _in_range(val, lo, hi),
                    f"AAPL {y} {field}={val} not in [{lo}, {hi}]",
                )
                checked += 1
        if checked == 0:
            self.skipTest("no overlapping ballpark years in live AAPL facts")

    def test_msft_live_ballpark(self):
        years, statements, cik, _company_name = self._live_or_skip("MSFT")
        self.assertTrue(cik)
        self.assertGreater(len(years), 5)
        checked = 0
        for y, fields in MSFT_BALLPARK.items():
            if y not in statements:
                continue
            for field, (lo, hi) in fields.items():
                val = statements[y].get(field)
                self.assertTrue(
                    _in_range(val, lo, hi),
                    f"MSFT {y} {field}={val} not in [{lo}, {hi}]",
                )
                checked += 1
        if checked == 0:
            self.skipTest("no overlapping ballpark years in live MSFT facts")


class TestCompanyfacts404(unittest.TestCase):
    def test_http_404_is_unknown_ticker_not_url(self):
        class Resp:
            status_code = 404

            def raise_for_status(self):
                raise AssertionError("404 must not call raise_for_status")

            def json(self):
                raise AssertionError("404 must not parse body")

        class Client:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                return Resp()

        with mock.patch("app.edgar.httpx.Client", Client):
            with self.assertRaises(ValueError) as ctx:
                _http_get_json(
                    "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000000.json"
                )
        self.assertIn("unknown ticker", str(ctx.exception).lower())
        self.assertNotIn("sec.gov", str(ctx.exception).lower())


def _share_entry(
    *,
    end: str,
    val: float,
    fy: int,
    filed: str,
    start: str | None = None,
    form: str = "10-K",
    fp: str = "FY",
) -> dict:
    entry: dict = {
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }
    if start is not None:
        entry["start"] = start
    return entry


def _shares_payload(entries: list[dict], *, ratio_entries: list[dict] | None = None) -> dict:
    us_gaap: dict = {
        "WeightedAverageNumberOfDilutedSharesOutstanding": {
            "units": {"shares": entries}
        }
    }
    if ratio_entries is not None:
        us_gaap["StockholdersEquityNoteStockSplitConversionRatio1"] = {
            "units": {"pure": ratio_entries}
        }
    return {"facts": {"us-gaap": us_gaap}}


class TestSplitAdjustedSharesSynthetic(unittest.TestCase):
    def test_latest_filed_restatement_wins(self):
        # Same period restated 2x in a later filing; fy pick stays on original fy.
        entries = [
            _share_entry(
                start="2021-01-01",
                end="2021-12-31",
                val=100.0,
                fy=2021,
                filed="2022-02-01",
            ),
            _share_entry(
                start="2021-01-01",
                end="2021-12-31",
                val=200.0,
                fy=2022,
                filed="2023-02-01",
            ),
            _share_entry(
                start="2022-01-01",
                end="2022-12-31",
                val=200.0,
                fy=2022,
                filed="2023-02-01",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2021], 200.0)
        self.assertAlmostEqual(shares[2022], 200.0)

    def test_later_thousand_fold_scale_error_does_not_win(self):
        # CPRT FY2012: 131428000 in the 2012 and 2013 10-Ks, then 131428 in the
        # 2014 10-K. The last figure is a unit scale error, not a restatement.
        entries = [
            _share_entry(
                start="2011-08-01",
                end="2012-07-31",
                val=131428000.0,
                fy=2012,
                filed="2012-10-01",
            ),
            _share_entry(
                start="2011-08-01",
                end="2012-07-31",
                val=131428000.0,
                fy=2013,
                filed="2013-09-30",
            ),
            _share_entry(
                start="2011-08-01",
                end="2012-07-31",
                val=131428.0,
                fy=2014,
                filed="2015-10-01",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2012], 131428000.0)

    def test_unrestated_older_year_gets_implied_factor(self):
        # FY2020 never restated; FY2021 restated 4x on a later filing → factor applies back.
        entries = [
            _share_entry(
                start="2019-01-01",
                end="2019-12-31",
                val=100.0,
                fy=2020,
                filed="2020-02-01",
            ),
            _share_entry(
                start="2019-01-01",
                end="2019-12-31",
                val=100.0,
                fy=2021,
                filed="2021-02-01",
            ),
            _share_entry(
                start="2020-01-01",
                end="2020-12-31",
                val=100.0,
                fy=2021,
                filed="2021-02-01",
            ),
            _share_entry(
                start="2020-01-01",
                end="2020-12-31",
                val=400.0,
                fy=2022,
                filed="2022-02-01",
            ),
            _share_entry(
                start="2021-01-01",
                end="2021-12-31",
                val=400.0,
                fy=2022,
                filed="2022-02-01",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2020], 400.0)
        self.assertAlmostEqual(shares[2021], 400.0)
        self.assertAlmostEqual(shares[2022], 400.0)

    def test_small_revision_is_not_a_split(self):
        entries = [
            _share_entry(
                start="2020-01-01",
                end="2020-12-31",
                val=100.0,
                fy=2020,
                filed="2021-02-01",
            ),
            _share_entry(
                start="2020-01-01",
                end="2020-12-31",
                val=100.0,
                fy=2021,
                filed="2022-02-01",
            ),
            _share_entry(
                start="2021-01-01",
                end="2021-12-31",
                val=100.0,
                fy=2021,
                filed="2022-02-01",
            ),
            _share_entry(
                start="2021-01-01",
                end="2021-12-31",
                val=103.0,
                fy=2022,
                filed="2023-02-01",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        # Latest restatement wins for 2021; r=1.03 is not a split so 2020 stays 100.
        self.assertAlmostEqual(shares[2021], 103.0)
        self.assertAlmostEqual(shares[2020], 100.0)

    def test_split_before_10k_is_not_applied_twice(self):
        # 10:1 split before the FY2025 10-K. The 10-K already restates annual
        # shares. A later 10-Q restates the prior-year quarter. Annual stays
        # on the 10-K basis (NFLX / NOW / TPL).
        entries = [
            _share_entry(
                start="2024-01-01",
                end="2024-12-31",
                val=100.0,
                fy=2024,
                filed="2025-02-01",
            ),
            _share_entry(
                start="2024-01-01",
                end="2024-12-31",
                val=1000.0,
                fy=2025,
                filed="2026-02-15",
            ),
            _share_entry(
                start="2025-01-01",
                end="2025-12-31",
                val=1000.0,
                fy=2025,
                filed="2026-02-15",
            ),
            _share_entry(
                start="2025-01-01",
                end="2025-03-31",
                val=250.0,
                fy=2025,
                filed="2025-04-20",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2025-01-01",
                end="2025-03-31",
                val=2500.0,
                fy=2026,
                filed="2026-04-20",
                form="10-Q",
                fp="Q1",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2024], 1000.0)
        self.assertAlmostEqual(shares[2025], 1000.0)

    def test_split_after_10k_uses_later_10q_comparatives(self):
        # Last 10-K is pre-split. A later 10-Q restates the comparative quarter 4x
        # (BKNG / CRWD). Annual shares, filed before B, are multiplied.
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=100.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=100.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2023], 400.0)

    def test_reverse_split_after_10k(self):
        # 1:3 reverse. Only the later 10-Q shows the restated comparative.
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=300.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=90.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=30.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2023], 100.0)

    def test_scale_glitch_round_trip_is_ignored(self):
        # One filing reports shares ×1000, the next filing is back to normal.
        # 1000 is outside 1/60..60, so it is not a split.
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=100.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25000.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2024,
                filed="2024-08-01",
                form="10-Q",
                fp="Q2",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2023], 100.0)

    def test_small_10q_restatement_is_not_a_split(self):
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=100.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=26.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2023], 100.0)

    def test_split_tag_without_share_count_change_is_ignored(self):
        # Ratio tag says 10x; 10-Q comparatives are unchanged, so no adjustment.
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=100.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
        ]
        ratio = [
            {
                "end": "2024-06-01",
                "val": 10.0,
                "fy": 2024,
                "fp": "Q2",
                "form": "10-Q",
                "filed": "2024-08-01",
            }
        ]
        shares = split_adjusted_shares(
            _shares_payload(entries, ratio_entries=ratio)["facts"]["us-gaap"]
        )
        self.assertAlmostEqual(shares[2023], 100.0)

    def test_two_10q_restatements_of_the_same_split_apply_once(self):
        # Two later 10-Qs each restate a comparative 4x. One jump, factor 4.
        entries = [
            _share_entry(
                start="2023-01-01",
                end="2023-12-31",
                val=100.0,
                fy=2023,
                filed="2024-02-01",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=25.0,
                fy=2023,
                filed="2023-05-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=100.0,
                fy=2024,
                filed="2024-05-10",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2023-01-01",
                end="2023-03-31",
                val=100.0,
                fy=2024,
                filed="2024-08-01",
                form="10-Q",
                fp="Q2",
            ),
            _share_entry(
                start="2023-04-01",
                end="2023-06-30",
                val=25.0,
                fy=2023,
                filed="2023-08-01",
                form="10-Q",
                fp="Q2",
            ),
            _share_entry(
                start="2023-04-01",
                end="2023-06-30",
                val=100.0,
                fy=2024,
                filed="2024-08-01",
                form="10-Q",
                fp="Q2",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2023], 400.0)

    def test_two_splits_and_composite_annual_restatement_count_once(self):
        # CPRT-like: 2:1 then 2:1 a year apart. Each 10-Q comparative moves 2x.
        # The later 10-K restates the two-years-ago annual by 4 (both splits).
        # The 4x is the product of the two jumps, not a third split.
        entries = [
            _share_entry(
                start="2019-08-01",
                end="2020-07-31",
                val=100.0,
                fy=2020,
                filed="2020-09-15",
            ),
            _share_entry(
                start="2020-08-01",
                end="2021-07-31",
                val=100.0,
                fy=2021,
                filed="2021-09-15",
            ),
            _share_entry(
                start="2020-08-01",
                end="2021-07-31",
                val=400.0,
                fy=2023,
                filed="2023-09-28",
            ),
            _share_entry(
                start="2021-08-01",
                end="2022-07-31",
                val=100.0,
                fy=2022,
                filed="2022-09-15",
            ),
            _share_entry(
                start="2021-08-01",
                end="2022-07-31",
                val=400.0,
                fy=2023,
                filed="2023-09-28",
            ),
            _share_entry(
                start="2022-08-01",
                end="2023-07-31",
                val=400.0,
                fy=2023,
                filed="2023-09-28",
            ),
            _share_entry(
                start="2021-08-01",
                end="2021-10-31",
                val=25.0,
                fy=2022,
                filed="2021-12-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2021-08-01",
                end="2021-10-31",
                val=50.0,
                fy=2023,
                filed="2022-12-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2022-08-01",
                end="2022-10-31",
                val=50.0,
                fy=2023,
                filed="2022-12-01",
                form="10-Q",
                fp="Q1",
            ),
            _share_entry(
                start="2022-08-01",
                end="2022-10-31",
                val=100.0,
                fy=2024,
                filed="2023-12-01",
                form="10-Q",
                fp="Q1",
            ),
        ]
        shares = split_adjusted_shares(_shares_payload(entries)["facts"]["us-gaap"])
        self.assertAlmostEqual(shares[2020], 400.0)
        self.assertAlmostEqual(shares[2021], 400.0)
        self.assertAlmostEqual(shares[2022], 400.0)
        self.assertAlmostEqual(shares[2023], 400.0)


class TestSplitAdjustedSharesFixtures(unittest.TestCase):
    def test_cprt_shares_stay_near_one_billion(self):
        payload = json.loads(CPRT_SHARES.read_text(encoding="utf-8"))
        _years, statements = map_companyfacts_to_statements(payload)
        seen = [year for year in range(2013, 2027) if statements.get(year, {}).get("shares")]
        self.assertGreaterEqual(len(seen), 10)
        for year in seen:
            shares = statements[year]["shares"]
            self.assertGreaterEqual(shares, 0.90e9, msg=year)
            self.assertLessEqual(shares, 1.10e9, msg=year)

    def test_nvda_shares_stay_in_post_split_band(self):
        payload = json.loads(NVDA_SHARES.read_text(encoding="utf-8"))
        _years, statements = map_companyfacts_to_statements(payload)
        seen = [year for year in range(2010, 2027) if statements.get(year, {}).get("shares")]
        self.assertGreaterEqual(len(seen), 10)
        for year in seen:
            shares = statements[year]["shares"]
            self.assertGreaterEqual(shares, 21e9, msg=year)
            self.assertLessEqual(shares, 27e9, msg=year)


class TestIsAnnualDuration(unittest.TestCase):
    def test_duration_window_and_instant(self):
        base = {"fp": "FY", "form": "10-K", "fy": 2020, "val": 1.0}
        self.assertTrue(
            _is_annual({**base, "start": "2019-08-01", "end": "2020-07-30"})
        )  # 364 days
        self.assertTrue(
            _is_annual({**base, "start": "2019-08-01", "end": "2020-08-06"})
        )  # 371 days
        self.assertFalse(
            _is_annual({**base, "start": "2020-05-01", "end": "2020-07-31"})
        )  # 91 days
        self.assertFalse(
            _is_annual({**base, "start": "2020-02-01", "end": "2020-07-31"})
        )  # 181 days
        self.assertTrue(_is_annual({**base, "end": "2020-07-31"}))  # instant
        self.assertFalse(
            _is_annual({**base, "start": "not-a-date", "end": "2020-07-31"})
        )

    def test_quarterly_fy_falls_through_ladder(self):
        """Earlier tag with only 91-day fp=FY rows yields to a later annual tag."""
        us_gaap = {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "start": "2019-05-01",
                            "end": "2019-07-31",
                            "val": 500_000_000,
                            "fy": 2019,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2019-09-30",
                        }
                    ]
                }
            },
            "RevenueFromContractWithCustomerIncludingAssessedTax": {
                "units": {
                    "USD": [
                        {
                            "start": "2018-08-01",
                            "end": "2019-07-31",
                            "val": 2_041_957_000,
                            "fy": 2019,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2019-09-30",
                        }
                    ]
                }
            },
        }
        series = _series_for_tags(
            us_gaap,
            [
                "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
            ],
        )
        self.assertEqual(series[2019], 2_041_957_000)


def _quarter_facts(spans: list[tuple[str, str, float]], *, fy: int = 2012, filed: str = "2012-10-31") -> list[dict]:
    return [
        {
            "start": start,
            "end": end,
            "val": val,
            "fy": fy,
            "fp": "FY",
            "form": "10-K",
            "filed": filed,
        }
        for start, end, val in spans
    ]


_AAPL_FY2012_DIVIDEND_QUARTERS = [
    ("2011-09-25", "2011-12-31", 0),
    ("2012-01-01", "2012-03-31", 0),
    ("2012-04-01", "2012-06-30", 0),
    ("2012-07-01", "2012-09-29", 2.5e9),
]


class TestQuarterChainPass(unittest.TestCase):
    def test_four_contiguous_quarters_sum_when_no_annual(self):
        us_gaap = {
            "PaymentsOfDividends": {
                "units": {"USD": _quarter_facts(_AAPL_FY2012_DIVIDEND_QUARTERS)}
            }
        }
        series = _series_for_tags(us_gaap, ["PaymentsOfDividends"])
        self.assertEqual(series[2012], 2.5e9)

    def test_earlier_tag_quarter_chain_beats_later_tag_annual(self):
        quarters = _quarter_facts(_AAPL_FY2012_DIVIDEND_QUARTERS)
        annual = {
            "start": "2011-09-25",
            "end": "2012-09-29",
            "val": 9.0e9,
            "fy": 2012,
            "fp": "FY",
            "form": "10-K",
            "filed": "2012-10-31",
        }
        us_gaap = {
            "PaymentsOfDividends": {"units": {"USD": quarters}},
            "PaymentsOfDividendsCommonStock": {"units": {"USD": [annual]}},
        }
        series = _series_for_tags(
            us_gaap,
            ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
        )
        self.assertEqual(series[2012], 2.5e9)

    def test_same_tag_annual_beats_its_quarter_chain(self):
        quarters = _quarter_facts(_AAPL_FY2012_DIVIDEND_QUARTERS)
        annual = {
            "start": "2011-09-25",
            "end": "2012-09-29",
            "val": 9.0e9,
            "fy": 2012,
            "fp": "FY",
            "form": "10-K",
            "filed": "2012-10-31",
        }
        us_gaap = {"PaymentsOfDividends": {"units": {"USD": [*quarters, annual]}}}
        series = _series_for_tags(us_gaap, ["PaymentsOfDividends"])
        self.assertEqual(series[2012], 9.0e9)

    def test_later_tag_annual_fills_year_earlier_tag_lacks(self):
        quarters = _quarter_facts(_AAPL_FY2012_DIVIDEND_QUARTERS[:3])
        annual = {
            "start": "2011-09-25",
            "end": "2012-09-29",
            "val": 9.0e9,
            "fy": 2012,
            "fp": "FY",
            "form": "10-K",
            "filed": "2012-10-31",
        }
        us_gaap = {
            "PaymentsOfDividends": {"units": {"USD": quarters}},
            "PaymentsOfDividendsCommonStock": {"units": {"USD": [annual]}},
        }
        series = _series_for_tags(
            us_gaap,
            ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
        )
        self.assertEqual(series[2012], 9.0e9)

    def test_three_quarters_are_not_a_year(self):
        us_gaap = {
            "PaymentsOfDividends": {
                "units": {"USD": _quarter_facts(_AAPL_FY2012_DIVIDEND_QUARTERS[:3])}
            }
        }
        series = _series_for_tags(us_gaap, ["PaymentsOfDividends"])
        self.assertNotIn(2012, series)

    def test_prefer_shares_does_not_sum_quarters(self):
        us_gaap = {
            "WeightedAverageNumberOfDilutedSharesOutstanding": {
                "units": {
                    "shares": _quarter_facts(
                        [
                            ("2011-09-25", "2011-12-31", 900e6),
                            ("2012-01-01", "2012-03-31", 910e6),
                            ("2012-04-01", "2012-06-30", 920e6),
                            ("2012-07-01", "2012-09-29", 930e6),
                        ]
                    )
                }
            }
        }
        series = _series_for_tags(
            us_gaap,
            ["WeightedAverageNumberOfDilutedSharesOutstanding"],
            prefer_shares=True,
        )
        self.assertNotIn(2012, series)


class TestAresDividendsGolden(unittest.TestCase):
    """ARES #28: PaymentsOfDividends quarter chains beat later Dividends annuals."""

    def test_quarter_chains_beat_equity_statement_dividends(self):
        fy2024 = _quarter_facts(
            [
                ("2024-01-01", "2024-03-31", 16_294_000),
                ("2024-04-01", "2024-06-30", 16_008_000),
                ("2024-07-01", "2024-09-30", 16_242_000),
                ("2024-10-01", "2024-12-31", 16_098_000),
            ],
            fy=2024,
            filed="2025-02-27",
        )
        fy2025 = _quarter_facts(
            [
                ("2025-01-01", "2025-03-31", 21_489_000),
                ("2025-04-01", "2025-06-30", 20_958_000),
                ("2025-07-01", "2025-09-30", 21_095_000),
                ("2025-10-01", "2025-12-31", 21_027_000),
            ],
            fy=2025,
            filed="2026-02-25",
        )
        dividends_annual = [
            _fy_fact("2023-01-01", "2023-12-31", 1_128_911_000, fy=2025, filed="2026-02-25"),
            _fy_fact("2024-01-01", "2024-12-31", 1_457_396_000, fy=2025, filed="2026-02-25"),
            _fy_fact("2025-01-01", "2025-12-31", 2_600_142_000, fy=2025, filed="2026-02-25"),
        ]
        us_gaap = {
            "PaymentsOfDividends": {"units": {"USD": [*fy2024, *fy2025]}},
            "Dividends": {"units": {"USD": dividends_annual}},
        }
        series = _series_for_tags(us_gaap, TAG_PREFS["dividends"])
        self.assertEqual(series[2024], 64_642_000)
        self.assertEqual(series[2025], 84_569_000)


def _fy_fact(
    start: str,
    end: str,
    val: float,
    *,
    fy: int = 2021,
    filed: str = "2022-02-24",
) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "filed": filed,
    }


class TestAnnualEndAnchor(unittest.TestCase):
    """Duration facts for fy=Y must end near E(Y), not a prior-year comparative."""

    def test_exe_like_predecessor_successor_does_not_use_prior_year(self):
        # EXE fy=2021 10-K: short predecessor, 324-day successor, prior-year annuals.
        facts = [
            _fy_fact("2021-01-01", "2021-02-09", -100e6),
            _fy_fact("2021-02-10", "2021-12-31", -500e6),
            _fy_fact("2020-01-01", "2020-12-31", -9_734e6),
            _fy_fact("2019-01-01", "2019-12-31", -308e6),
        ]
        us_gaap = {"NetIncomeLoss": {"units": {"USD": facts}}}
        series = _series_for_tags(us_gaap, ["NetIncomeLoss"])
        self.assertNotIn(2021, series)

        share_facts = [
            _share_entry(start=f["start"], end=f["end"], val=abs(f["val"]), fy=2021, filed=f["filed"])
            for f in facts
        ]
        # Prior-year comparative is the only annual-duration share fact.
        shares = split_adjusted_shares(_shares_payload(share_facts)["facts"]["us-gaap"])
        self.assertNotIn(2021, shares)

    def test_current_year_annual_beats_comparatives(self):
        facts = [
            _fy_fact("2021-01-01", "2021-12-31", 111e6),
            _fy_fact("2020-01-01", "2020-12-31", -9_734e6),
            _fy_fact("2019-01-01", "2019-12-31", -308e6),
        ]
        us_gaap = {"NetIncomeLoss": {"units": {"USD": facts}}}
        series = _series_for_tags(us_gaap, ["NetIncomeLoss"])
        self.assertEqual(series[2021], 111e6)

    def test_one_day_subsequent_event_does_not_block_current_annual(self):
        # Ends 61 days after FYE. Counting it in E(Y) would reject the annual.
        facts = [
            _fy_fact("2021-01-01", "2021-12-31", 111e6),
            _fy_fact("2020-01-01", "2020-12-31", -9_734e6),
            _fy_fact("2022-03-01", "2022-03-02", 1.0, filed="2022-03-02"),
        ]
        us_gaap = {"NetIncomeLoss": {"units": {"USD": facts}}}
        series = _series_for_tags(us_gaap, ["NetIncomeLoss"])
        self.assertEqual(series[2021], 111e6)

    def test_prior_year_quarter_chain_does_not_fill_current_fy(self):
        quarters = _quarter_facts(
            [
                ("2020-01-01", "2020-03-31", -1e6),
                ("2020-04-01", "2020-06-30", -2e6),
                ("2020-07-01", "2020-09-30", -3e6),
                ("2020-10-01", "2020-12-31", -4e6),
            ],
            fy=2021,
            filed="2022-02-24",
        )
        successor = _fy_fact("2021-02-10", "2021-12-31", -500e6)
        us_gaap = {"NetIncomeLoss": {"units": {"USD": [*quarters, successor]}}}
        series = _series_for_tags(us_gaap, ["NetIncomeLoss"])
        self.assertNotIn(2021, series)


class TestCprtRevenueGolden(unittest.TestCase):
    def test_cprt_fy2019_2020_are_annual_scale(self):
        payload = json.loads(CPRT_REVENUE.read_text(encoding="utf-8"))
        _years, statements = map_companyfacts_to_statements(payload)
        r2019 = statements[2019]["revenue"]
        r2020 = statements[2020]["revenue"]
        self.assertAlmostEqual(r2019, 2.04e9, delta=0.02 * 2.04e9)
        self.assertAlmostEqual(r2020, 2.21e9, delta=0.02 * 2.21e9)
        for year in range(2017, 2027):
            revenue = statements[year]["revenue"]
            self.assertIsNotNone(revenue, msg=year)
            self.assertGreaterEqual(revenue, 1.0e9, msg=year)


def _usd(tag: str, facts: list[dict]) -> dict:
    return {tag: {"units": {"USD": facts}}}


def _lhx_revenue_facts(
    *,
    q4: float = 21_865_000_000,
    ytd: float | None = 16_217_000_000,
) -> list[dict]:
    """LHX-shaped revenue facts. FY2025 has no 12-month fact (#29)."""
    facts = [
        {
            "start": "2023-12-30",
            "end": "2025-01-03",
            "val": 21_325_000_000,
            "fy": 2024,
            "fp": "FY",
            "form": "10-K",
            "filed": "2025-02-14",
        },
        {
            "start": "2025-10-04",
            "end": "2026-01-02",
            "val": q4,
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2026-02-12",
        },
        {
            "start": "2023-12-30",
            "end": "2025-01-03",
            "val": 21_325_000_000,
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2026-02-12",
        },
        {
            "start": "2024-09-28",
            "end": "2025-01-03",
            "val": 21_325_000_000,
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2026-02-12",
        },
    ]
    if ytd is not None:
        facts.append(
            {
                "start": "2025-01-04",
                "end": "2025-10-03",
                "val": ytd,
                "fy": 2025,
                "fp": "Q3",
                "form": "10-Q",
                "filed": "2025-10-24",
            }
        )
    return facts


def _lhx_payload(
    *,
    q4: float = 21_865_000_000,
    ytd: float | None = 16_217_000_000,
) -> dict:
    ni = [
        {
            "start": "2023-12-30",
            "end": "2025-01-03",
            "val": 1_000_000_000,
            "fy": 2024,
            "fp": "FY",
            "form": "10-K",
            "filed": "2025-02-14",
        },
        {
            "start": "2024-12-29",
            "end": "2026-01-02",
            "val": 1_100_000_000,
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2026-02-12",
        },
    ]
    return {
        "facts": {
            "us-gaap": {
                **_usd(
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                    _lhx_revenue_facts(q4=q4, ytd=ytd),
                ),
                **_usd("NetIncomeLoss", ni),
            }
        }
    }


class TestShortContextAnnualRevenue(unittest.TestCase):
    def test_lhx_fy2025_short_context_fills_revenue(self):
        _years, statements = map_companyfacts_to_statements(_lhx_payload())
        self.assertEqual(statements[2025]["revenue"], 21_865_000_000)
        self.assertEqual(statements[2024]["revenue"], 21_325_000_000)

    def test_genuine_q4_is_rejected(self):
        _years, statements = map_companyfacts_to_statements(
            _lhx_payload(q4=5.648e9)
        )
        self.assertIsNone(statements[2025]["revenue"])

    def test_missing_nine_month_ytd_is_rejected(self):
        _years, statements = map_companyfacts_to_statements(
            _lhx_payload(ytd=None)
        )
        self.assertIsNone(statements[2025]["revenue"])

    def test_out_of_band_is_rejected(self):
        _years, statements = map_companyfacts_to_statements(
            _lhx_payload(q4=40e9, ytd=16.2e9)
        )
        self.assertIsNone(statements[2025]["revenue"])

    def test_flag_off_for_other_series(self):
        us_gaap = _usd("NetIncomeLoss", _lhx_revenue_facts())
        series = _series_for_tags(us_gaap, ["NetIncomeLoss"])
        self.assertNotIn(2025, series)
