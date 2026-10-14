"""Fiscal-year labels come from the period end, not the filer's ``fy`` (#50)."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from app.edgar import (
    fiscal_year_label,
    map_companyfacts_to_statements,
    normalize_fiscal_years,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}_fy_label_companyfacts.json").read_text())


def _fy(start: str, end: str, fy: int, accn: str, filed: str, val: float) -> dict:
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": "FY",
            "form": "10-K", "filed": filed, "accn": accn}


class TestFiscalYearLabel(unittest.TestCase):
    def test_calendar_year(self):
        self.assertEqual(fiscal_year_label(date(2025, 12, 31)), 2025)

    def test_52_53_week_mid_year(self):
        self.assertEqual(fiscal_year_label(date(2025, 9, 27)), 2025)  # AAPL
        self.assertEqual(fiscal_year_label(date(2026, 7, 3)), 2026)  # STX 53-week

    def test_first_days_of_january_belong_to_prior_year(self):
        self.assertEqual(fiscal_year_label(date(2026, 1, 3)), 2025)
        self.assertEqual(fiscal_year_label(date(2026, 1, 7)), 2025)
        self.assertEqual(fiscal_year_label(date(2026, 1, 8)), 2026)

    def test_late_january_and_february_use_end_year(self):
        self.assertEqual(fiscal_year_label(date(2026, 1, 31)), 2026)
        self.assertEqual(fiscal_year_label(date(2026, 2, 1)), 2026)


class TestNormalize(unittest.TestCase):
    def test_consistent_filer_is_untouched(self):
        payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            _fy("2024-01-01", "2024-12-31", 2024, "a1", "2025-02-01", 1),
            _fy("2023-01-01", "2023-12-31", 2024, "a1", "2025-02-01", 2),
        ]}}}}}
        self.assertIs(normalize_fiscal_years(payload), payload)

    def test_wrong_fy_rekeyed_by_own_period_end(self):
        payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            _fy("2024-01-01", "2024-12-31", 2024, "a1", "2025-02-01", 10),
            _fy("2025-01-01", "2025-12-31", 2024, "a2", "2026-02-01", 20),
            _fy("2024-01-01", "2024-12-31", 2024, "a2", "2026-02-01", 10),
        ]}}}}}
        years, st = map_companyfacts_to_statements(payload)
        self.assertEqual(years[:2], [2025, 2024])
        self.assertEqual(st[2025]["revenue"], 20)
        self.assertEqual(st[2024]["revenue"], 10)

    def test_fact_dated_after_filing_is_ignored(self):
        payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            _fy("2023-10-01", "2024-09-27", 2024, "a1", "2024-11-12", 10),
            _fy("2024-03-30", "2025-03-28", 2024, "a1", "2024-11-12", 99),
        ]}}}}}
        self.assertIs(normalize_fiscal_years(payload), payload)


class TestGoldens(unittest.TestCase):
    def test_stx_no_future_year_and_fy2025_present(self):
        years, st = map_companyfacts_to_statements(_load("stx"))
        self.assertEqual(years[:3], [2026, 2025, 2024])
        self.assertLessEqual(max(years), 2026)
        self.assertEqual(st[2026]["revenue"], 12_195_000_000)  # FY ended 2026-07-03
        self.assertEqual(st[2025]["revenue"], 9_097_000_000)  # 10-K tagged fy=2027
        self.assertEqual(st[2024]["revenue"], 6_551_000_000)

    def test_frt_fy2025_labelled_2025(self):
        years, st = map_companyfacts_to_statements(_load("frt"))
        self.assertEqual(years[:2], [2025, 2024])
        self.assertEqual(st[2025]["revenue"], 1_278_975_000)  # 10-K tagged fy=2024
        self.assertEqual(st[2024]["revenue"], 1_202_452_000)

    def test_aapl_52_53_week_unchanged(self):
        years, st = map_companyfacts_to_statements(_load("aapl"))
        self.assertEqual(years[:2], [2025, 2024])
        self.assertEqual(st[2025]["revenue"], 416_161_000_000)
        self.assertEqual(st[2024]["revenue"], 391_035_000_000)

    def test_ko_calendar_year_unchanged(self):
        years, st = map_companyfacts_to_statements(_load("ko"))
        self.assertEqual(years[:2], [2025, 2024])
        self.assertEqual(st[2025]["revenue"], 47_941_000_000)
        self.assertEqual(st[2024]["revenue"], 47_061_000_000)


if __name__ == "__main__":
    unittest.main()
