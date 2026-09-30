"""Golden cases for the non-overlapping debt ladder."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.edgar import (
    MATERIAL_INTEREST_PCT_OF_REVENUE,
    compose_debt,
    map_companyfacts_to_statements,
)


def _usd(fy: int, val: float) -> dict:
    return {
        "end": f"{fy}-12-31",
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{fy + 1}-02-01",
    }


def _gaap(**tags: list[dict]) -> dict:
    return {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}


class TestComposeDebt(unittest.TestCase):
    def test_zero_debt_from_liabilities_without_ladder_tags(self):
        # Known zero-debt style: balance sheet exists, no debt concepts filed.
        totals, states = compose_debt(_gaap(Liabilities=[_usd(2024, 500.0)]))
        self.assertNotIn(2024, totals)
        self.assertEqual(states[2024], "zero")

    def test_explicit_long_term_debt_zero(self):
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                LongTermDebt=[_usd(2024, 0.0)],
            )
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertEqual(states[2024], "zero")

    def test_levered_long_term_does_not_double_count_debt_current(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebt=[_usd(2024, 100.0)],
                ShortTermBorrowings=[_usd(2024, 7.0)],
                DebtCurrent=[_usd(2024, 40.0)],
                CommercialPaper=[_usd(2024, 3.0)],
            )
        )
        # LongTermDebt already includes current maturities; DebtCurrent is
        # skipped. ShortTermBorrowings already includes commercial paper.
        self.assertEqual(totals[2024], 107.0)
        self.assertEqual(states[2024], "positive")

    def test_noncurrent_plus_current_maturities(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebtNoncurrent=[_usd(2024, 80.0)],
                LongTermDebtCurrent=[_usd(2024, 20.0)],
                CommercialPaper=[_usd(2024, 3.0)],
            )
        )
        self.assertEqual(totals[2024], 103.0)
        self.assertEqual(states[2024], "positive")

    def test_debt_current_replaces_maturities_and_short_borrowings(self):
        totals, states = compose_debt(
            _gaap(
                LongTermDebtNoncurrent=[_usd(2024, 80.0)],
                LongTermDebtCurrent=[_usd(2024, 20.0)],
                DebtCurrent=[_usd(2024, 40.0)],
                ShortTermBorrowings=[_usd(2024, 9.0)],
            )
        )
        self.assertEqual(totals[2024], 120.0)
        self.assertEqual(states[2024], "positive")

    def test_unknown_when_no_debt_tags_and_no_liabilities(self):
        totals, states = compose_debt(_gaap(Revenues=[_usd(2024, 10.0)]))
        self.assertEqual(totals, {})
        self.assertEqual(states, {})

    def test_partial_tag_explicit_zero_with_liabilities_is_zero(self):
        # ShortTermBorrowings is not a total tag. Every present ladder value
        # is 0, so this year follows the no-ladder path: Liabilities reported
        # means zero. Total stays 0.0 (the statement shows no debt).
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                ShortTermBorrowings=[_usd(2024, 0.0)],
            )
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertEqual(states[2024], "zero")

    def test_partial_zero_with_material_interest_is_unknown(self):
        # Same partial zero as above, but interest above 0.15% of revenue
        # still downgrades the would-be zero.
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                ShortTermBorrowings=[_usd(2024, 0.0)],
                InterestExpense=[_usd(2024, 12.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertEqual(states[2024], "unknown")

    def test_partial_zero_without_liabilities_is_unknown(self):
        # A partial zero with no Liabilities is the no-ladder unknown path.
        # The year stays in the state map because a ladder tag was present,
        # and the total stays 0.0.
        totals, states = compose_debt(
            _gaap(ShortTermBorrowings=[_usd(2024, 0.0)])
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertEqual(states[2024], "unknown")

    def test_explicit_zero_with_material_interest_expense_is_unknown(self):
        # LongTermDebt=0 would be zero evidence. Interest of 12 on revenue
        # of 1000 is above MATERIAL_INTEREST_PCT_OF_REVENUE, so unknown.
        totals, states = compose_debt(
            _gaap(
                LongTermDebt=[_usd(2024, 0.0)],
                InterestExpense=[_usd(2024, 12.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(totals[2024], 0.0)
        self.assertGreater(12.0, MATERIAL_INTEREST_PCT_OF_REVENUE * 1000.0)
        self.assertEqual(states[2024], "unknown")

    def test_liabilities_only_with_material_interest_is_unknown(self):
        # Liabilities without a ladder tag would be zero. Interest above
        # 0.15% of revenue means the filing may omit the debt concepts.
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestExpense=[_usd(2024, 4.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertNotIn(2024, totals)
        self.assertEqual(states[2024], "unknown")

    def test_interest_at_materiality_boundary_stays_zero(self):
        # 0.15% of 1000 is 1.5. Equal stays zero; strictly above is unknown.
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestExpense=[_usd(2024, 1.5)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertNotIn(2024, totals)
        self.assertEqual(states[2024], "zero")

        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestExpense=[_usd(2024, 1.6)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(states[2024], "unknown")

    def test_missing_revenue_any_interest_is_unknown(self):
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestExpense=[_usd(2024, 0.1)],
            )
        )
        self.assertEqual(states[2024], "unknown")

    def test_interest_income_expense_net_sign(self):
        # Negative is net interest expense. -2 / 1000 is material; -1 is not.
        # A positive value is net interest income and does not count.
        _, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestIncomeExpenseNet=[_usd(2024, -2.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(states[2024], "unknown")

        _, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestIncomeExpenseNet=[_usd(2024, -1.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(states[2024], "zero")

        _, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                InterestIncomeExpenseNet=[_usd(2024, 5.0)],
                Revenues=[_usd(2024, 1000.0)],
            )
        )
        self.assertEqual(states[2024], "zero")

    def test_maturity_schedule_blocks_zero_without_threshold(self):
        totals, states = compose_debt(
            _gaap(
                Liabilities=[_usd(2024, 500.0)],
                LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo=[
                    _usd(2024, 405.0)
                ],
            )
        )
        self.assertNotIn(2024, totals)
        self.assertEqual(states[2024], "unknown")

    def test_overlapping_notes_take_max_not_sum(self):
        totals, states = compose_debt(
            _gaap(
                SeniorNotes=[_usd(2024, 5.0)],
                UnsecuredDebt=[_usd(2024, 6.0)],
                NotesPayable=[_usd(2024, 6.0)],
            )
        )
        self.assertEqual(totals[2024], 6.0)
        self.assertEqual(states[2024], "positive")

    def test_combined_amount_wins_over_smaller_long_term_debt(self):
        totals, states = compose_debt(
            _gaap(
                DebtLongtermAndShorttermCombinedAmount=[_usd(2024, 10.0)],
                LongTermDebt=[_usd(2024, 8.0)],
            )
        )
        self.assertEqual(totals[2024], 10.0)
        self.assertEqual(states[2024], "positive")


class TestComposeDebtRealGoldens(unittest.TestCase):
    """Trimmed live companyfacts (ladder tags + Liabilities, FY2025 annual only)."""

    FIXTURES = Path(__file__).resolve().parent / "fixtures"

    def _load(self, name: str) -> dict:
        return json.loads((self.FIXTURES / name).read_text(encoding="utf-8"))

    def test_cmg_known_zero_debt(self):
        # Chipotle FY2025 10-K: LongTermDebt explicitly 0, Liabilities 6.16B.
        # No interest-expense annual fact that year, so materiality does not
        # downgrade the explicit zero.
        payload = self._load("cmg_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], 0.0)
        self.assertEqual(states[2025], "zero")
        years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2025]["debt"], 0.0)
        self.assertEqual(statements[2025]["debt_state"], "zero")

    def test_aapl_levered_no_double_count(self):
        # Apple FY2025: LongTermDebt 90.678B (= noncurrent 78.328B + current
        # 12.350B, not added again) + CommercialPaper 7.979B = 98.657B.
        payload = self._load("aapl_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], 98_657_000_000.0)
        self.assertEqual(states[2025], "positive")

    def test_unknown_path_through_statements(self):
        payload = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {"units": {"USD": [_usd(2024, 10.0)]}},
                }
            }
        }
        years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2024]["debt"])
        self.assertEqual(statements[2024]["debt_state"], "unknown")

    def test_ddog_convertible_notes_only(self):
        # Datadog FY2025: no v1 ladder tags. ConvertibleLongTermNotesPayable
        # 983,449,000 is the debt total. InterestExpenseNonoperating is
        # positive and does not change a positive state.
        payload = self._load("ddog_debt_fy2025_companyfacts.json")
        convertible = 983_449_000.0
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], convertible)
        self.assertEqual(states[2025], "positive")
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2025]["debt"], convertible)
        self.assertEqual(statements[2025]["debt_state"], "positive")

    def test_ford_interest_without_ladder_is_not_zero(self):
        # Ford FY2025 us-gaap has Liabilities and InterestExpenseNonoperating
        # and none of the debt ladder tags. Liabilities-only would be zero;
        # interest above 0.15% of revenue downgrades that to unknown.
        # Debt total stays unset.
        payload = self._load("f_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertNotIn(2025, totals)
        self.assertNotEqual(states[2025], "zero")
        self.assertEqual(states[2025], "unknown")
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertIsNone(statements[2025]["debt"])
        self.assertEqual(statements[2025]["debt_state"], "unknown")

    def test_txt_material_interest_is_unknown(self):
        # Textron FY2025: no debt-ladder total. InterestIncomeExpenseNet is
        # a net expense above 0.15% of revenue, so liabilities-only is unknown.
        payload = self._load("txt_debt_fy2025_companyfacts.json")
        _totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(states[2025], "unknown")

    def test_ttd_immaterial_interest_stays_zero(self):
        # The Trade Desk FY2025: no debt-ladder tags. Interest is at or below
        # 0.15% of revenue and there is no maturity schedule, so zero stands.
        payload = self._load("ttd_debt_fy2025_companyfacts.json")
        _totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(states[2025], "zero")

    def test_lulu_line_of_credit_zero_only_is_zero(self):
        # lululemon FY2025: the only ladder fact is LineOfCredit = 0.
        # That partial zero follows the no-ladder path. Liabilities is
        # reported and interest is not material, so the state is zero.
        # Total stays 0.0.
        payload = self._load("lulu_debt_fy2025_companyfacts.json")
        totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(totals[2025], 0.0)
        self.assertEqual(states[2025], "zero")

    def test_cprt_no_ladder_immaterial_interest_is_zero(self):
        # Copart FY2026: no debt-ladder tags. Liabilities is reported.
        # InterestPaidNet is at or below 0.15% of revenue once the
        # including-assessed-tax fallback supplies revenue, so zero stands.
        payload = self._load("cprt_debt_fy2026_companyfacts.json")
        _totals, states = compose_debt(payload["facts"]["us-gaap"])
        self.assertEqual(states[2026], "zero")

    def test_cprt_revenue_falls_back_to_including_assessed_tax(self):
        payload = self._load("cprt_debt_fy2026_companyfacts.json")
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2026]["revenue"], 4_666_209_000.0)

    def test_revenue_fallback_does_not_override_earlier_tag(self):
        # Same FY: Revenues wins over the including-assessed-tax fallback.
        payload = {
            "facts": {
                "us-gaap": _gaap(
                    Revenues=[_usd(2024, 100.0)],
                    RevenueFromContractWithCustomerIncludingAssessedTax=[
                        _usd(2024, 120.0)
                    ],
                    NetIncomeLoss=[_usd(2024, 1.0)],
                )
            }
        }
        _years, statements = map_companyfacts_to_statements(payload)
        self.assertEqual(statements[2024]["revenue"], 100.0)
