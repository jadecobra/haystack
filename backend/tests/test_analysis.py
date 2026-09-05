import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.cli import main as cli_main
from app.metrics import LOCKED_LABELS, SCHEMA_VERSION, TREASURY_LABEL, build_table, compute_year
from app.sources import analyze


class TestMetrics(unittest.TestCase):
    def test_locked_labels_include_treasury(self):
        self.assertEqual(len(LOCKED_LABELS), 25)
        self.assertIn("Shares Outstanding", LOCKED_LABELS)
        self.assertIn(TREASURY_LABEL, LOCKED_LABELS)
        self.assertEqual(LOCKED_LABELS[-1], "30 Year Treasury (DGS30)")

    def test_compute_and_table(self):
        stmt = {
            "revenue": 100,
            "net_income": 10,
            "equity": 50,
            "assets": 200,
            "total_liabilities": 150,
            "debt": 40,
            "fcf": 20,
            "dividends": 5,
            "shares": 10,
            "cash": 8,
        }
        year = compute_year(stmt, 0.05)
        self.assertAlmostEqual(year["Net Income / Revenue"], 0.1)
        self.assertAlmostEqual(year["Shares Outstanding"], 10)
        self.assertAlmostEqual(year["Owner Earnings per Share"], 2.0)
        self.assertAlmostEqual(year[TREASURY_LABEL], 40.0)
        self.assertAlmostEqual(year["30 Year Treasury (DGS30)"], 0.05)
        rows = build_table([2024], {2024: stmt}, {2024: 0.05})
        self.assertEqual(len(rows), 25)
        self.assertEqual(rows[0]["values"]["2024"], "10.0%")
        self.assertAlmostEqual(rows[0]["raw"]["2024"], 0.1)
        shares_row = next(r for r in rows if r["metric"] == "Shares Outstanding")
        self.assertEqual(shares_row["values"]["2024"], "10")
        self.assertAlmostEqual(shares_row["raw"]["2024"], 10)
        treasury = next(r for r in rows if r["metric"] == TREASURY_LABEL)
        self.assertTrue(treasury["values"]["2024"].startswith("$"))
        self.assertAlmostEqual(treasury["raw"]["2024"], 40.0)
        dgs30 = next(r for r in rows if r["metric"] == "30 Year Treasury (DGS30)")
        self.assertEqual(dgs30["values"]["2024"], "5.00%")
        self.assertAlmostEqual(dgs30["raw"]["2024"], 0.05)


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "healthy")
        self.assertIn("message", body)

    def test_analyze_ticker_endpoint(self):
        years = ["2024", "2023", "2022", "2021", "2020"]
        fake = {
            "ticker": "AAPL",
            "years": years,
            "rows": [
                {
                    "metric": m,
                    "values": {
                        y: ("1.0%" if i < 13 else "$1.00") for y in years
                    },
                    "raw": {y: (0.01 if i < 13 else 1.0) for y in years},
                }
                for i, m in enumerate(LOCKED_LABELS)
            ],
            "source": "edgar",
            "status": "success",
            "message": "mocked",
            "treasury_label": TREASURY_LABEL,
        }
        with mock.patch("app.main.analyze", return_value=fake) as mocked:
            response = self.client.get("/analyze/AAPL")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["ticker"], "AAPL")
            self.assertEqual(len(body["rows"]), 25)
            self.assertEqual([r["metric"] for r in body["rows"]], LOCKED_LABELS)
            self.assertIn("raw", body["rows"][0])
            mocked.assert_called_once_with("AAPL")

    def test_analyze_ticker_invalid_ticker(self):
        response = self.client.get("/analyze/!!!")
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_analyze_fixture_query(self):
        fake = {
            "ticker": "AAPL",
            "years": ["2024"],
            "rows": [
                {
                    "metric": m,
                    "values": {"2024": "1.0%"},
                    "raw": {"2024": 0.01},
                }
                for m in LOCKED_LABELS
            ],
            "source": "edgar",
            "status": "success",
            "message": "mocked live",
            "treasury_label": TREASURY_LABEL,
        }
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": ""}, clear=False):
            with mock.patch("app.main.analyze", return_value=fake) as mocked:
                response = self.client.get("/analyze/AAPL?fixture=1")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["source"], "edgar")
                mocked.assert_called_once_with("AAPL")

    def test_analyze_env_force_fixture(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            response = self.client.get("/analyze/AAPL")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["source"], "fixture")
            self.assertIn("raw", response.json()["rows"][0])

    def test_contract_endpoint(self):
        response = self.client.get("/contract")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema_version"], SCHEMA_VERSION)
        self.assertEqual(body["labels"], LOCKED_LABELS)
        self.assertEqual(body["row_count"], 25)


class TestSourcesFixture(unittest.TestCase):
    def test_analyze_prefer_fixture(self):
        payload = analyze("AAPL", prefer_fixture=True)
        self.assertEqual(payload["source"], "fixture")
        self.assertEqual(len(payload["rows"]), 25)
        self.assertEqual(payload["previous_close"], 100.0)
        self.assertIn("raw", payload["rows"][0])


class TestQuote(unittest.TestCase):
    def setUp(self):
        import tempfile

        from app import quote as quote_mod

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._orig_dir = quote_mod._CACHE_DIR
        quote_mod._CACHE_DIR = Path(self._tmpdir.name)
        quote_mod._mem.clear()
        quote_mod._inflight.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        from app import quote as quote_mod

        quote_mod._CACHE_DIR = self._orig_dir
        quote_mod._mem.clear()
        quote_mod._inflight.clear()

    def _yahoo_client(self, price: float, *, calls: list):
        fake = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "previousClose": price,
                            "regularMarketTime": 1757001600,
                        }
                    }
                ]
            }
        }

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return fake

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, *args, **kwargs):
                calls.append(1)
                return _Resp()

        return _Client

    def test_previous_close_parses_yahoo_meta(self):
        from app.quote import previous_close

        calls: list = []
        with mock.patch("app.quote.httpx.Client", self._yahoo_client(227.16, calls=calls)):
            quote = previous_close("AAPL")
        self.assertIsNotNone(quote)
        self.assertEqual(quote["price"], 227.16)
        self.assertEqual(quote["as_of"], "2025-09-04")
        self.assertEqual(len(calls), 1)

    def test_previous_close_cached_second_call_skips_yahoo(self):
        from app.quote import previous_close

        calls: list = []
        with mock.patch("app.quote.httpx.Client", self._yahoo_client(227.16, calls=calls)):
            first = previous_close("AAPL")
            second = previous_close("AAPL")
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)


class TestCli(unittest.TestCase):
    def test_contract_local(self):
        self.assertEqual(cli_main(["contract"]), 0)

    def test_analyze_local(self):
        self.assertEqual(cli_main(["analyze", "AAPL", "--local"]), 0)

    def test_analyze_local_invalid(self):
        self.assertEqual(cli_main(["analyze", "!!!", "--local"]), 1)
