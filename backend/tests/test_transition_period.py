"""#49: FERG 10-KT after a year-end change (Jul 31 -> Dec 31) plus predecessor 10-Ks.

Golden values are from the filings: FY2025 10-K (2024-08-01..2025-07-31,
filed 2025-09-26) revenue $30,762M / NI $1,856M; FY2024 $29,635M / $1,735M;
FY2023 $29,734M / $1,889M; FY2022 $28,566M / $2,122M (Ferguson plc 10-Ks).
The 10-KT stub 2025-08-01..2025-12-31 (revenue $12,833M) is not a year.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import edgar

FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "ferg_transition_companyfacts.json").read_text()
)
SUCC, PRED = FIXTURE["successor"], FIXTURE["predecessor"]


def _merged() -> dict:
    return edgar.merge_predecessor_facts(SUCC, PRED)


class TestFergTransitionPeriod(unittest.TestCase):
    def test_golden_years_match_filings(self):
        years, st = edgar.map_companyfacts_to_statements(_merged())
        self.assertEqual(years, [2025, 2024, 2023, 2022])
        expect = {
            2025: (30_762e6, 1_856e6),
            2024: (29_635e6, 1_735e6),
            2023: (29_734e6, 1_889e6),
            2022: (28_566e6, 2_122e6),
        }
        for y, (rev, ni) in expect.items():
            self.assertEqual(st[y]["revenue"], rev, y)
            self.assertEqual(st[y]["net_income"], ni, y)

    def test_transition_stub_is_not_a_year(self):
        years, st = edgar.map_companyfacts_to_statements(_merged())
        self.assertNotIn(2026, years)
        # Neither stub (2025-08..12: $12,833M; 2024-08..12 comparative: $12,279M)
        # shows up as an annual value.
        revenues = {st[y]["revenue"] for y in years}
        self.assertNotIn(12_833e6, revenues)
        self.assertNotIn(12_279e6, revenues)

    def test_stub_facts_dropped_full_year_comparatives_kept(self):
        norm = edgar.normalize_fiscal_years(SUCC)
        rows = norm["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
        kt = [e for e in rows if e["form"] == "10-KT"]
        self.assertTrue(kt)
        self.assertTrue(all(e["end"] <= "2025-07-31" for e in kt))
        self.assertIn(("2024-08-01", "2025-07-31"), {(e["start"], e["end"]) for e in kt})

    def test_successor_alone_still_has_fy2025(self):
        years, st = edgar.map_companyfacts_to_statements(SUCC)
        self.assertEqual(years[0], 2025)
        self.assertEqual(st[2025]["revenue"], 30_762e6)


if __name__ == "__main__":
    unittest.main()
