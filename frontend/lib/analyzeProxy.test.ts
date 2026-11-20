import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  fetchAnalyzeWithRetry,
  MAX_UPSTREAM_ATTEMPTS,
  UPSTREAM_TIMEOUT_MS,
} from "./analyzeProxy.ts";
import {
  ANALYZE_TIMEOUT_MS,
  shouldRetryAnalyzeStatus,
} from "../app/utils/analyze-error.ts";

function hangingFetch(calls: number[]) {
  return (_url: string | URL | Request, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      calls.push(calls.length + 1);
      init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("The operation was aborted.", "AbortError"));
      });
    });
}

describe("fetchAnalyzeWithRetry (#127)", () => {
  it("retries once when the first upstream request times out, then succeeds", async () => {
    let attempts = 0;
    const fetchFn: typeof fetch = (_url, init) => {
      attempts += 1;
      if (attempts === 1) {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        });
      }
      return Promise.resolve(
        new Response(JSON.stringify({ ticker: "AAPL" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    };

    const result = await fetchAnalyzeWithRetry("http://example.invalid/analyze/AAPL", {
      fetchFn,
      timeoutMs: 25,
      maxAttempts: MAX_UPSTREAM_ATTEMPTS,
    });

    assert.equal(attempts, 2);
    assert.equal(result.kind, "upstream");
    if (result.kind === "upstream") {
      assert.equal(result.status, 200);
      assert.equal(result.body, '{"ticker":"AAPL"}');
    }
  });

  it("returns timeout after two upstream timeouts in a row", async () => {
    const calls: number[] = [];
    const result = await fetchAnalyzeWithRetry("http://example.invalid/analyze/AAPL", {
      fetchFn: hangingFetch(calls),
      timeoutMs: 25,
      maxAttempts: MAX_UPSTREAM_ATTEMPTS,
    });

    assert.equal(calls.length, 2);
    assert.deepEqual(result, { kind: "timeout" });
  });

  it("does not retry on a non-timeout network error", async () => {
    let attempts = 0;
    const fetchFn: typeof fetch = () => {
      attempts += 1;
      return Promise.reject(new Error("connect ECONNREFUSED"));
    };

    const result = await fetchAnalyzeWithRetry("http://example.invalid/analyze/AAPL", {
      fetchFn,
      timeoutMs: 25,
    });

    assert.equal(attempts, 1);
    assert.deepEqual(result, {
      kind: "unreachable",
      detail: "connect ECONNREFUSED",
    });
  });

  it("does not retry when upstream answers with an HTTP error status", async () => {
    let attempts = 0;
    const fetchFn: typeof fetch = () => {
      attempts += 1;
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "not found" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
      );
    };

    const result = await fetchAnalyzeWithRetry("http://example.invalid/analyze/AAPL", {
      fetchFn,
      timeoutMs: 25,
    });

    assert.equal(attempts, 1);
    assert.equal(result.kind, "upstream");
    if (result.kind === "upstream") {
      assert.equal(result.status, 404);
    }
  });
});

describe("client timeout and retry coordination (#127)", () => {
  it("gives the route enough time for two upstream attempts", () => {
    assert.ok(
      ANALYZE_TIMEOUT_MS > UPSTREAM_TIMEOUT_MS * MAX_UPSTREAM_ATTEMPTS,
      `Expected ANALYZE_TIMEOUT_MS (${ANALYZE_TIMEOUT_MS}) > ${UPSTREAM_TIMEOUT_MS * MAX_UPSTREAM_ATTEMPTS}`,
    );
  });

  it("does not retry a 504 timeout returned by the analyze route", () => {
    assert.equal(shouldRetryAnalyzeStatus(504), false);
    assert.equal(shouldRetryAnalyzeStatus(502), true);
    assert.equal(shouldRetryAnalyzeStatus(503), true);
    assert.equal(shouldRetryAnalyzeStatus(404), false);
  });
});
