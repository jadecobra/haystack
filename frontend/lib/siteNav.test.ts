import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { docsNavLink, oeComparisonLinks } from "./sectorTable.ts";

const shell = readFileSync(new URL("../app/components/page-shell.tsx", import.meta.url), "utf8");

describe("site nav (#65)", () => {
  it("lists /docs plus the 12 OE Comparison hrefs", () => {
    assert.deepEqual(docsNavLink(), {
      label: "How metrics are calculated",
      href: "/docs",
    });
    assert.deepEqual(
      oeComparisonLinks().map((link) => link.href),
      [
        "/screen",
        "/sector/communication-services",
        "/sector/consumer-discretionary",
        "/sector/consumer-staples",
        "/sector/energy",
        "/sector/financials",
        "/sector/health-care",
        "/sector/industrials",
        "/sector/information-technology",
        "/sector/materials",
        "/sector/real-estate",
        "/sector/utilities",
      ],
    );
    assert.deepEqual(
      oeComparisonLinks().map((link) => link.label),
      [
        "S&P 500",
        "Communication Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Financials",
        "Health Care",
        "Industrials",
        "Information Technology",
        "Materials",
        "Real Estate",
        "Utilities",
      ],
    );
  });

  it("renders those hrefs inside site-nav in PageShell", () => {
    assert.match(shell, /data-testid="site-nav"/);
    assert.match(shell, /aria-label="Site navigation"/);
    assert.match(shell, /docsNavLink\(\)/);
    assert.match(shell, /oeComparisonLinks\(\)/);
    assert.match(shell, /href=\{docsNavLink\(\)\.href\}/);
    assert.match(shell, /href=\{link\.href\}/);
    assert.doesNotMatch(shell, / · /);
    assert.match(shell, /<p key=\{link\.href\}>/);
  });

  it("adds one Pumping Python maker line and no agbalumo link", () => {
    assert.match(shell, /from the same maker/);
    assert.match(shell, /data-testid="maker-line"/);
    assert.match(shell, /data-testid="maker-link"/);
    assert.match(shell, /how do i know my code works\?/);
    assert.match(shell, /https:\/\/www\.pumpingpython\.com\/\?ref=longmuch/);
    assert.doesNotMatch(shell, /agbalumo/i);
  });
});
