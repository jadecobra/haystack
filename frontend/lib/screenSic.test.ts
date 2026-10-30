import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseSicQuery, sicForTicker, sicIndustryName } from "./screenSic.ts";

describe("screen SIC filter", () => {
  it("maps AAPL to Electronic Computers", () => {
    assert.equal(sicForTicker("AAPL"), 3571);
    assert.equal(sicForTicker("aapl"), 3571);
    assert.equal(sicIndustryName(3571), "Electronic Computers");
  });
  it("parses a SIC query and ignores other values", () => {
    assert.equal(parseSicQuery("3571"), 3571);
    assert.equal(parseSicQuery("sic"), null);
    assert.equal(parseSicQuery(""), null);
    assert.equal(parseSicQuery(null), null);
  });
  it("has no SIC for a ticker outside the snapshot", () => {
    assert.equal(sicForTicker("ZZZZQ"), null);
  });
});
