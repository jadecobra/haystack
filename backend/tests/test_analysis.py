import unittest
import app
import fastapi


class TestAnalysis(unittest.TestCase):

    def setUp(self):
        self.client = fastapi.testclient.TestClient(app.main.app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_analyze_ticker_endpoint(self):
        response = self.client.get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ticker", response.json())
        self.assertIn("analysis", response.json())

    def test_analyze_ticker_invalid_ticker(self):
        response = self.client.get("/analyze/INVALID")
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.json())
