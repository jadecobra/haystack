import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { peerRevenue, peersHeading, peersMore, peersReason, type PeersBlock } from "./peersCopy.ts";

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
      "Peers in the same SEC industry: Retail-Family Clothing Stores (SIC 5651), by latest annual revenue",
    );
  });
  it("explains the 3-digit widening", () => {
    assert.match(
      peersHeading({ ...sic, basis: "sic3", group: "SIC 565x", fallback: true }) ?? "",
      /same SEC industry group SIC 565x \(fewer than 3 others in Retail-Family Clothing Stores \(SIC 5651\)\)/,
    );
  });
  it("gives a reason when blank", () => {
    const blank = { ...sic, peers: [], total: 0, reason: "no other SEC filer in this SIC group reports annual revenue" };
    assert.equal(peersHeading(blank), "Peers (same SEC industry)");
    assert.equal(peersReason(blank), "No peers listed: no other SEC filer in this SIC group reports annual revenue.");
    assert.equal(peersReason(sic), null);
  });
  it("formats revenue", () => {
    assert.equal(peerRevenue({ ticker: "TJX", revenue: 56.36e9, revenue_fy: 2025 }), "$56.4B FY2025");
    assert.equal(peerRevenue({ ticker: "X", revenue: 12_300_000 }), "$12.3M");
    assert.equal(peerRevenue({ ticker: "ROST" }), null);
  });
});
