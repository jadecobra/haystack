"""Owner earnings composition: capex, maintenance proxy, OCF fallbacks."""

from __future__ import annotations

import unittest

from app.edgar import (
    _compose_capex,
    _owner_earnings,
    _resolve_ocf,
    map_companyfacts_to_statements,
)


def _usd(fy: int, val: float, form: str = "10-K") -> dict:
    return {
        "end": f"{fy}-12-31",
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": form,
        "filed": f"{fy + 1}-02-01",
    }


def _facts(**tags: list[dict]) -> dict:
    us_gaap = {}
    for tag, entries in tags.items():
        us_gaap[tag] = {"units": {"USD": entries}}
    return {"facts": {"us-gaap": us_gaap}}


class TestComposeCapex(unittest.TestCase):
    def test_combined_wins_over_ppe(self):
        payload = _facts(
            PaymentsToAcquirePropertyPlantAndEquipment=[_usd(2024, 10)],
            PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets=[_usd(2024, 40)],
        )
        capex = _compose_capex(payload["facts"]["us-gaap"])
        self.assertEqual(capex[2024], 40)

    def test_ppe_plus_software_summed(self):
        payload = _facts(
            PaymentsToAcquirePropertyPlantAndEquipment=[_usd(2024, 10)],
            PaymentsToDevelopSoftware=[_usd(2024, 3)],
        )
        capex = _compose_capex(payload["facts"]["us-gaap"])
        self.assertEqual(capex[2024], 13)

    def test_productive_only_if_no_ppe(self):
        both = _facts(
            PaymentsToAcquirePropertyPlantAndEquipment=[_usd(2024, 10)],
            PaymentsToAcquireProductiveAssets=[_usd(2024, 99)],
        )
        self.assertEqual(_compose_capex(both["facts"]["us-gaap"])[2024], 10)
        only = _facts(PaymentsToAcquireProductiveAssets=[_usd(2024, 99)])
        self.assertEqual(_compose_capex(only["facts"]["us-gaap"])[2024], 99)

    def test_negative_capex_abs(self):
        payload = _facts(PaymentsToAcquirePropertyPlantAndEquipment=[_usd(2024, -10)])
        self.assertEqual(_compose_capex(payload["facts"]["us-gaap"])[2024], 10)


class TestOwnerEarnings(unittest.TestCase):
    def test_min_capex_and_da(self):
        self.assertEqual(_owner_earnings({2024: 100}, {2024: 30}, {2024: 20})[2024], 80)
        self.assertEqual(_owner_earnings({2024: 100}, {2024: 10}, {2024: 20})[2024], 90)

    def test_single_leg(self):
        self.assertEqual(_owner_earnings({2024: 100}, {2024: 15}, {})[2024], 85)
        self.assertEqual(_owner_earnings({2024: 100}, {}, {2024: 12})[2024], 88)

    def test_no_maint_is_null(self):
        self.assertEqual(_owner_earnings({2024: 100}, {}, {}), {})


class TestOcfFallbacks(unittest.TestCase):
    def test_reported_ocf_wins(self):
        payload = _facts(
            NetCashProvidedByUsedInOperatingActivities=[_usd(2024, 50)],
            CashAndCashEquivalentsPeriodIncreaseDecrease=[_usd(2024, 5)],
            NetCashProvidedByUsedInInvestingActivities=[_usd(2024, -10)],
            NetCashProvidedByUsedInFinancingActivities=[_usd(2024, -20)],
        )
        ocf = _resolve_ocf(payload["facts"]["us-gaap"], {}, {})
        self.assertEqual(ocf[2024], 50)

    def test_cash_identity(self):
        payload = _facts(
            CashAndCashEquivalentsPeriodIncreaseDecrease=[_usd(2024, 5)],
            NetCashProvidedByUsedInInvestingActivities=[_usd(2024, -10)],
            NetCashProvidedByUsedInFinancingActivities=[_usd(2024, -20)],
            EffectOfExchangeRateOnCashAndCashEquivalents=[_usd(2024, 1)],
        )
        ocf = _resolve_ocf(payload["facts"]["us-gaap"], {}, {})
        self.assertEqual(ocf[2024], 5 - (-10) - (-20) - 1)

    def test_accrual_rebuild_uses_wc_pairs(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2023, 8), _usd(2024, 10)],
            DepreciationAndAmortization=[_usd(2023, 2), _usd(2024, 3)],
            AccountsReceivableNetCurrent=[_usd(2023, 4), _usd(2024, 6)],
            InventoryNet=[_usd(2023, 1), _usd(2024, 1)],
            AccountsPayableCurrent=[_usd(2023, 2), _usd(2024, 5)],
        )
        us = payload["facts"]["us-gaap"]
        ni = {2023: 8.0, 2024: 10.0}
        da = {2023: 2.0, 2024: 3.0}
        ocf = _resolve_ocf(us, ni, da)
        # ΔAR=2, ΔInv=0, ΔAP=3 → ΔNWC=2+0-3=-1; OCF=10+3-(-1)=14
        self.assertEqual(ocf[2024], 14)

    def test_accrual_refuses_ni_plus_da_without_wc(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 10)],
            DepreciationAndAmortization=[_usd(2024, 3)],
        )
        ocf = _resolve_ocf(payload["facts"]["us-gaap"], {2024: 10.0}, {2024: 3.0})
        self.assertNotIn(2024, ocf)

    def test_map_null_without_ocf_or_maint(self):
        payload = _facts(NetIncomeLoss=[_usd(2024, 100)])
        years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2024]["fcf"])

    def test_map_end_to_end_reported(self):
        payload = _facts(
            NetIncomeLoss=[_usd(2024, 10)],
            Revenues=[_usd(2024, 100)],
            NetCashProvidedByUsedInOperatingActivities=[_usd(2024, 40)],
            PaymentsToAcquirePropertyPlantAndEquipment=[_usd(2024, 25)],
            DepreciationAndAmortization=[_usd(2024, 10)],
        )
        _, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2024]["fcf"], 40 - 10)


if __name__ == "__main__":
    unittest.main()
