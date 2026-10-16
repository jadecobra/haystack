import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { sortPeerRows, type SectorRow } from "./sectorTable.ts";
import { sectorCells } from "./sectorTable.ts";

function row(
  ticker: string,
  oe: number | null,
  margin: number | null,
  extra: Partial<SectorRow> = {},
): SectorRow {
  return {
    ticker,
    name: `${ticker} Inc`,
    oe_yield: oe,
    payback_years: null,
    ni_margin: margin,
    debt_to_equity: null,
    no_debt: null,
    debt_state: "unknown",
    fy: 2025,
    sector: null,
    sub_industry: null,
    years: null,
    ...extra,
  };
}

describe("sortPeerRows (#58)", () => {
  const rows = [
    row("MID", 0.04, 0.5),
    row("DASH", 0.9, 0.9, { missing: "not in screen snapshot or peer metrics", fy: null }),
    row("LOW", 0.01, null),
    row("HIGH", 0.2, 0.1),
    row("BLANK", null, 0.8),
    row("ZZ", 0.01, 0.2, { missing: "missing" }),
  ];

  it("defaults to OE yield descending, nulls after numbers, dash rows last", () => {
    assert.deepEqual(
      sortPeerRows(rows).map((r) => r.ticker),
      ["HIGH", "MID", "LOW", "BLANK", "DASH", "ZZ"],
    );
  });

  it("sorts NI margin descending and returns to OE yield", () => {
    const byMargin = sortPeerRows(rows, "ni_margin").map((r) => r.ticker);
    assert.deepEqual(byMargin, ["BLANK", "MID", "HIGH", "LOW", "DASH", "ZZ"]);
    assert.deepEqual(
      sortPeerRows(rows, "oe_yield").map((r) => r.ticker),
      ["HIGH", "MID", "LOW", "BLANK", "DASH", "ZZ"],
    );
  });

  it("labels the OE yield cell with the year count", () => {
    assert.equal(sectorCells(row("A", 0.04, 0.1, { years: 3 }))[1], "4.0% 3y");
    assert.equal(sectorCells(row("B", 0.04, 0.1, { years: 5 }))[1], "4.0% 5y");
    assert.equal(sectorCells(row("C", null, null, { years: 2 }))[1], "— 2y");
    assert.equal(sectorCells(row("D", 0.04, 0.1))[1], "4.0%");
  });
});
