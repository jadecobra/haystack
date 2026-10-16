import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { priceCell, sectorCells, sortPeerRows, type SectorRow } from "./sectorTable.ts";

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
    assert.equal(sectorCells(row("A", 0.04, 0.1, { years: 3 }))[2], "4.0% 3y");
    assert.equal(sectorCells(row("B", 0.04, 0.1, { years: 5 }))[2], "4.0% 5y");
    assert.equal(sectorCells(row("C", null, null, { years: 2 }))[2], "— 2y");
    assert.equal(sectorCells(row("D", 0.04, 0.1))[2], "4.0%");
  });
});

describe("conservative cells and sort (#59)", () => {
  it("shows cons values with a basis suffix", () => {
    const cells = sectorCells(
      row("A", 0.2, 0.3, {
        years: 5,
        oe_yield_cons: 0.099,
        oe_yield_basis: "latest",
        payback_years: 8,
        payback_cons: 10.1,
        payback_basis: "latest",
        ni_margin_cons: 0.148,
        ni_margin_basis: "5y avg",
      }),
    );
    assert.equal(cells[1], "—");
    assert.equal(cells[2], "9.9% latest");
    assert.equal(cells[3], "10.1 latest");
    assert.equal(cells[4], "14.8% 5y avg");
  });

  it("formats price with and without an as-of date", () => {
    const dated = priceCell(row("A", 0.04, 0.1, { price: 99.09, price_as_of: "2026-10-15" }));
    assert.equal(dated.text, "$99.09 Oct 15");
    assert.equal(dated.asOf, "Oct 15");
    const bare = priceCell(row("A", 0.04, 0.1, { price: 99.09 }));
    assert.equal(bare.text, "$99.09");
    assert.equal(bare.asOf, null);
    const missing = priceCell(row("A", null, null));
    assert.equal(missing.text, "—");
    assert.equal(missing.title, "no price in snapshot");
  });

  it("falls back to the old fields when cons keys are absent", () => {
    const cells = sectorCells(row("A", 0.04, 0.1, { years: 3, payback_years: 12.5 }));
    assert.equal(cells[2], "4.0% 3y");
    assert.equal(cells[3], "12.5");
    assert.equal(cells[4], "10.0%");
  });

  it("sorts on cons values and still parks dash rows last", () => {
    const rows = [
      row("AVG", 0.2, 0.2, { oe_yield_cons: 0.05, ni_margin_cons: 0.01 }),
      row("LATEST", 0.01, 0.01, { oe_yield_cons: 0.2, ni_margin_cons: 0.5 }),
      row("OLD", 0.1, 0.3),
      row("DASH", 0.9, 0.9, { missing: "not in screen snapshot or peer metrics", fy: null }),
    ];
    assert.deepEqual(
      sortPeerRows(rows).map((r) => r.ticker),
      ["LATEST", "OLD", "AVG", "DASH"],
    );
    assert.deepEqual(
      sortPeerRows(rows, "ni_margin").map((r) => r.ticker),
      ["LATEST", "OLD", "AVG", "DASH"],
    );
  });
});
