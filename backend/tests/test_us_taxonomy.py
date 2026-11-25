"""NASDAQ Screener ICB taxonomy snapshot building, validation, and lookup."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.us_taxonomy import (
    ICB_SECTOR_TO_GICS,
    MIN_ROWS,
    SCREENER_URL,
    TaxonomyEntry,
    _content,
    build_taxonomy,
    clear_cache,
    diff_summary,
    fetch_screener_rows,
    load_taxonomy,
    lookup_taxonomy,
    main,
    normalize_sector,
    ticker_candidates,
    write_taxonomy,
)

SAMPLE_SCREENER_ROWS = [
    {
        "symbol": "CRWV",
        "name": "CoreWeave Inc.",
        "sector": "Technology",
        "industry": "Computer Software: Prepackaged Software",
    },
    {
        "symbol": "sofi",
        "name": "SoFi Technologies",
        "sector": "Finance",
        "industry": "Finance: Consumer Services",
    },
    {
        "symbol": "BRK/B",
        "name": "Berkshire Hathaway",
        "sector": "",
        "industry": "",
    },
    {
        "symbol": "BLANK_IND",
        "name": "Blank Industry Corp",
        "sector": "Industrials",
        "industry": "   ",
    },
    {
        "symbol": "CRWV",
        "name": "CoreWeave Duplicate",
        "sector": "Energy",
        "industry": "Should Be Ignored",
    },
]


class TestNormalizeAndCandidates(unittest.TestCase):
    def test_normalize_sector_maps_all_11_icb_sectors_and_preserves_miscellaneous(self) -> None:
        expected = {
            "Basic Materials": "Materials",
            "Consumer Discretionary": "Consumer Discretionary",
            "Consumer Staples": "Consumer Staples",
            "Energy": "Energy",
            "Finance": "Financials",
            "Health Care": "Health Care",
            "Industrials": "Industrials",
            "Real Estate": "Real Estate",
            "Technology": "Information Technology",
            "Telecommunications": "Communication Services",
            "Utilities": "Utilities",
        }
        self.assertEqual(len(ICB_SECTOR_TO_GICS), 11)
        self.assertEqual(ICB_SECTOR_TO_GICS, expected)
        for icb, gics in expected.items():
            self.assertEqual(normalize_sector(icb), gics)
            self.assertEqual(normalize_sector(f"  {icb}  "), gics)
        self.assertEqual(normalize_sector("Miscellaneous"), "Miscellaneous")
        self.assertEqual(normalize_sector("  Miscellaneous  "), "Miscellaneous")

    def test_ticker_candidates_handles_plain_and_share_class_separators(self) -> None:
        self.assertEqual(ticker_candidates("aapl"), ["AAPL"])
        self.assertEqual(ticker_candidates(" brk.b "), ["BRK.B", "BRK-B", "BRK/B"])
        self.assertEqual(ticker_candidates("BRK-B"), ["BRK-B", "BRK.B", "BRK/B"])
        self.assertEqual(ticker_candidates("BRK/B"), ["BRK/B", "BRK.B", "BRK-B"])
        self.assertEqual(ticker_candidates("   "), [])


class TestBuildAndDiffTaxonomy(unittest.TestCase):
    def test_build_taxonomy_filters_blanks_deduplicates_and_enforces_min_rows(self) -> None:
        payload = build_taxonomy(SAMPLE_SCREENER_ROWS, "2026-11-24", min_rows=2)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["source"], SCREENER_URL)
        self.assertEqual(payload["retrieved"], "2026-11-24")
        self.assertEqual(payload["sector_map"], ICB_SECTOR_TO_GICS)
        self.assertEqual(list(payload["tickers"]), ["CRWV", "SOFI"])
        self.assertEqual(
            payload["tickers"]["CRWV"],
            {
                "sector": "Information Technology",
                "industry": "Computer Software: Prepackaged Software",
                "raw_sector": "Technology",
            },
        )
        self.assertEqual(
            payload["tickers"]["SOFI"],
            {
                "sector": "Financials",
                "industry": "Finance: Consumer Services",
                "raw_sector": "Finance",
            },
        )
        with self.assertRaises(ValueError):
            build_taxonomy(SAMPLE_SCREENER_ROWS, "2026-11-24", min_rows=3)

    def test_content_ignores_date_and_diff_summary_counts_changes(self) -> None:
        old = build_taxonomy(
            [
                {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
                {"symbol": "BBB", "sector": "Finance", "industry": "Banks"},
                {"symbol": "DEL", "sector": "Energy", "industry": "Oil"},
            ],
            "2026-10-01",
            min_rows=2,
        )
        same_content = build_taxonomy(
            [
                {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
                {"symbol": "BBB", "sector": "Finance", "industry": "Banks"},
                {"symbol": "DEL", "sector": "Energy", "industry": "Oil"},
            ],
            "2026-11-24",
            min_rows=2,
        )
        self.assertEqual(_content(old), _content(same_content))
        self.assertEqual(diff_summary(old, same_content), [])

        new = build_taxonomy(
            [
                {"symbol": "AAA", "sector": "Industrials", "industry": "Software"},
                {"symbol": "BBB", "sector": "Finance", "industry": "Asset Management"},
                {"symbol": "ADD", "sector": "Utilities", "industry": "Electric"},
            ],
            "2026-11-24",
            min_rows=2,
        )
        lines = diff_summary(old, new)
        joined = "\n".join(lines)
        self.assertIn("added", joined)
        self.assertIn("1", joined)
        self.assertIn("removed", joined)
        self.assertIn("sector", joined)
        self.assertIn("industr", joined)


class TestLoadLookupAndValidation(unittest.TestCase):
    def tearDown(self) -> None:
        clear_cache()

    def test_write_load_lookup_and_clear_cache(self) -> None:
        payload = build_taxonomy(
            [
                {"symbol": "CRWV", "sector": "Technology", "industry": "Computer Software: Prepackaged Software"},
                {"symbol": "BF.B", "sector": "Consumer Staples", "industry": "Beverages (Production/Distribution)"},
            ],
            "2026-11-24",
            min_rows=2,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "us_taxonomy.json"
            write_taxonomy(payload, path)
            entries = load_taxonomy(path)
            self.assertEqual(
                entries["CRWV"],
                TaxonomyEntry(
                    ticker="CRWV",
                    sector="Information Technology",
                    industry="Computer Software: Prepackaged Software",
                    raw_sector="Technology",
                ),
            )
            self.assertEqual(lookup_taxonomy("crwv", entries), entries["CRWV"])
            self.assertEqual(lookup_taxonomy("BF-B", entries), entries["BF.B"])
            self.assertEqual(lookup_taxonomy("BF/B", entries), entries["BF.B"])
            self.assertIsNone(lookup_taxonomy("MISSING", entries))
            self.assertIsNone(lookup_taxonomy("", entries))
            clear_cache()

    def test_malformed_json_schema_raises_value_error(self) -> None:
        bad_payloads: list[object] = [
            [],
            {"schema_version": 2, "tickers": {}},
            {"schema_version": 1, "tickers": []},
            {"schema_version": 1, "tickers": {"AAPL": "bad"}},
            {"schema_version": 1, "tickers": {"AAPL": {"sector": "", "industry": "Tech"}}},
            {"schema_version": 1, "tickers": {"AAPL": {"sector": "Information Technology", "industry": ""}}},
            {"schema_version": 1, "tickers": {"AAPL": {"sector": "Information Technology", "industry": 123}}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for idx, bad in enumerate(bad_payloads):
                path = Path(tmp) / f"bad_{idx}.json"
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_taxonomy(path)


class TestFetchAndCliMain(unittest.TestCase):
    def tearDown(self) -> None:
        clear_cache()

    def test_fetch_screener_rows_validates_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"data": {"rows": SAMPLE_SCREENER_ROWS}}), encoding="utf-8")
            self.assertEqual(len(fetch_screener_rows(good)), len(SAMPLE_SCREENER_ROWS))

            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"data": {"rows": None}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                fetch_screener_rows(bad)

    def test_main_dry_run_real_write_and_min_rows_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            screener_json = tmp_dir / "screener.json"
            screener_json.write_text(
                json.dumps({"data": {"rows": SAMPLE_SCREENER_ROWS}}),
                encoding="utf-8",
            )
            out_path = tmp_dir / "us_taxonomy.json"

            fail_code = main(
                ["--json", str(screener_json), "--path", str(out_path), "--min-rows", "10"]
            )
            self.assertEqual(fail_code, 2)
            self.assertFalse(out_path.exists())

            dry_code = main(
                [
                    "--dry-run",
                    "--json",
                    str(screener_json),
                    "--path",
                    str(out_path),
                    "--min-rows",
                    "2",
                ]
            )
            self.assertEqual(dry_code, 0)
            self.assertFalse(out_path.exists())

            write_code = main(
                ["--json", str(screener_json), "--path", str(out_path), "--min-rows", "2"]
            )
            self.assertEqual(write_code, 0)
            self.assertTrue(out_path.exists())
            loaded = load_taxonomy(out_path)
            self.assertEqual(set(loaded), {"CRWV", "SOFI"})

    def test_main_overwrites_corrupt_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            screener_json = tmp_dir / "screener.json"
            screener_json.write_text(
                json.dumps({"data": {"rows": SAMPLE_SCREENER_ROWS}}),
                encoding="utf-8",
            )
            out_path = tmp_dir / "us_taxonomy.json"
            out_path.write_text("{corrupt", encoding="utf-8")

            code = main(
                ["--json", str(screener_json), "--path", str(out_path), "--min-rows", "2"]
            )
            self.assertEqual(code, 0)
            self.assertEqual(set(load_taxonomy(out_path)), {"CRWV", "SOFI"})


class TestCommittedSnapshot(unittest.TestCase):
    def tearDown(self) -> None:
        clear_cache()

    def test_committed_snapshot_loads_offline_and_contains_expected_entries(self) -> None:
        entries = load_taxonomy()
        self.assertGreaterEqual(len(entries), MIN_ROWS)

        crwv = lookup_taxonomy("CRWV")
        self.assertIsNotNone(crwv)
        assert crwv is not None
        self.assertEqual(crwv.sector, "Information Technology")
        self.assertEqual(crwv.industry, "Computer Software: Prepackaged Software")

        sofi = lookup_taxonomy("SOFI")
        self.assertIsNotNone(sofi)
        assert sofi is not None
        self.assertEqual(sofi.sector, "Financials")

        realty_income = lookup_taxonomy("O")
        self.assertIsNotNone(realty_income)
        assert realty_income is not None
        self.assertEqual(realty_income.sector, "Real Estate")

        self.assertIsNone(lookup_taxonomy("BRK.B"))
