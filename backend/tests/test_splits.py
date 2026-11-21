"""Post-filing stock split adjustments for statements and quotes (#139)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import edgar, quote


def _entry(
    *,
    start: str,
    end: str,
    val: float,
    fy: int,
    filed: str,
    form: str = "10-K",
    fp: str = "FY",
) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def _sndk_payload(
    *,
    extra_shares: list[dict] | None = None,
    extra_gaap: dict | None = None,
) -> dict:
    shares = [
        _entry(
            start="2025-06-28",
            end="2026-07-03",
            val=155_000_000.0,
            fy=2026,
            filed="2026-08-17",
        ),
        _entry(
            start="2024-06-29",
            end="2025-06-27",
            val=145_000_000.0,
            fy=2025,
            filed="2025-08-21",
        ),
    ]
    if extra_shares:
        shares.extend(extra_shares)
    revenues = [
        _entry(
            start="2025-06-28",
            end="2026-07-03",
            val=20_248_000_000.0,
            fy=2026,
            filed="2026-08-17",
        ),
        _entry(
            start="2024-06-29",
            end="2025-06-27",
            val=7_355_000_000.0,
            fy=2025,
            filed="2025-08-21",
        ),
    ]
    net_income = [
        _entry(
            start="2025-06-28",
            end="2026-07-03",
            val=11_433_000_000.0,
            fy=2026,
            filed="2026-08-17",
        ),
        _entry(
            start="2024-06-29",
            end="2025-06-27",
            val=-1_641_000_000.0,
            fy=2025,
            filed="2025-08-21",
        ),
    ]
    us_gaap: dict = {
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": shares}},
        "Revenues": {"units": {"USD": revenues}},
        "NetIncomeLoss": {"units": {"USD": net_income}},
    }
    if extra_gaap:
        us_gaap.update(extra_gaap)
    return {
        "cik": "0002023554",
        "entityName": "Sandisk Corporation",
        "facts": {"us-gaap": us_gaap},
    }


def _yahoo_splits_payload(ts: int, numerator: float, denominator: float) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "SNDK"},
                    "events": {
                        "splits": {
                            str(ts): {
                                "date": ts,
                                "numerator": numerator,
                                "denominator": denominator,
                                "splitRatio": f"{int(numerator)}:{int(denominator)}",
                            }
                        }
                    },
                }
            ]
        }
    }


def _fake_yahoo_client(payload: dict):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers") or {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, *args, **kwargs):
            if "query1.finance.yahoo.com/v8/finance/chart/" in url:
                return _Resp()
            raise AssertionError(url)

    return _Client


class TestPostFilingSplits(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cache_patch = mock.patch.object(quote, "_CACHE_DIR", Path(self._tmp.name))
        self._cache_patch.start()
        self.addCleanup(self._cache_patch.stop)

    def _run_statements(self, companyfacts: dict, splits_payload: dict):
        with (
            mock.patch.object(edgar, "resolve_cik", return_value="2023554"),
            mock.patch.object(edgar, "fetch_companyfacts", return_value=companyfacts),
            mock.patch.object(edgar, "predecessor_ciks", return_value=[]),
            mock.patch.object(quote.httpx, "Client", _fake_yahoo_client(splits_payload)),
        ):
            return edgar.statements_for_ticker("SNDK")

    def test_split_after_latest_filing_adjusts_shares(self):
        splits = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        _years, statements, _cik, _name = self._run_statements(_sndk_payload(), splits)
        self.assertEqual(statements[2026]["shares"], 1_240_000_000.0)
        self.assertEqual(statements[2025]["shares"], 1_160_000_000.0)

    def test_no_double_adjust_after_restating_10q(self):
        extra_shares = [
            _entry(
                start="2025-06-28",
                end="2025-09-26",
                val=146_000_000.0,
                fy=2026,
                filed="2025-11-05",
                form="10-Q",
                fp="Q1",
            ),
            _entry(
                start="2025-06-28",
                end="2025-09-26",
                val=146_000_000.0 * 8.0,
                fy=2027,
                filed="2026-12-10",
                form="10-Q",
                fp="Q1",
            ),
        ]
        splits = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        _years, statements, _cik, _name = self._run_statements(
            _sndk_payload(extra_shares=extra_shares), splits
        )
        self.assertEqual(statements[2026]["shares"], 1_240_000_000.0)
        self.assertEqual(statements[2025]["shares"], 1_160_000_000.0)

    def test_split_before_latest_filing_ignored(self):
        splits = _yahoo_splits_payload(1735732800, 8.0, 1.0)
        _years, statements, _cik, _name = self._run_statements(_sndk_payload(), splits)
        self.assertEqual(statements[2026]["shares"], 155_000_000.0)
        self.assertEqual(statements[2025]["shares"], 145_000_000.0)

    def test_reported_dps_divided_by_split(self):
        extra_gaap = {
            "CommonStockDividendsPerShareDeclared": {
                "units": {
                    "USD/shares": [
                        _entry(
                            start="2025-06-28",
                            end="2026-07-03",
                            val=0.8,
                            fy=2026,
                            filed="2026-08-17",
                        )
                    ]
                }
            },
            "PaymentsOfDividends": {
                "units": {
                    "USD": [
                        _entry(
                            start="2025-06-28",
                            end="2026-07-03",
                            val=250_000_000.0,
                            fy=2026,
                            filed="2026-08-17",
                        )
                    ]
                }
            },
        }
        splits = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        _years, statements, _cik, _name = self._run_statements(
            _sndk_payload(extra_gaap=extra_gaap), splits
        )
        self.assertAlmostEqual(statements[2026]["dividends_per_share"], 0.1)

    def test_recent_splits_parses_yahoo_payload(self):
        splits_payload = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        with mock.patch.object(quote.httpx, "Client", _fake_yahoo_client(splits_payload)):
            parsed = quote.recent_splits("SNDK")
        self.assertEqual(parsed, [quote.Split(date(2026, 11, 20), 8.0)])
