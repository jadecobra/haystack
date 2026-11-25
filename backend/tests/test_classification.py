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
    clear_gics_cache,
    fetch_sic,
    is_financial_company,
    load_gics,
    sic_division,
)
from app.main import app
from app.sp1500_map import INDEX_SPECS, load_constituents


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
        constituents = load_constituents()
        gics = load_gics()
        for spec in INDEX_SPECS:
            count = sum(1 for c in constituents.values() if c.index == spec.index)
            self.assertGreaterEqual(count, spec.min_rows)
        self.assertTrue(set(constituents).issubset(gics))
        self.assertIn("BRK.B", gics)
        self.assertEqual(gics["BRK-B"], gics["BRK.B"])

    def test_load_gics_custom_path_and_cache_reset(self):
        clear_gics_cache()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sp1500.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "constituents": {
                            "BF.B": {
                                "index": "sp500",
                                "sector": "Consumer Staples",
                                "sub_industry": "Distillers & Vintners",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            gics = load_gics(path=path)
            self.assertEqual(gics["BF.B"]["sector"], "Consumer Staples")
            self.assertEqual(gics["BF-B"], gics["BF.B"])


class TestFetchSic(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache = Path(self._tmpdir.name)
        from app import classification

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
        from app import classification

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
        self.assertIsNone(block["link"])

    def test_sp400_and_sp600_gics_offline(self):
        with mock.patch("app.edgar.resolve_cik", side_effect=AssertionError("offline")):
            colm = classify("COLM")
            uaa = classify("UAA")
        assert colm is not None
        self.assertEqual(colm["scheme"], "gics")
        self.assertEqual(colm["sector"], "Consumer Discretionary")
        self.assertEqual(colm["industry"], "Apparel, Accessories & Luxury Goods")
        self.assertIsNone(colm["sic"])

        assert uaa is not None
        self.assertEqual(uaa["scheme"], "gics")
        self.assertEqual(uaa["sector"], "Consumer Discretionary")
        self.assertEqual(uaa["industry"], "Apparel, Accessories & Luxury Goods")
        self.assertIsNone(uaa["sic"])

    def test_icb_path_offline(self):
        with mock.patch("app.edgar.resolve_cik", side_effect=AssertionError("offline")):
            block = classify("CRWV")
        assert block is not None
        self.assertEqual(block["scheme"], "icb")
        self.assertEqual(block["sector"], "Information Technology")
        self.assertEqual(
            block["industry"], "Computer Software: Prepackaged Software"
        )
        self.assertIsNone(block["sic"])
        self.assertIsNone(block["sic_description"])
        self.assertIsNone(block["link"])

    def test_is_financial_company_sp1500_and_sic_fallback(self):
        self.assertTrue(is_financial_company("JPM"))
        self.assertTrue(is_financial_company("WAL"))
        self.assertTrue(is_financial_company("AAMI"))
        self.assertFalse(is_financial_company("COLM", sic=6021))
        self.assertFalse(is_financial_company("UAA", sic=6021))
        self.assertTrue(is_financial_company("SOFI"))
        self.assertFalse(is_financial_company("O"))
        self.assertFalse(is_financial_company("CRWV", sic=6021))
        self.assertTrue(is_financial_company("NOTIN1500", sic=6021))
        self.assertFalse(is_financial_company("NOTIN1500", sic=6798))

    def test_is_financial_company_fails_soft_when_taxonomy_unavailable(self):
        with mock.patch(
            "app.us_taxonomy.lookup_taxonomy",
            side_effect=OSError("missing taxonomy"),
        ):
            self.assertTrue(is_financial_company("NOTIN1500", sic=6021))
            self.assertFalse(is_financial_company("NOTIN1500", sic=7372))

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
        self.assertIsNone(block["link"])


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
                "link": None,
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
                "link": None,
            },
            "payback": None,
        }
        # Shape check via pydantic model
        from app.main import AnalysisResponse

        model = AnalysisResponse.model_validate(payload)
        self.assertEqual(model.classification.scheme, "sic")
        self.assertEqual(model.classification.sic, 3711)

    def test_analyze_icb_shape(self):
        from app.main import AnalysisResponse

        base = {
            "ticker": "CRWV",
            "company_name": "CoreWeave, Inc.",
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
            "cik": "1769628",
            "classification": {
                "scheme": "icb",
                "sector": "Information Technology",
                "industry": "Computer Software: Prepackaged Software",
                "sic": None,
                "sic_description": None,
                "link": None,
            },
            "payback": None,
        }
        for basis, fallback in (("icb", False), ("icb_sector", True)):
            payload = {
                **base,
                "peers": {
                    "basis": basis,
                    "group": (
                        "Information Technology"
                        if fallback
                        else "Computer Software: Prepackaged Software"
                    ),
                    "sub_industry": "Computer Software: Prepackaged Software",
                    "fallback": fallback,
                    "total": 0,
                    "peers": [],
                    "sic": 7372,
                    "reason": None,
                },
            }
            model = AnalysisResponse.model_validate(payload)
            self.assertEqual(model.classification.scheme, "icb")
            self.assertEqual(model.peers.basis, basis)


if __name__ == "__main__":
    unittest.main()
