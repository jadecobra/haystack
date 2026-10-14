"""#42: S&P 500 peers by GICS sub-industry, widening to industry group."""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.peers import MAX_PEERS, load_structure, peers_for

GICS = {
    "AAA": {"sector": "Information Technology", "sub_industry": "Technology Hardware, Storage & Peripherals"},
    "BBB": {"sector": "Information Technology", "sub_industry": "Technology Hardware, Storage & Peripherals"},
    "CCC": {"sector": "Information Technology", "sub_industry": "Technology Hardware, Storage & Peripherals"},
    "DDD": {"sector": "Information Technology", "sub_industry": "Technology Hardware, Storage & Peripherals"},
    "OIL": {"sector": "Energy", "sub_industry": "Integrated Oil & Gas"},
    "OIL2": {"sector": "Energy", "sub_industry": "Integrated Oil & Gas"},
    "DRL": {"sector": "Energy", "sub_industry": "Oil & Gas Drilling"},
    "REF": {"sector": "Energy", "sub_industry": "Oil & Gas Refining & Marketing"},
    "BRK.B": {"sector": "Financials", "sub_industry": "Multi-Sector Holdings"},
    "BRK-B": {"sector": "Financials", "sub_industry": "Multi-Sector Holdings"},
}


class TestPeersRule(unittest.TestCase):
    def test_sub_industry_peers_exclude_self(self):
        p = peers_for("AAA", gics=GICS, names={"BBB": "Bee"})
        self.assertEqual(p["basis"], "sub_industry")
        self.assertFalse(p["fallback"])
        self.assertEqual([x["ticker"] for x in p["peers"]], ["BBB", "CCC", "DDD"])
        self.assertEqual(p["peers"][0]["name"], "Bee")

    def test_thin_sub_industry_widens_to_industry_group(self):
        p = peers_for("OIL", gics=GICS, names={})
        self.assertEqual(p["basis"], "industry_group")
        self.assertEqual(p["group"], "Energy")
        self.assertTrue(p["fallback"])
        # same sub-industry first, then the rest of the group by ticker
        self.assertEqual([x["ticker"] for x in p["peers"]], ["OIL2", "DRL", "REF"])

    def test_non_sp500_and_alias(self):
        self.assertIsNone(peers_for("RIVN", gics=GICS, names={}))
        p = peers_for("BRK-B", gics=GICS, names={})
        self.assertNotIn("BRK.B", [x["ticker"] for x in p["peers"]])
        self.assertNotIn("BRK-B", [x["ticker"] for x in p["peers"]])

    def test_structure_covers_every_sp500_sub_industry(self):
        from app.classification import load_gics

        structure = load_structure()
        subs = {g["sub_industry"] for g in load_gics().values() if g.get("sub_industry")}
        self.assertEqual(sorted(subs - set(structure)), [])

    def test_real_map_aapl_and_xom(self):
        aapl = peers_for("AAPL", names={})
        self.assertEqual(aapl["basis"], "sub_industry")
        self.assertIn("DELL", [x["ticker"] for x in aapl["peers"]])
        xom = peers_for("XOM", names={})
        self.assertEqual(xom["basis"], "industry_group")
        self.assertEqual(xom["peers"][0]["ticker"], "CVX")
        self.assertLessEqual(len(xom["peers"]), MAX_PEERS)


class TestPeersContract(unittest.TestCase):
    def test_fixture_aapl_peers_shape(self):
        with mock.patch.dict(os.environ, {"HAYSTACK_PREFER_FIXTURE": "1"}):
            r = TestClient(app).get("/analyze/AAPL")
        self.assertEqual(r.status_code, 200)
        p = r.json()["peers"]
        self.assertEqual(set(p), {"basis", "group", "sub_industry", "fallback", "total", "peers"})
        self.assertEqual(p["basis"], "sub_industry")
        self.assertEqual(p["sub_industry"], "Technology Hardware, Storage & Peripherals")
        self.assertFalse(p["fallback"])
        self.assertEqual(p["total"], len(p["peers"]))
        self.assertTrue(all(set(x) == {"ticker", "name"} for x in p["peers"]))
        self.assertNotIn("AAPL", [x["ticker"] for x in p["peers"]])
