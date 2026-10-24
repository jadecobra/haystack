import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dropReason, listUnranked, shortReason, universeBalances } from "./unranked.ts";

const snapshot = JSON.parse(
  readFileSync(new URL("../public/screen/sp500-oe-yield.json", import.meta.url), "utf8"),
) as {
  ranked: number;
  rows: unknown[];
  excluded: unknown[];
};

describe("shortReason", () => {
  it("keeps the clause after the owner-earnings prefix", () => {
    assert.equal(
      shortReason(
        "no owner earnings: no operating cash flow with capex or D&A in the latest 10-K year",
      ),
      "no operating cash flow with capex or D&A in the latest 10-K year",
    );
  });

  it("collapses the long SEC-facts reason", () => {
    assert.equal(
      shortReason("no SEC annual us-gaap facts (new registrant): companyfacts missing"),
      "no SEC annual facts",
    );
  });
});

describe("listUnranked", () => {
  it("lists excluded names, blank yields, and rows the table drops", () => {
    const names = listUnranked({
      ranked: 1,
      excluded: [{ ticker: "hona", reason: "no SEC annual us-gaap facts: missing" }],
      rows: [
        { ticker: "AAPL", name: "Apple", oe_yield: 0.04, price: 100, fy: 2025 },
        {
          ticker: "JPM",
          name: "JPMorgan",
          oe_yield: null,
          oe_note: "no owner earnings: no operating cash flow with capex or D&A",
          price: 10,
          fy: 2024,
        },
        { ticker: "NOP", name: "No Price Co", oe_yield: 0.1, fy: 2024 },
        { ticker: "NOY", name: "No Year Co", oe_yield: 0.1, price: 3 },
      ],
    });
    assert.deepEqual(
      names.map((item) => [item.ticker, item.reason]),
      [
        ["HONA", "no SEC annual facts"],
        ["JPM", "no operating cash flow with capex or D&A"],
        ["NOP", "no price"],
        ["NOY", "no fiscal year"],
      ],
    );
    assert.equal(names[1].name, "JPMorgan");
    assert.equal(dropReason({ ticker: "X", price: 1 }), "no fiscal year");
  });

  it("matches the shipped snapshot: 493 ranked + 10 = 501 rows + 2 excluded", () => {
    const names = listUnranked(snapshot);
    assert.equal(names.length, 10);
    assert.deepEqual(
      names.map((item) => item.ticker),
      ["HONA", "VYLR", "CB", "EG", "IBKR", "JPM", "KKR", "RF", "SKYD", "USB"],
    );
    assert.ok(names.every((item) => item.reason.length > 0 && item.reason.length < 120));
    assert.equal(universeBalances(snapshot), true);
    assert.equal(snapshot.ranked + names.length, snapshot.rows.length + snapshot.excluded.length);
  });
});
