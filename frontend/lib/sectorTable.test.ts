import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  groupForTicker, groupRows, parseSectorRow, resolveSlug, sectorCells, sectorSlug,
  groupCountNote, type SectorRow,
} from "./sectorTable.ts";

const row = (ticker: string, oe: number, sub: string, sector: string, extra: Partial<SectorRow> = {}): SectorRow => ({
  ticker, name: `${ticker} Inc`, oe_yield: oe, payback_years: null, ni_to_equity: null,
  debt_to_equity: null, no_debt: null, fy: 2025, sector, sub_industry: sub, ...extra,
});
const HW = "Technology Hardware, Storage & Peripherals";
const IT = "Information Technology";
const rows = [
  row("AAPL", 0.03, HW, IT), row("DELL", 0.08, HW, IT), row("MSFT", 0.025, "Systems Software", IT),
  row("XOM", 0.06, "Integrated Oil & Gas", "Energy"),
];

describe("sectorSlug", () => {
  it("slugs names with & and commas", () => {
    assert.equal(sectorSlug(HW), "technology-hardware-storage-and-peripherals");
    assert.equal(sectorSlug(IT), "information-technology");
  });
});

describe("groupRows", () => {
  it("sorts by OE yield and caps", () => {
    const g = groupRows(rows, "sector", IT, 2);
    assert.deepEqual(g.rows.map((r) => r.ticker), ["DELL", "AAPL"]);
    assert.equal(g.total, 3);
    assert.equal(groupCountNote(g), "Top 2 of 3 names");
  });
});

describe("resolveSlug", () => {
  it("prefers sub-industry, then sector, else null", () => {
    assert.equal(resolveSlug(rows, "technology-hardware-storage-and-peripherals")?.level, "sub_industry");
    const sec = resolveSlug(rows, "information-technology");
    assert.equal(sec?.level, "sector");
    assert.equal(sec?.total, 3);
    assert.equal(resolveSlug(rows, "nope"), null);
  });
});

describe("groupForTicker", () => {
  it("uses the ticker's sub-industry", () => {
    const g = groupForTicker(rows, "aapl", null, null);
    assert.equal(g?.name, HW);
    assert.equal(g?.sector, IT);
  });
  it("falls back to sector when the sub-industry has no rows", () => {
    assert.equal(groupForTicker(rows, "ZZZ", "Nothing Here", "Energy")?.level, "sector");
  });
});

describe("parse and cells", () => {
  it("formats columns and dashes unknowns", () => {
    const r = parseSectorRow({ ticker: "jpm", name: "JPMorgan", oe_yield: 0.05, fy: 2025, payback_years: 20,
      ni_to_equity: 0.165, debt_to_equity: null, no_debt: null, sector: "Financials", sub_industry: "Diversified Banks" });
    assert.ok(r);
    assert.deepEqual(sectorCells(r), ["JPMorgan", "5.0%", "20.0", "16.5%", "—", "—", "2025"]);
    assert.equal(parseSectorRow({ ticker: "X" }), null);
  });
});
