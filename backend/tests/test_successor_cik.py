"""#45: ticker moved to a successor CIK (8-K12B) with no 10-K yet; merge predecessor history."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import edgar
from app.main import app

FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "xom_successor_companyfacts.json").read_text()
)
SUCC, PRED = FIXTURE["successor"], FIXTURE["predecessor"]


def _fake_fetch(cik, meta=None):
    return {"2115436": SUCC, "34088": PRED}[edgar._normalize_cik(cik)]


class TestPredecessorMap(unittest.TestCase):
    def test_xom_and_ferg_entries(self):
        self.assertEqual(edgar.predecessor_ciks("2115436"), ["34088"])
        self.assertEqual(edgar.predecessor_ciks("0002011641"), ["1832433"])
        self.assertEqual(edgar.predecessor_ciks("320193"), [])

    def test_successor_alone_has_no_annual_years(self):
        years, _ = edgar.map_companyfacts_to_statements(SUCC)
        self.assertEqual(years, [])

    def test_merge_successor_wins_and_keeps_identity(self):
        merged = edgar.merge_predecessor_facts(SUCC, PRED)
        self.assertEqual(merged["entityName"], SUCC["entityName"])
        self.assertEqual(merged["cik"], SUCC["cik"])
        # successor entries are untouched (same objects/period first)
        for tag, node in SUCC["facts"]["us-gaap"].items():
            for unit, entries in node["units"].items():
                self.assertEqual(merged["facts"]["us-gaap"][tag]["units"][unit][: len(entries)], entries)
        # inputs not mutated
        self.assertEqual(edgar.map_companyfacts_to_statements(SUCC)[0], [])


class TestXomGolden(unittest.TestCase):
    """Values from Exxon Mobil Corp 10-K (accession 0000034088-26-000045)."""

    def setUp(self):
        p1 = mock.patch.object(edgar, "resolve_cik", return_value="2115436")
        p2 = mock.patch.object(edgar, "fetch_companyfacts", side_effect=_fake_fetch)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_statements(self):
        years, st, cik, name = edgar.statements_for_ticker("XOM")
        self.assertEqual(cik, "2115436")
        self.assertEqual(name, "ExxonMobil Holdings Corp")
        self.assertEqual(years[:4], [2025, 2024, 2023, 2022])
        self.assertEqual(st[2025]["revenue"], 332_238_000_000)
        self.assertEqual(st[2024]["revenue"], 349_585_000_000)
        self.assertEqual(st[2025]["net_income"], 28_844_000_000)
        self.assertEqual(st[2024]["net_income"], 33_680_000_000)
        self.assertAlmostEqual(st[2025]["shares"] / 1e9, 4.305, places=2)

    def test_analyze_endpoint_not_400(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": ""}), mock.patch(
            "app.fred.treasury_for_years", return_value={}
        ), mock.patch("app.fred.latest_dgs30", side_effect=RuntimeError), mock.patch(
            "app.quote.previous_close", return_value=None
        ):
            r = TestClient(app).get("/analyze/XOM")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["years"][0], "2025")
        self.assertEqual(body["classification"]["sector"], "Energy")
