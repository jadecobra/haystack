import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { peerRevenue, peersHeading, peersMore, peersNote, peersReason, peersWiden, type PeersBlock } from "./peersCopy.ts";

const base: PeersBlock = {
  basis: "sub_industry",
  group: "Technology Hardware, Storage & Peripherals",
  sub_industry: "Technology Hardware, Storage & Peripherals",
  fallback: false,
  total: 2,
  peers: [{ ticker: "DELL" }, { ticker: "HPQ" }],
};

describe("peersHeading", () => {
  it("names the sub-industry", () => {
    assert.equal(
      peersHeading(base),
      "S&P 500 peers in Technology Hardware, Storage & Peripherals (GICS sub-industry)",
    );
  });
  it("explains the industry-group fallback", () => {
    assert.equal(
      peersHeading({ ...base, basis: "industry_group", group: "Energy", sub_industry: "Integrated Oil & Gas", fallback: true }),
      "S&P 500 peers in the Energy industry group (fewer than 3 others in Integrated Oil & Gas)",
    );
  });
  it("is null with no peers", () => {
    assert.equal(peersHeading(null), null);
    assert.equal(peersHeading({ ...base, peers: [], total: 0 }), null);
  });
  it("reports capped extras", () => {
    assert.equal(peersMore(base), null);
    assert.equal(peersMore({ ...base, total: 45 }), "+43 more");
  });
});

describe("SEC SIC peers (#54)", () => {
  const sic: PeersBlock = {
    basis: "sic",
    group: "Retail-Family Clothing Stores",
    sub_industry: "Retail-Family Clothing Stores",
    fallback: false,
    total: 2,
    sic: 5651,
    peers: [{ ticker: "TJX", revenue: 56.36e9, revenue_fy: 2025 }, { ticker: "ROST" }],
  };
  it("labels the same SEC industry", () => {
    assert.equal(
      peersHeading(sic),
      "Industry peers — all US filers (SIC 5651 Retail-Family Clothing Stores)",
    );
    assert.equal(
      peersNote(sic),
      "Top 2 of 2 US SEC filers in SIC 5651 with annual revenue of at least $10M, ranked by latest revenue and sorted by OE yield.",
    );
  });
  it("omits the SIC code when it is null", () => {
    assert.equal(
      peersHeading({ ...sic, sic: null }),
      "Industry peers — all US filers (Retail-Family Clothing Stores)",
    );
  });
  it("explains the 3-digit widening", () => {
    const wide = { ...sic, basis: "sic3" as const, group: "SIC 565x", fallback: true, total: 8 };
    assert.equal(
      peersHeading(wide),
      "Industry peers — all US filers (SIC 565xx, widened from SIC 5651 Retail-Family Clothing Stores)",
    );
    assert.equal(
      peersNote(wide),
      "Fewer than 5 peers in SIC 5651 cleared $10M revenue; widened to 2 of 8 US SEC filers in the 3-digit SIC 565 group, sorted by OE yield.",
    );
  });
  it("gives a reason when blank", () => {
    const blank = { ...sic, peers: [], total: 0, reason: "no other SEC filer in this SIC group reports annual revenue" };
    assert.equal(peersHeading(blank), "Industry peers — all US filers");
    assert.equal(peersNote(blank), null);
    assert.equal(peersReason(blank), "No peers listed: no other SEC filer in this SIC group reports annual revenue.");
    assert.equal(peersReason(sic), null);
  });
  it("links the industry to the filtered S&P screen", () => {
    assert.deepEqual(peersWiden(sic), {
      href: "/screen?sic=5651",
      label: "Widen to Retail-Family Clothing Stores",
    });
    const wide = { ...sic, basis: "sic3" as const, group: "SIC 565x", fallback: true };
    assert.deepEqual(peersWiden(wide), {
      href: "/screen?sic=5651",
      label: "Widen to Retail-Family Clothing Stores",
    });
    assert.equal(peersWiden(base), null);
    assert.equal(peersWiden({ ...sic, sic: null }), null);
  });
  it("formats revenue", () => {
    assert.equal(peerRevenue({ ticker: "TJX", revenue: 56.36e9, revenue_fy: 2025 }), "$56.4B FY2025");
    assert.equal(peerRevenue({ ticker: "X", revenue: 12_300_000 }), "$12.3M");
    assert.equal(peerRevenue({ ticker: "ROST" }), null);
  });
});
