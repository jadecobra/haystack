import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  GA_MEASUREMENT_ID,
  gtagScriptSrc,
  pageViewArgs,
  shouldLoadGa4,
  vercelAppRedirect,
} from "./ga4.ts";

describe("GA4 hostname gate (#63)", () => {
  it("loads only on longmuch.com", () => {
    assert.equal(shouldLoadGa4("longmuch.com"), true);
    assert.equal(shouldLoadGa4("localhost"), false);
    assert.equal(shouldLoadGa4("127.0.0.1"), false);
    assert.equal(shouldLoadGa4("longmuch.vercel.app"), false);
    assert.equal(shouldLoadGa4("www.longmuch.com"), false);
    assert.equal(shouldLoadGa4("preview.vercel.app"), false);
  });

  it("points gtag.js at G-RBK1ZGN2HX", () => {
    assert.equal(GA_MEASUREMENT_ID, "G-RBK1ZGN2HX");
    assert.equal(
      gtagScriptSrc(),
      "https://www.googletagmanager.com/gtag/js?id=G-RBK1ZGN2HX",
    );
  });

  it("sends page_view with the next path on a client route change", () => {
    assert.deepEqual(pageViewArgs("/AAPL"), [
      "event",
      "page_view",
      { page_path: "/AAPL", send_to: "G-RBK1ZGN2HX" },
    ]);
    assert.deepEqual(pageViewArgs("/screen"), [
      "event",
      "page_view",
      { page_path: "/screen", send_to: "G-RBK1ZGN2HX" },
    ]);
  });
});

describe("longmuch.vercel.app redirect (#63)", () => {
  it("308s every path on that host to https://longmuch.com", () => {
    const rule = vercelAppRedirect();
    assert.equal(rule.permanent, true);
    assert.equal(rule.source, "/:path*");
    assert.deepEqual(rule.has, [{ type: "host", value: "longmuch.vercel.app" }]);
    assert.equal(rule.destination, "https://longmuch.com/:path*");
  });
});
