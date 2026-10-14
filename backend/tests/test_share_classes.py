"""#53: traded-class equivalent shares for multi-class issuers.

Goldens are checked against the 10-K per-share figures:
- BRK.B 2025 (10-K 0001193125-26-083899): average equivalent Class B shares
  2,157,335,139; net earnings per equivalent Class B share $31.04.
- V FY2025 (10-K 0001403161-25-000089, Note 16): class A diluted
  weighted-average shares 1,966M (as-converted); diluted EPS $10.20.
"""

from __future__ import annotations

import unittest

from app import edgar, share_classes

ENTRY = {
    "traded_class": "x:B",
    "ratios": {"x:A": {"ratio": 1500}, "x:B": {"ratio": 1}, "x:C": {"ratio": None, "reason": "test"}},
}


class TestEquivalentShares(unittest.TestCase):
    def test_cover_counts_times_ratio(self):
        shares, how = share_classes.equivalent_shares(ENTRY, {"cover": {"x:A": 511_820, "x:B": 1_389_605_139}})
        self.assertEqual(shares, 2_157_335_139)
        self.assertIn("cover", how)

    def test_unknown_ratio_is_blank_with_reason(self):
        shares, how = share_classes.equivalent_shares(ENTRY, {"cover": {"x:B": 10, "x:Z": 5}})
        self.assertIsNone(shares)
        self.assertIn("no conversion ratio for x:Z", how)
        shares, how = share_classes.equivalent_shares(ENTRY, {"cover": {"x:B": 10, "x:C": 5}})
        self.assertIsNone(shares)
        self.assertIn("test", how)

    def test_auto_mode_detects_if_converted_diluted(self):
        entry = {"traded_class": "x:A", "ratios": {"x:B": {"ratio": 1}}, "diluted_includes_other_classes": "auto"}
        profit = {"diluted": {"x:A": 200.0}, "basic": {"x:A": 171.0, "x:B": 23.0}}
        loss = {"diluted": {"x:A": 168.0}, "basic": {"x:A": 168.0, "x:B": 23.0}}
        self.assertEqual(share_classes.equivalent_shares(entry, profit)[0], 200.0)
        self.assertEqual(share_classes.equivalent_shares(entry, loss)[0], 191.0)

    def test_eps_basic_ratio(self):
        entry = {"traded_class": "x:A", "ratios": {"x:C": {"ratio": "eps_basic_ratio"}}}
        filing = {"cover": {"x:A": 100.0, "x:C": 10.0}, "eps_basic": {"x:A": 10.0, "x:C": 40.0}}
        self.assertEqual(share_classes.equivalent_shares(entry, filing)[0], 140.0)

    def test_parse_instance_per_class(self):
        xml = b"""<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
          xmlns:dei="http://xbrl.sec.gov/dei/2024" xmlns:us-gaap="http://fasb.org/us-gaap/2024">
          <context id="d"><entity><identifier scheme="x">1</identifier></entity><period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period></context>
          <context id="dA"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></segment></entity><period><startDate>2024-10-01</startDate><endDate>2025-09-30</endDate></period></context>
          <context id="cA"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></segment></entity><period><instant>2025-10-30</instant></period></context>
          <dei:DocumentPeriodEndDate contextRef="d">2025-09-30</dei:DocumentPeriodEndDate>
          <dei:EntityCommonStockSharesOutstanding contextRef="cA">1687629770</dei:EntityCommonStockSharesOutstanding>
          <us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding contextRef="dA">1966000000</us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding>
        </xbrl>"""
        out = share_classes.parse_instance(xml)
        self.assertEqual(out["period_end"], "2025-09-30")
        self.assertEqual(out["cover"], {"us-gaap:CommonClassAMember": 1687629770.0})
        self.assertEqual(out["diluted"], {"us-gaap:CommonClassAMember": 1966000000.0})


class TestGoldensFromSeed(unittest.TestCase):
    """Real per-class counts from the committed seed (data/share_class_counts.json)."""

    def test_brk_b_2025_matches_10k(self):
        by_year = share_classes.shares_by_year("1067983")
        shares, _how, accn = by_year[2025]
        self.assertEqual(accn, "0001193125-26-083899")
        self.assertEqual(shares, 2_157_335_139)
        self.assertAlmostEqual(66_968e6 / shares, 31.04, places=2)

    def test_v_fy2025_matches_10k(self):
        shares, how, accn = share_classes.shares_by_year("1403161")[2025]
        self.assertEqual(accn, "0001403161-25-000089")
        self.assertEqual(shares, 1_966e6)
        self.assertIn("as-converted", how)
        self.assertAlmostEqual(20_058e6 / shares, 10.20, places=2)

    def test_targets_have_latest_year(self):
        for cik, year in (("1701605", 2025), ("922621", 2025), ("16918", 2026)):
            shares, how, _ = share_classes.shares_by_year(cik)[year]
            self.assertGreater(shares or 0, 0, (cik, how))

    def test_apply_fills_only_missing_years(self):
        st = {2025: {"shares": None}, 2024: {"shares": 123.0}}
        share_classes.apply("1403161", st)
        self.assertEqual(st[2025]["shares"], 1_966e6)
        self.assertEqual(st[2024]["shares"], 123.0)
        st = {2025: {"shares": None}}
        share_classes.apply("320193", st)  # AAPL: not mapped
        self.assertIsNone(st[2025]["shares"])

    def test_map_entries_cite_evidence(self):
        for cik, entry in share_classes.load_map().items():
            self.assertTrue(entry.get("diluted_evidence"), cik)
            for cls, spec in entry["ratios"].items():
                if cls != entry["traded_class"] and spec.get("ratio") != 1 or "evidence" in spec:
                    self.assertTrue(spec.get("evidence") or spec.get("reason"), (cik, cls))
            self.assertTrue(edgar.predecessor_ciks(cik) == [], cik)


if __name__ == "__main__":
    unittest.main()
