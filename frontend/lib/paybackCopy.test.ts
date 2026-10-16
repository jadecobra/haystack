import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { paybackSentence, type PaybackBlock } from "./paybackCopy.ts";

function block(overrides: Partial<PaybackBlock> = {}): PaybackBlock {
  return {
    price: 100,
    years_at_latest: 12.5,
    years_at_5y_avg: 14.2,
    treasury_years: 20.7,
    pays_back: true,
    ...overrides,
  };
}

describe("paybackSentence", () => {
  it("states latest, five-year average, and treasury years", () => {
    assert.equal(
      paybackSentence("AAPL", block()),
      "At $100.00 you get your money back in about 12.5 years from latest owner earnings (about 14.2 years on the 5y avg), vs ~20.7 years at the 30-year Treasury.",
    );
  });

  it("omits the five-year parenthetical when that average is missing", () => {
    assert.equal(
      paybackSentence("AAPL", block({ years_at_5y_avg: null })),
      "At $100.00 you get your money back in about 12.5 years from latest owner earnings, vs ~20.7 years at the 30-year Treasury.",
    );
  });

  it("omits the treasury clause when treasury years are missing", () => {
    assert.equal(
      paybackSentence("AAPL", block({ treasury_years: null })),
      "At $100.00 you get your money back in about 12.5 years from latest owner earnings (about 14.2 years on the 5y avg).",
    );
  });

  it("labels a shorter average with its year count", () => {
    assert.equal(
      paybackSentence("LULU", block({ years_at_5y_avg: 18.4, oe_avg_years: 3, treasury_years: null })),
      "At $100.00 you get your money back in about 12.5 years from latest owner earnings (about 18.4 years on the 3y avg).",
    );
  });

  it("says the ticker does not pay back when current owner earnings are not positive", () => {
    assert.equal(
      paybackSentence("XYZ", block({ pays_back: false, years_at_latest: null })),
      "At $100.00, XYZ doesn't pay back on current earnings.",
    );
  });

  it("returns null when payback is absent or latest years are unknown", () => {
    assert.equal(paybackSentence("AAPL", null), null);
    assert.equal(paybackSentence("AAPL", undefined), null);
    assert.equal(paybackSentence("AAPL", block({ years_at_latest: null })), null);
  });
});
