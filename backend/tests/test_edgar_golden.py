"""Golden / mapping tests for SEC companyfacts → statements."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from unittest import mock

from app.edgar import entity_name, map_companyfacts_to_statements, _http_get_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNIPPET = FIXTURES / "aapl_companyfacts_snippet.json"

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
