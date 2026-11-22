"""Post-filing stock split adjustments for statements and quotes (#139)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import httpx

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
            parts = urlsplit(url)
            if parts.hostname == "query1.finance.yahoo.com" and parts.path.startswith(
                "/v8/finance/chart/"
            ):
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

    def test_recent_splits_disk_cache_ttl_and_empty_list(self):
        calls: list[tuple[str, dict, dict, float | None]] = []

        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        def _make_client(payload):
            class _Client:
                def __init__(self, *args, **kwargs):
                    self._headers = kwargs.get("headers") or {}
                    self._timeout = kwargs.get("timeout")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def get(self, url, *args, **kwargs):
                    calls.append((url, kwargs.get("params") or {}, dict(self._headers), self._timeout))
                    return _Resp(payload)

            return _Client

        splits_payload = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        with mock.patch.object(quote.httpx, "Client", _make_client(splits_payload)):
            first = quote.recent_splits("sndk")
            second = quote.recent_splits("SNDK")
        self.assertEqual(first, [quote.Split(date(2026, 11, 20), 8.0)])
        self.assertEqual(second, first)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            "https://query1.finance.yahoo.com/v8/finance/chart/SNDK",
        )
        self.assertEqual(
            calls[0][1],
            {"range": "2y", "interval": "3mo", "events": "splits"},
        )
        self.assertEqual(calls[0][2].get("User-Agent"), quote._UA)
        self.assertEqual(calls[0][3], 5.0)
        cache_path = Path(self._tmp.name) / "SNDK.splits.json"
        self.assertEqual(
            json.loads(cache_path.read_text(encoding="utf-8")),
            [{"ex_date": "2026-11-20", "ratio": 8.0}],
        )

        calls.clear()
        empty_payload = {"chart": {"result": [{"meta": {"symbol": "NONE"}}]}}
        with mock.patch.object(quote.httpx, "Client", _make_client(empty_payload)):
            self.assertEqual(quote.recent_splits("NONE"), [])
            self.assertEqual(quote.recent_splits("NONE"), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            json.loads((Path(self._tmp.name) / "NONE.splits.json").read_text(encoding="utf-8")),
            [],
        )

    def test_recent_splits_stale_cache_fallback_and_fail_soft(self):
        class _FailingClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, *args, **kwargs):
                raise httpx.ConnectError("network down")

        with mock.patch.object(quote.httpx, "Client", _FailingClient):
            self.assertEqual(quote.recent_splits("FAIL"), [])
            self.assertEqual(quote.recent_splits(""), [])

        cache_path = Path(self._tmp.name) / "SNDK.splits.json"
        cache_path.write_text(
            json.dumps([{"ex_date": "2026-11-20", "ratio": 8.0}]),
            encoding="utf-8",
        )
        stale_ts = time.time() - quote._CACHE_TTL_S - 60
        os.utime(cache_path, (stale_ts, stale_ts))
        with mock.patch.object(quote.httpx, "Client", _FailingClient):
            self.assertEqual(
                quote.recent_splits("SNDK"),
                [quote.Split(date(2026, 11, 20), 8.0)],
            )

    def test_parse_yahoo_splits_reverse_and_skips_malformed(self):
        payload = {
            "chart": {
                "result": [
                    {
                        "events": {
                            "splits": {
                                "rev": {"date": 1795185000, "numerator": 1, "denominator": 10},
                                "zero_num": {"date": 1795185000, "numerator": 0, "denominator": 1},
                                "neg_den": {"date": 1795185000, "numerator": 2, "denominator": -1},
                                "missing_den": {"date": 1795185000, "numerator": 2},
                                "bool_num": {"date": 1795185000, "numerator": True, "denominator": 1},
                                "bad_date": {"date": "nope", "numerator": 2, "denominator": 1},
                                "not_dict": "bad",
                            }
                        }
                    }
                ]
            }
        }
        parsed = quote._parse_yahoo_splits(payload)
        self.assertEqual(parsed, [quote.Split(date(2026, 11, 20), 0.1)])

    def test_apply_market_splits_and_latest_filed_edge_cases(self):
        self.assertIsNone(edgar.latest_filed({}))
        payload = _sndk_payload()
        self.assertEqual(edgar.latest_filed(payload), date(2026, 8, 17))

        rows = {
            2026: {
                "shares": 100.0,
                "dividends_per_share": 0.8,
                "owner_earnings": 500.0,
                "dividends": 50.0,
            },
            2025: {
                "shares": None,
                "dividends_per_share": None,
                "owner_earnings": 400.0,
                "dividends": None,
            },
        }
        edgar.apply_market_splits(
            rows,
            [
                quote.Split(date(2026, 8, 17), 5.0),
                quote.Split(date(2026, 9, 1), 2.0),
                quote.Split(date(2026, 11, 20), 4.0),
            ],
            basis=date(2026, 8, 17),
        )
        self.assertEqual(rows[2026]["shares"], 800.0)
        self.assertAlmostEqual(rows[2026]["dividends_per_share"], 0.1)
        self.assertEqual(rows[2026]["owner_earnings"], 500.0)
        self.assertEqual(rows[2026]["dividends"], 50.0)
        self.assertIsNone(rows[2025]["shares"])
        self.assertIsNone(rows[2025]["dividends_per_share"])

        edgar.apply_market_splits(
            rows,
            [quote.Split(date(2026, 11, 20), 8.0)],
            basis=None,
        )
        self.assertEqual(rows[2026]["shares"], 800.0)

    def test_traversal_ticker_rejected(self):
        self.assertEqual(quote.recent_splits("../etc/passwd"), [])
        self.assertIsNone(quote.previous_close("../etc/passwd"))
        self.assertIsNone(quote._read_json("../escape.json", max_age_s=None))
        with self.assertRaises(ValueError):
            quote._write_json("../escape.json", {})

    def test_yahoo_splits_normalizes_dotted_ticker(self):
        quote._mem.clear()
        requested_urls: list[str] = []
        splits_payload = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        quote_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "previousClose": 450.0,
                            "regularMarketTime": 1795185000,
                        }
                    }
                ]
            }
        }

        class _Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, *args, **kwargs):
                requested_urls.append(url)
                params = kwargs.get("params") or {}
                if params.get("events") == "splits":
                    return _Resp(splits_payload)
                return _Resp(quote_payload)

        with mock.patch.object(quote.httpx, "Client", _Client):
            splits = quote.recent_splits("BRK.B")
            prev = quote.previous_close("BRK.B")
        self.assertEqual(splits, [quote.Split(date(2026, 11, 20), 8.0)])
        self.assertEqual(prev, {"price": 450.0, "as_of": "2026-11-20"})
        self.assertEqual(
            requested_urls,
            [
                "https://query1.finance.yahoo.com/v8/finance/chart/BRK-B",
                "https://query1.finance.yahoo.com/v8/finance/chart/BRK-B",
            ],
        )
        self.assertTrue((Path(self._tmp.name) / "BRK.B.splits.json").is_file())

    def test_recent_splits_falls_back_to_query2_then_cnbc(self):
        calls: list[str] = []
        splits_payload = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        future_ex = (date.today() + timedelta(days=30)).strftime("%m/%d/%Y")

        class _Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        def _make_client(mode: str):
            class _Client:
                def __init__(self, *args, **kwargs):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def get(self, url, *args, **kwargs):
                    calls.append(url)
                    host = urlsplit(url).hostname
                    if host == "query1.finance.yahoo.com":
                        if mode == "empty":
                            return _Resp({"chart": {"result": [{"meta": {"symbol": "NONE"}}]}})
                        raise httpx.ConnectError("query1 down")
                    if host == "query2.finance.yahoo.com":
                        if mode == "query2":
                            return _Resp(splits_payload)
                        raise httpx.ConnectError("query2 down")
                    if host == "quote.cnbc.com":
                        ex = future_ex if mode == "cnbc_future" else "11/20/2026"
                        factor = "0.5" if mode == "cnbc_future" else "0.125"
                        return _Resp(
                            {
                                "FormattedQuoteResult": {
                                    "FormattedQuote": [
                                        {
                                            "EventData": {
                                                "split_ex_date": ex,
                                                "split_factor": factor,
                                            }
                                        }
                                    ]
                                }
                            }
                        )
                    raise AssertionError(url)

            return _Client

        with mock.patch.object(quote.httpx, "Client", _make_client("query2")):
            self.assertEqual(
                quote.recent_splits("SNDK"),
                [quote.Split(date(2026, 11, 20), 8.0)],
            )

        with mock.patch.object(quote.httpx, "Client", _make_client("cnbc")):
            self.assertEqual(
                quote.recent_splits("AAPL"),
                [quote.Split(date(2026, 11, 20), 8.0)],
            )

        with mock.patch.object(quote.httpx, "Client", _make_client("cnbc_future")):
            self.assertEqual(quote.recent_splits("FUTR"), [])

        calls.clear()
        with mock.patch.object(quote.httpx, "Client", _make_client("empty")):
            self.assertEqual(quote.recent_splits("NONE"), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(urlsplit(calls[0]).hostname, "query1.finance.yahoo.com")

    def test_non_restating_10q_does_not_suppress_post_10k_split(self):
        payload = _sndk_payload(
            extra_shares=[
                _entry(
                    start="2026-07-04",
                    end="2026-10-02",
                    val=1_200_000_000.0,
                    fy=2027,
                    filed="2026-12-01",
                    form="10-Q",
                    fp="Q1",
                )
            ]
        )
        payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(
            _entry(
                start="2026-07-04",
                end="2026-10-02",
                val=5_000_000_000.0,
                fy=2027,
                filed="2026-12-01",
                form="10-Q",
                fp="Q1",
            )
        )
        splits = _yahoo_splits_payload(1795185000, 8.0, 1.0)
        _years, statements, _cik, _name = self._run_statements(payload, splits)
        self.assertEqual(statements[2026]["shares"], 1_240_000_000.0)
        self.assertEqual(statements[2025]["shares"], 1_160_000_000.0)

    def test_multiclass_share_classes_uses_10k_basis_not_10q(self):
        payload = {
            "cik": "0001403161",
            "entityName": "Visa Inc.",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                _entry(
                                    start="2024-10-01",
                                    end="2025-09-30",
                                    val=35_900_000_000.0,
                                    fy=2025,
                                    filed="2025-11-12",
                                ),
                                _entry(
                                    start="2026-10-01",
                                    end="2026-12-31",
                                    val=10_000_000_000.0,
                                    fy=2027,
                                    filed="2026-12-01",
                                    form="10-Q",
                                    fp="Q1",
                                ),
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                _entry(
                                    start="2024-10-01",
                                    end="2025-09-30",
                                    val=20_058_000_000.0,
                                    fy=2025,
                                    filed="2025-11-12",
                                )
                            ]
                        }
                    },
                }
            },
        }
        splits = _yahoo_splits_payload(1795185000, 2.0, 1.0)
        with (
            mock.patch.object(edgar, "resolve_cik", return_value="1403161"),
            mock.patch.object(edgar, "fetch_companyfacts", return_value=payload),
            mock.patch.object(edgar, "predecessor_ciks", return_value=[]),
            mock.patch.object(quote.httpx, "Client", _fake_yahoo_client(splits)),
        ):
            _years, statements, _cik, _name = edgar.statements_for_ticker("V")
        self.assertEqual(statements[2025]["shares"], 3_932_000_000.0)

    def test_recent_splits_logs_warning_when_all_sources_fail(self):
        class _FailingClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, *args, **kwargs):
                raise httpx.ConnectError("all down")

        with (
            mock.patch.object(quote.httpx, "Client", _FailingClient),
            self.assertLogs("app.quote", level="WARNING") as cm,
        ):
            self.assertEqual(quote.recent_splits("FAIL"), [])
        self.assertTrue(
            any("FAIL" in msg and "no cache" in msg for msg in cm.output), cm.output
        )

        cache_path = Path(self._tmp.name) / "FAIL.splits.json"
        cache_path.write_text(
            json.dumps([{"ex_date": "2026-11-20", "ratio": 8.0}]),
            encoding="utf-8",
        )
        stale_ts = time.time() - quote._CACHE_TTL_S - 60
        os.utime(cache_path, (stale_ts, stale_ts))
        with (
            mock.patch.object(quote.httpx, "Client", _FailingClient),
            self.assertLogs("app.quote", level="WARNING") as cm_stale,
        ):
            self.assertEqual(
                quote.recent_splits("FAIL"),
                [quote.Split(date(2026, 11, 20), 8.0)],
            )
        self.assertTrue(
            any("FAIL" in msg and "stale cache" in msg for msg in cm_stale.output),
            cm_stale.output,
        )
