"""S&P 1500 constituent map parsing, validation, and diffing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.sp1500_map import (
    INDEX_IDS,
    INDEX_SPECS,
    VALID_SCREEN_UNIVERSES,
    VALID_UNIVERSES,
    Constituent,
    ConstituentRow,
    IndexSpec,
    _content,
    build_map,
    clear_cache,
    diff_summary,
    fetch_index_rows,
    index_tickers,
    load_constituents,
    lookup_constituent,
    main,
    parse_constituents,
    parse_universe,
    universe_tickers,
    write_map,
)

SP500_PAGE = """<table id="constituents"><tbody>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date added</th><th>CIK</th><th>Founded</th></tr>
<tr><td><a>AAPL</a></td><td>Apple Inc.</td><td>Information Technology</td><td>Technology Hardware, Storage &amp; Peripherals</td><td>Cupertino, CA</td><td>1982-11-30</td><td>0000320193</td><td>1977</td></tr>
<tr><td>BRK.B<sup>[1]</sup></td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td><td>Omaha, NE</td><td>2010-02-16</td><td>0001067983</td><td>1839</td></tr>
</tbody></table>"""

SP400_PAGE = """<table id="constituents"><tbody>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>Headquarters Location</th><th>SEC filings</th></tr>
<tr><td><a>COLM</a></td><td>Columbia Sportswear</td><td>Consumer Discretionary</td><td>Apparel, Accessories &amp; Luxury Goods</td><td>Portland, OR</td><td>view</td></tr>
<tr><td><a>WAL</a></td><td>Western Alliance Bancorporation</td><td>Financials</td><td>Regional Banks</td><td>Phoenix, AZ</td><td>view</td></tr>
</tbody></table>"""

SP600_PAGE = """<table id="constituents"><tbody>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>Headquarters Location</th><th>SEC filings</th><th>CIK</th></tr>
<tr><td><a>UAA</a></td><td>Under Armour (Class A)</td><td>Consumer Discretionary</td><td>Apparel, Accessories &amp; Luxury Goods</td><td>Baltimore, MD</td><td>view</td><td>0001336917</td></tr>
<tr><td><a data-mw='{"html":"&lt;a href=\\"https://www.nyse.com\\"&gt;x&lt;/a&gt;>PRK"}'>PRK</a></td><td>Park National Bank</td><td>Financials</td><td>Regional Banks</td><td>Newark, OH</td><td>view</td><td>0000805676</td></tr>
<tr><td><a>AAMI</a></td><td>Acadian Asset Management</td><td>Financials</td><td>Asset Management &amp; Custody Banks</td><td>Boston, MA</td><td>view</td><td>0001748824</td></tr>
</tbody></table>"""

REORDERED_NO_ID_PAGE = """<table><tr><th>Nav</th></tr><tr><td>Links</td></tr></table>
<table class="wikitable sortable"><tbody>
<tr><th>Security</th><th>GICS Sub-Industry<sup>[a]</sup></th><th>Ticker symbol</th><th>GICS Sector</th></tr>
<tr><td>Example Corp</td><td>Packaged Foods &amp; Meats</td><td>EXMP<sup>[2]</sup></td><td>Consumer Staples</td></tr>
</tbody></table>"""


def _html_table(rows: list[tuple[str, str, str, str]]) -> str:
    body = "\n".join(
        f"<tr><td>{t}</td><td>{n}</td><td>{s}</td><td>{sub}</td></tr>"
        for t, n, s, sub in rows
    )
    return (
        '<table id="constituents"><tbody>'
        "<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>"
        f"{body}</tbody></table>"
    )


class TestParseConstituents(unittest.TestCase):
    def test_parses_all_three_wikipedia_table_formats(self):
        r500 = parse_constituents(SP500_PAGE)
        self.assertEqual([r.ticker for r in r500], ["AAPL", "BRK.B"])
        self.assertEqual(r500[0].sub_industry, "Technology Hardware, Storage & Peripherals")

        r400 = parse_constituents(SP400_PAGE)
        self.assertEqual([r.ticker for r in r400], ["COLM", "WAL"])
        self.assertEqual(r400[1].sector, "Financials")

        r600 = parse_constituents(SP600_PAGE)
        self.assertEqual([r.ticker for r in r600], ["UAA", "PRK", "AAMI"])
        self.assertEqual(r600[0].sub_industry, "Apparel, Accessories & Luxury Goods")

    def test_fallback_without_constituents_id_and_reordered_headers(self):
        rows = parse_constituents(REORDERED_NO_ID_PAGE)
        self.assertEqual(
            rows,
            [
                ConstituentRow(
                    ticker="EXMP",
                    name="Example Corp",
                    sector="Consumer Staples",
                    sub_industry="Packaged Foods & Meats",
                )
            ],
        )

    def test_bad_header_raises(self):
        with self.assertRaises(ValueError):
            parse_constituents(SP500_PAGE.replace("GICS Sector", "Sector"))

    def test_missing_table_raises(self):
        with self.assertRaises(ValueError):
            parse_constituents("<table><tr><th>Foo</th></tr><tr><td>Bar</td></tr></table>")

    def test_empty_ticker_or_sector_raises(self):
        with self.assertRaises(ValueError):
            parse_constituents(_html_table([("", "No Ticker", "Energy", "Oil")]))
        with self.assertRaises(ValueError):
            parse_constituents(_html_table([("ABC", "No Sector", "", "Oil")]))


class TestFetchIndexRows(unittest.TestCase):
    def test_min_rows_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "small.html"
            html_path.write_text(SP400_PAGE, encoding="utf-8")
            spec = IndexSpec("sp400", "S&P 400", "https://example.invalid", 10)
            with self.assertRaises(ValueError):
                fetch_index_rows(spec, html_path=html_path)
            ok_spec = IndexSpec("sp400", "S&P 400", "https://example.invalid", 2)
            rows = fetch_index_rows(ok_spec, html_path=html_path)
            self.assertEqual(len(rows), 2)


class TestBuildAndDiffMap(unittest.TestCase):
    def test_overlap_precedence_and_order(self):
        rows_by_index = {
            "sp500": [ConstituentRow("AAPL", "Apple", "Information Technology", "Tech")],
            "sp400": [
                ConstituentRow("AAPL", "Apple Dup", "Information Technology", "Tech"),
                ConstituentRow("COLM", "Columbia", "Consumer Discretionary", "Apparel"),
            ],
            "sp600": [
                ConstituentRow("COLM", "Columbia Dup", "Consumer Discretionary", "Apparel"),
                ConstituentRow("UAA", "Under Armour", "Consumer Discretionary", "Apparel"),
            ],
        }
        payload, warnings = build_map(rows_by_index, "2026-11-23")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(list(payload["constituents"]), ["AAPL", "COLM", "UAA"])
        self.assertEqual(payload["constituents"]["AAPL"]["index"], "sp500")
        self.assertEqual(payload["constituents"]["COLM"]["index"], "sp400")
        self.assertEqual(payload["constituents"]["UAA"]["index"], "sp600")
        self.assertEqual(
            warnings,
            [
                "overlap: AAPL kept in sp500, skipped in sp400",
                "overlap: COLM kept in sp400, skipped in sp600",
            ],
        )

    def test_content_ignores_date_and_diff_reports_grouped_changes(self):
        old_rows = {
            "sp500": [ConstituentRow("AAPL", "Apple", "Information Technology", "Tech")],
            "sp400": [ConstituentRow("FIX", "Comfort", "Industrials", "Building Products")],
            "sp600": [ConstituentRow("OLD", "Old Co", "Energy", "Oil")],
        }
        old, _ = build_map(old_rows, "2026-10-01")
        same, _ = build_map(old_rows, "2026-11-01")
        self.assertEqual(_content(old), _content(same))
        self.assertEqual(diff_summary(old, same), [])

        new_rows = {
            "sp500": [
                ConstituentRow("AAPL", "Apple", "Energy", "Oil & Gas"),
                ConstituentRow("FIX", "Comfort", "Industrials", "Building Products"),
            ],
            "sp400": [ConstituentRow("COLM", "Columbia", "Consumer Discretionary", "Apparel")],
            "sp600": [],
        }
        new, _ = build_map(new_rows, "2026-11-23")
        lines = diff_summary(old, new)
        self.assertIn("added [sp400]: COLM", lines)
        self.assertIn("removed [sp600]: OLD", lines)
        self.assertIn("index changed: FIX sp400 -> sp500", lines)
        self.assertIn("sectors changed: AAPL Information Technology -> Energy", lines)
        self.assertIn("sub_industries changed: AAPL Tech -> Oil & Gas", lines)


class TestLoadAndWriteMap(unittest.TestCase):
    def tearDown(self):
        clear_cache()

    def test_write_load_and_index_tickers(self):
        rows_by_index = {
            "sp500": parse_constituents(SP500_PAGE),
            "sp400": parse_constituents(SP400_PAGE),
            "sp600": parse_constituents(SP600_PAGE),
        }
        payload, _ = build_map(rows_by_index, "2026-11-23")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sp1500_map.json"
            write_map(payload, path)
            loaded = load_constituents(path)
            self.assertEqual(
                loaded["COLM"],
                Constituent(
                    ticker="COLM",
                    index="sp400",
                    sector="Consumer Discretionary",
                    sub_industry="Apparel, Accessories & Luxury Goods",
                ),
            )
            self.assertEqual(index_tickers("sp500", path=path), ["AAPL", "BRK.B"])
            self.assertEqual(index_tickers("sp400", path=path), ["COLM", "WAL"])
            self.assertEqual(index_tickers("sp600", path=path), ["UAA", "PRK", "AAMI"])
            self.assertEqual(
                universe_tickers("sp1500", path=path),
                ["AAPL", "BRK.B", "COLM", "WAL", "UAA", "PRK", "AAMI"],
            )
            self.assertEqual(universe_tickers("sp400", path=path), ["COLM", "WAL"])

            self.assertEqual(lookup_constituent("BRK-B", loaded), loaded["BRK.B"])
            self.assertEqual(lookup_constituent(" brk.b ", loaded), loaded["BRK.B"])
            self.assertIsNone(lookup_constituent("MISSING", loaded))
            self.assertIsNone(lookup_constituent("", loaded))

    def test_parse_universe_and_constants(self):
        self.assertEqual(INDEX_IDS, ("sp500", "sp400", "sp600"))
        self.assertEqual(VALID_UNIVERSES, ("sp1500", "sp500", "sp400", "sp600"))
        self.assertEqual(VALID_SCREEN_UNIVERSES, ("sp500", "sp1500"))
        self.assertEqual(parse_universe(" SP1500 "), "sp1500")
        self.assertEqual(parse_universe("sp400"), "sp400")
        with self.assertRaises(ValueError):
            parse_universe("sp999")

    def test_invalid_json_schema_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"constituents": {"BAD": {"index": "sp999", "sector": "Tech"}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_constituents(path)


class TestCliMain(unittest.TestCase):
    def test_main_refuses_under_min_rows_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            p500 = tmp_dir / "sp500.html"
            p400 = tmp_dir / "sp400.html"
            p600 = tmp_dir / "sp600.html"
            out = tmp_dir / "out.json"
            p500.write_text(SP500_PAGE, encoding="utf-8")
            p400.write_text(SP400_PAGE, encoding="utf-8")
            p600.write_text(SP600_PAGE, encoding="utf-8")
            code = main(
                [
                    "--html-sp500", str(p500),
                    "--html-sp400", str(p400),
                    "--html-sp600", str(p600),
                    "--path", str(out),
                ]
            )
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())

    def test_main_writes_when_above_min_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            pages = {}
            for spec in INDEX_SPECS:
                rows = [
                    (f"{spec.index.upper()}{i}", f"Company {i}", "Industrials", "Machinery")
                    for i in range(spec.min_rows)
                ]
                html_file = tmp_dir / f"{spec.index}.html"
                html_file.write_text(_html_table(rows), encoding="utf-8")
                pages[spec.index] = html_file
            out = tmp_dir / "out.json"
            dry_code = main(
                [
                    "--dry-run",
                    "--html-sp500", str(pages["sp500"]),
                    "--html-sp400", str(pages["sp400"]),
                    "--html-sp600", str(pages["sp600"]),
                    "--path", str(out),
                ]
            )
            self.assertEqual(dry_code, 0)
            self.assertFalse(out.exists())

            write_code = main(
                [
                    "--html-sp500", str(pages["sp500"]),
                    "--html-sp400", str(pages["sp400"]),
                    "--html-sp600", str(pages["sp600"]),
                    "--path", str(out),
                ]
            )
            self.assertEqual(write_code, 0)
            self.assertTrue(out.exists())
            self.assertEqual(len(index_tickers("sp500", path=out)), 480)
            self.assertEqual(len(index_tickers("sp400", path=out)), 380)
            self.assertEqual(len(index_tickers("sp600", path=out)), 570)
