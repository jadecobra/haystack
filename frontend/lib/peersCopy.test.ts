import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { peersHeading, peersMore, type PeersBlock } from "./peersCopy.ts";

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
