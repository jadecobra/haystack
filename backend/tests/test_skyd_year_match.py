"""First 10-K after a merger: predecessor full years share the filing fy.

SKYD (Paramount / Skydance) files one 10-K. DocumentFiscalYearFocus is 2025
for the predecessor years ended 2023-12-31 and 2024-12-31, the pre-close
stub, and the post-close stub. Three stray 364-day facts end 2025-12-31.
The statement years still have to keep OCF, capex and D&A.
"""

from __future__ import annotations

import unittest

from app.edgar import map_companyfacts_to_statements, rescale_share_facts

ACCN = "0002041610-26-000011"
FILED = "2026-02-25"


def _fact(start: str, end: str, val: float) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": ACCN,
        "fy": 2025,
        "fp": "FY",
        "form": "10-K",
        "filed": FILED,
    }


def _series(periods: list[tuple[str, str, float]]) -> dict:
    return {"units": {"USD": [_fact(*row) for row in periods]}}


# Periods: FY2023, FY2024, pre-close stub, post-close stub.
_OCF = [
    ("2023-01-01", "2023-12-31", 475_000_000),
    ("2024-01-01", "2024-12-31", 752_000_000),
    ("2025-01-01", "2025-08-06", 164_000_000),
    ("2025-08-08", "2025-12-31", 485_000_000),
]
_CAPEX = [
    ("2023-01-01", "2023-12-31", 328_000_000),
    ("2024-01-01", "2024-12-31", 263_000_000),
    ("2025-01-01", "2025-08-06", 134_000_000),
    ("2025-08-08", "2025-12-31", 162_000_000),
]
_DA = [
    ("2023-01-01", "2023-12-31", 418_000_000),
    ("2024-01-01", "2024-12-31", 392_000_000),
    ("2025-01-01", "2025-08-06", 204_000_000),
    ("2025-08-08", "2025-12-31", 590_000_000),
]
_REV = [
    ("2023-01-01", "2023-12-31", 29_652_000_000),
    ("2024-01-01", "2024-12-31", 29_213_000_000),
    ("2025-01-01", "2025-08-06", 16_622_000_000),
    ("2025-08-08", "2025-12-31", 14_000_000_000),
]
_NI = [
    ("2023-01-01", "2023-12-31", -608_000_000),
    ("2024-01-01", "2024-12-31", -6_190_000_000),
    ("2025-01-01", "2025-08-06", -35_000_000),
    ("2025-08-08", "2025-12-31", -100_000_000),
]


def _payload() -> dict:
    # Repeat the stray calendar-year facts so a single tag cannot define the
    # filing period end. Live SKYD has three of these against ~120 statement facts.
    stray = [_fact("2025-01-01", "2025-12-31", 3.0) for _ in range(3)]
    statements = [_fact(*row) for row in _REV]
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _series(_REV),
                "NetIncomeLoss": _series(_NI),
                "NetCashProvidedByUsedInOperatingActivities": _series(_OCF),
                "PaymentsToAcquirePropertyPlantAndEquipment": _series(_CAPEX),
                "DepreciationAndAmortization": _series(_DA),
                "NumberOfReportableSegments": {"units": {"pure": stray}},
                "NumberOfOperatingSegments": {
                    "units": {"pure": [_fact("2025-01-01", "2025-12-31", 3.0) for _ in range(3)]}
                },
                "Revenues": {"units": {"USD": statements}},
                # The live filing has ~120 statement facts on each full year
                # and 3 stray facts on the calendar stub year.
                "CostsAndExpenses": {
                    "units": {
                        "USD": [
                            *[_fact("2023-01-01", "2023-12-31", 1.0) for _ in range(40)],
                            *[_fact("2024-01-01", "2024-12-31", 1.0) for _ in range(40)],
                        ]
                    }
                },
            }
        }
    }


class TestSkydYearMatch(unittest.TestCase):
    def test_predecessor_full_years_keep_ocf_capex_and_da(self) -> None:
        years, statements = map_companyfacts_to_statements(_payload())
        self.assertEqual(years[:2], [2024, 2023])
        self.assertNotIn(2025, years)
        # Owner earnings = OCF - min(capex, D&A). Formula unchanged.
        self.assertEqual(statements[2024]["owner_earnings"], 752_000_000 - 263_000_000)
        self.assertEqual(statements[2023]["owner_earnings"], 475_000_000 - 328_000_000)
        self.assertEqual(statements[2024]["revenue"], 29_213_000_000)

    def test_placeholder_cover_does_not_shrink_uncovered_10k_shares(self) -> None:
        payload = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "end": "2025-05-13",
                                    "val": 1000,
                                    "accn": "q1",
                                    "form": "10-Q",
                                    "filed": "2025-05-14",
                                },
                                {
                                    "end": "2025-11-05",
                                    "val": 1_071_666_977,
                                    "accn": "q3",
                                    "form": "10-Q",
                                    "filed": "2025-11-10",
                                },
                            ]
                        }
                    }
                },
                "us-gaap": {
                    "WeightedAverageNumberOfDilutedSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "val": 664_000_000,
                                    "accn": "k",
                                    "fp": "FY",
                                    "form": "10-K",
                                    "fy": 2024,
                                    "filed": "2026-02-25",
                                }
                            ]
                        }
                    }
                },
            }
        }
        scaled = rescale_share_facts(payload)
        val = scaled["WeightedAverageNumberOfDilutedSharesOutstanding"]["units"]["shares"][0]["val"]
        self.assertEqual(val, 664_000_000)


if __name__ == "__main__":
    unittest.main()
