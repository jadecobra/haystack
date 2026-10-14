"""#46: S&P 500 map regeneration from the Wikipedia constituents table."""

import json
import unittest

from app.sp500_map import _content, build_map, diff_summary, parse_constituents

PAGE = """<table id="constituents"><tbody><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>HQ</th></tr>
<tr><td><a>AAPL</a></td><td>Apple Inc.</td><td>Information Technology</td><td>Technology Hardware, Storage &amp; Peripherals</td><td>x</td></tr>
<tr><td>XOM</td><td>ExxonMobil</td><td>Energy</td><td>Integrated Oil &amp; Gas</td><td>x</td></tr>
</tbody></table>"""


class TestSp500Map(unittest.TestCase):
    def test_parse(self):
        rows = parse_constituents(PAGE)
        self.assertEqual([r["ticker"] for r in rows], ["AAPL", "XOM"])
        self.assertEqual(rows[0]["sub_industry"], "Technology Hardware, Storage & Peripherals")

    def test_bad_header_raises(self):
        with self.assertRaises(ValueError):
            parse_constituents(PAGE.replace("GICS Sector", "Sector"))

    def test_no_diff_ignores_dates(self):
        rows = parse_constituents(PAGE)
        a = build_map(rows, {}, "2026-10-01")
        b = build_map(rows, a, "2026-11-01")
        self.assertEqual(_content(a), _content(b))
        self.assertEqual(diff_summary(a, b), [])

    def test_diff_reports_changes(self):
        rows = parse_constituents(PAGE)
        old = build_map(rows, {}, "2026-10-01")
        new = json.loads(json.dumps(old))
        new["tickers"] = ["AAPL", "BE"]
        new["sectors"]["AAPL"] = "Energy"
        lines = diff_summary(old, new)
        self.assertIn("added: BE", lines)
        self.assertIn("removed: XOM", lines)
        self.assertTrue(any(l.startswith("sectors changed: AAPL") for l in lines))
