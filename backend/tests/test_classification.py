"""GICS + SIC classification for the ticker page."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.classification import (
    classify,
    fetch_sic,
    load_gics,
    sic_division,
)
from app.main import app
from app.screen import DATA_PATH, load_sectors


class TestSicDivision(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(sic_division(100), "Agriculture, Forestry & Fishing")
        self.assertEqual(sic_division(1311), "Mining")
        self.assertEqual(sic_division(1531), "Construction")
        self.assertEqual(sic_division(3571), "Manufacturing")
        self.assertEqual(
            sic_division(4911), "Transportation, Communications & Utilities"
        )
        self.assertEqual(sic_division(5012), "Wholesale Trade")
        self.assertEqual(sic_division(5200), "Retail Trade")
        self.assertEqual(sic_division(6022), "Finance, Insurance & Real Estate")
        self.assertEqual(sic_division(7372), "Services")
        self.assertEqual(sic_division(9995), "Public Administration")
        self.assertIsNone(sic_division(None))
        self.assertIsNone(sic_division(-1))
        self.assertIsNone(sic_division(1800))


class TestLoadGics(unittest.TestCase):
    def test_known_names(self):
        gics = load_gics()
        self.assertEqual(gics["AAPL"]["sector"], "Information Technology")
        self.assertEqual(
            gics["AAPL"]["sub_industry"],
            "Technology Hardware, Storage & Peripherals",
        )
        self.assertEqual(gics["JPM"]["sector"], "Financials")
        self.assertEqual(gics["JPM"]["sub_industry"], "Diversified Banks")
        self.assertEqual(gics["XOM"]["sector"], "Energy")
        self.assertEqual(gics["XOM"]["sub_industry"], "Integrated Oil & Gas")

    def test_json_coverage(self):
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        tickers = set(raw["tickers"])
        sectors = set(raw["sectors"])
        subs = set(raw.get("sub_industries") or {})
        # Counts move with the monthly refresh PR (#46); keep sane bounds.
        self.assertGreaterEqual(len(tickers), 495)
        self.assertGreaterEqual(len(sectors), len(tickers) - 10)
        self.assertTrue(sectors.issubset(tickers))
        self.assertTrue(subs.issubset(tickers))
        self.assertEqual(load_sectors(), {k: v for k, v in raw["sectors"].items()})


class TestFetchSic(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache = Path(self._tmpdir.name)
        import app.classification as classification

        self._patch_cache = mock.patch.object(classification, "_CACHE_DIR", self.cache)
        self._patch_mem = mock.patch.object(classification, "_sic_mem", {})
        self._patch_cache.start()
        self._patch_mem.start()
        self.addCleanup(self._patch_cache.stop)
        self.addCleanup(self._patch_mem.stop)

    def test_network_then_cache(self):
        body = {"sic": "3711", "sicDescription": "Motor Vehicles & Passenger Car Bodies"}
        with mock.patch("app.edgar._http_get_json", return_value=body) as get:
            first = fetch_sic("37996")
            second = fetch_sic("37996")
        self.assertEqual(first["sic"], 3711)
        self.assertEqual(first["sic_description"], body["sicDescription"])
        self.assertEqual(second, first)
        get.assert_called_once()

    def test_stale_on_failure(self):
        body = {"sic": "7372", "sicDescription": "Prepackaged Software"}
        with mock.patch("app.edgar._http_get_json", return_value=body):
            fetch_sic("320193")
        import app.classification as classification

        classification._sic_mem.clear()
        with mock.patch(
            "app.edgar._http_get_json", side_effect=RuntimeError("down")
        ):
            path = classification._sic_cache_path("320193")
            os.utime(path, (0, 0))
            got = fetch_sic("320193")
        self.assertEqual(got["sic"], 7372)


class TestClassify(unittest.TestCase):
    def test_gics_path_offline(self):
        block = classify("AAPL")
        assert block is not None
        self.assertEqual(block["scheme"], "gics")
        self.assertEqual(block["sector"], "Information Technology")
        self.assertEqual(
            block["industry"], "Technology Hardware, Storage & Peripherals"
        )
        self.assertIsNone(block["sic"])
        self.assertEqual(
            block["link"], "/screen?sector=Information%20Technology"
        )

    def test_sic_path(self):
        body = {"sic": "3711", "sicDescription": "Motor Vehicles & Passenger Car Bodies"}
        with mock.patch("app.edgar.resolve_cik", return_value="37996"), mock.patch(
            "app.classification.fetch_sic",
            return_value={
                "sic": 3711,
                "sic_description": body["sicDescription"],
            },
        ):
            block = classify("ZZZZZ")
        assert block is not None
        self.assertEqual(block["scheme"], "sic")
        self.assertEqual(block["sic"], 3711)
        self.assertEqual(block["sector"], "Manufacturing")
        self.assertEqual(block["industry"], body["sicDescription"])
        self.assertEqual(block["link"], "/screen?sic=3711")


class TestAnalyzeClassificationContract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_fixture_aapl_gics(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            response = self.client.get("/analyze/AAPL")
        self.assertEqual(response.status_code, 200)
        block = response.json()["classification"]
        self.assertEqual(
            block,
            {
                "scheme": "gics",
                "sector": "Information Technology",
                "industry": "Technology Hardware, Storage & Peripherals",
                "sic": None,
                "sic_description": None,
                "link": "/screen?sector=Information%20Technology",
            },
        )

    def test_analyze_sic_shape(self):
        payload = {
            "ticker": "ZZZZZ",
            "company_name": None,
            "years": ["2024"],
            "rows": [],
            "source": "edgar",
            "status": "success",
            "message": "ok",
            "treasury_label": "Owner Earnings / 30 Year Treasury per Share",
            "treasury_dgs30_pct": 5.0,
            "treasury_dgs30_as_of": "2026-10-01",
            "previous_close": 10.0,
            "previous_close_as_of": None,
            "groups": [],
            "schema_version": "8",
            "labels": [],
            "cik": "37996",
            "classification": {
                "scheme": "sic",
                "sector": "Manufacturing",
                "industry": "Motor Vehicles & Passenger Car Bodies",
                "sic": 3711,
                "sic_description": "Motor Vehicles & Passenger Car Bodies",
                "link": "/screen?sic=3711",
            },
            "payback": None,
        }
        # Shape check via pydantic model
        from app.main import AnalysisResponse

        model = AnalysisResponse.model_validate(payload)
        self.assertEqual(model.classification.scheme, "sic")
        self.assertEqual(model.classification.sic, 3711)


if __name__ == "__main__":
    unittest.main()
