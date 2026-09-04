import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.cli import main as cli_main
from app.metrics import LOCKED_LABELS, SCHEMA_VERSION, build_table, compute_year


class TestMetrics(unittest.TestCase):
    def test_locked_labels_include_treasury(self):
        self.assertEqual(len(LOCKED_LABELS), 23)
        self.assertIn("FCF / 30 Year Treasury per Share", LOCKED_LABELS)

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
        self.assertAlmostEqual(year["FCF per Share"], 2.0)
        self.assertAlmostEqual(year["FCF / 30 Year Treasury per Share"], 40.0)
        rows = build_table([2024], {2024: stmt}, {2024: 0.05})
        self.assertEqual(len(rows), 23)
        self.assertEqual(rows[0]["values"]["2024"], "10.0%")
        treasury = next(r for r in rows if r["metric"] == "FCF / 30 Year Treasury per Share")
        self.assertTrue(treasury["values"]["2024"].startswith("$"))


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
        response = self.client.get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ticker"], "AAPL")
        self.assertEqual(len(body["rows"]), 23)
        self.assertEqual([r["metric"] for r in body["rows"]], LOCKED_LABELS)
        self.assertIn("FCF / 30 Year Treasury per Share", [r["metric"] for r in body["rows"]])
        self.assertGreaterEqual(len(body["years"]), 5)

    def test_analyze_ticker_invalid_ticker(self):
        response = self.client.get("/analyze/!!!")
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_analyze_fixture_query(self):
        response = self.client.get("/analyze/AAPL?fixture=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fixture")

    def test_contract_endpoint(self):
        response = self.client.get("/contract")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema_version"], SCHEMA_VERSION)
        self.assertEqual(body["labels"], LOCKED_LABELS)
        self.assertEqual(body["row_count"], 23)


class TestCli(unittest.TestCase):
    def test_contract_local(self):
        self.assertEqual(cli_main(["contract"]), 0)

    def test_analyze_local(self):
        self.assertEqual(cli_main(["analyze", "AAPL", "--local"]), 0)

    def test_analyze_local_invalid(self):
        self.assertEqual(cli_main(["analyze", "!!!", "--local"]), 1)
