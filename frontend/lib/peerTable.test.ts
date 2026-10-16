import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parsePeerRow } from "./peersCopy.ts";
import { sectorCells } from "./sectorTable.ts";

describe("peer table rows (#56)", () => {
  it("keeps dash rows and renders metric cells as dashes", () => {
    const row = parsePeerRow({
      ticker: "zzZz",
      name: "Missing Co",
      oe_yield: null,
      payback_years: null,
      ni_margin: null,
      debt_to_equity: null,
      no_debt: null,
      debt_state: "unknown",
      fy: null,
      current: false,
      missing: "not in screen snapshot or peer metrics",
    });
    assert.ok(row);
    assert.equal(row.ticker, "ZZZZ");
    assert.equal(row.name, "Missing Co");
    assert.equal(row.fy, null);
    assert.equal(row.missing, "not in screen snapshot or peer metrics");
    assert.equal(row.current, false);
    assert.deepEqual(sectorCells(row), ["Missing Co", "—", "—", "—", "—", "—"]);
  });

  it("parses a full metrics row with current flag", () => {
    const row = parsePeerRow({
      ticker: "aapl",
      name: "Apple Inc",
      oe_yield: 0.03,
      payback_years: 20.5,
      ni_margin: 1.5,
      debt_to_equity: 1.34,
      debt_state: "positive",
      fy: 2025,
      current: true,
    });
    assert.ok(row);
    assert.equal(row.current, true);
    assert.equal(row.fy, 2025);
    assert.deepEqual(sectorCells(row), ["Apple Inc", "3.0%", "20.5", "150.0%", "1.34", "2025"]);
  });

  it("rejects rows without a ticker", () => {
    assert.equal(parsePeerRow({ fy: 2025 }), null);
    assert.equal(parsePeerRow(null), null);
  });
});
