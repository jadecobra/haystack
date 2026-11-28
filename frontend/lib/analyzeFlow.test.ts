import assert from "node:assert/strict";
import { describe, it } from "node:test";
import fc from "fast-check";
import {
  MAX_ANALYZE_RETRIES,
  createInitialAnalyzeFlowState,
  reduceAnalyzeFlow,
  type AnalyzeFlowEvent,
  type AnalyzePayload,
} from "./analyzeFlow.ts";

type TestGroup = { id: string; title: string; labels: string[] };
type TestEvent = AnalyzeFlowEvent<AnalyzePayload, TestGroup>;

const tickerArb = fc.constantFrom("AAPL", "MSFT", "GOOG", "NVDA");
const startedAtArb = fc.integer({ min: 1, max: 5 });
const requestIdArb = fc.integer({ min: 0, max: 12 });
const messageArb = fc.constantFrom(
  "Timed out",
  "Upstream 503",
  "Ticker not found",
  "Backend returned no metric table",
);

const groupArb: fc.Arbitrary<TestGroup> = fc.record({
  id: fc.constantFrom("income", "cashflow"),
  title: fc.constantFrom("Income", "Cash Flow"),
  labels: fc.array(fc.constantFrom("Revenue", "Owner Earnings"), {
    minLength: 1,
    maxLength: 2,
  }),
});

const payloadArb: fc.Arbitrary<AnalyzePayload> = fc.record({
  ticker: tickerArb,
  rows: fc.array(fc.record({ metric: fc.constant("Revenue") }), {
    minLength: 0,
    maxLength: 3,
  }),
  years: fc.array(fc.constantFrom("2023", "2024", "2025"), {
    minLength: 0,
    maxLength: 3,
  }),
});

const replyEventArb: fc.Arbitrary<
  Extract<
    TestEvent,
    { type: "reply_ok" | "reply_transient" | "reply_product_error" | "timeout" }
  >
> = fc.oneof(
  fc.record({
    type: fc.constant("reply_ok" as const),
    requestId: requestIdArb,
    data: payloadArb,
    fallbackMessage: fc.option(messageArb, { nil: undefined }),
  }),
  fc.record({
    type: fc.constant("reply_transient" as const),
    requestId: requestIdArb,
    message: messageArb,
  }),
  fc.record({
    type: fc.constant("reply_product_error" as const),
    requestId: requestIdArb,
    message: messageArb,
  }),
  fc.record({
    type: fc.constant("timeout" as const),
    requestId: requestIdArb,
    message: messageArb,
  }),
);

const eventArb: fc.Arbitrary<TestEvent> = fc.oneof(
  fc.record({
    type: fc.constant("start" as const),
    ticker: tickerArb,
    startedAt: startedAtArb,
    skeleton: fc.record({
      groups: fc.array(groupArb, { minLength: 0, maxLength: 2 }),
      years: fc.array(fc.constantFrom("2023", "2024", "…"), {
        minLength: 1,
        maxLength: 5,
      }),
    }),
  }),
  fc.record({
    type: fc.constant("contract_groups" as const),
    startedAt: startedAtArb,
    groups: fc.array(groupArb, { minLength: 0, maxLength: 2 }),
  }),
  replyEventArb,
);

const eventListArb = fc.array(eventArb, { minLength: 0, maxLength: 30 });

describe("analyzeFlow state machine", () => {
  it("ignores any reply whose requestId does not match the active request", () => {
    fc.assert(
      fc.property(eventListArb, replyEventArb, (events, reply) => {
        const state = events.reduce(
          reduceAnalyzeFlow<AnalyzePayload, TestGroup>,
          createInitialAnalyzeFlowState<AnalyzePayload, TestGroup>(),
        );
        fc.pre(reply.requestId !== state.requestId);
        const next = reduceAnalyzeFlow(state, reply);
        assert.strictEqual(next, state);
      }),
      { numRuns: 1000 },
    );
  });

  it("retries each request at most once before transitioning to error", () => {
    fc.assert(
      fc.property(eventListArb, messageArb, fc.boolean(), (events, message, isTimeout) => {
        let state = createInitialAnalyzeFlowState<AnalyzePayload, TestGroup>();
        for (const event of events) {
          const prev = state;
          state = reduceAnalyzeFlow(state, event);
          assert.ok(state.retries <= MAX_ANALYZE_RETRIES);
          if (
            prev.view.kind === "waiting" &&
            prev.retries === MAX_ANALYZE_RETRIES &&
            (event.type === "reply_transient" || event.type === "timeout") &&
            event.requestId === prev.requestId
          ) {
            assert.equal(state.view.kind, "error");
          }
        }
        if (state.view.kind === "waiting" && state.retries === MAX_ANALYZE_RETRIES) {
          const next = reduceAnalyzeFlow(state, {
            type: isTimeout ? "timeout" : "reply_transient",
            requestId: state.requestId,
            message,
          });
          assert.equal(next.view.kind, "error");
        }
      }),
      { numRuns: 1000 },
    );
  });

  it("terminates each request in ready or error after at most MAX_ANALYZE_RETRIES + 1 active replies", () => {
    fc.assert(
      fc.property(
        eventListArb,
        fc.array(replyEventArb, {
          minLength: MAX_ANALYZE_RETRIES + 1,
          maxLength: 8,
        }),
        (prefix, replies) => {
          let state = prefix.reduce(
            reduceAnalyzeFlow<AnalyzePayload, TestGroup>,
            createInitialAnalyzeFlowState<AnalyzePayload, TestGroup>(),
          );
          state = reduceAnalyzeFlow(state, {
            type: "start",
            ticker: "AAPL",
            startedAt: 1,
            skeleton: { groups: [], years: ["…"] },
          });

          const activeId = state.requestId;
          let activeReplies = 0;
          for (const reply of replies) {
            state = reduceAnalyzeFlow(state, { ...reply, requestId: activeId });
            activeReplies += 1;
            if (activeReplies >= MAX_ANALYZE_RETRIES + 1) {
              assert.ok(
                state.view.kind === "ready" || state.view.kind === "error",
                `expected terminal view after ${activeReplies} active replies, got ${state.view.kind}`,
              );
            }
          }
        },
      ),
      { numRuns: 1000 },
    );
  });

  it("never enters ready with empty rows or empty years", () => {
    fc.assert(
      fc.property(eventListArb, (events) => {
        let state = createInitialAnalyzeFlowState<AnalyzePayload, TestGroup>();
        for (const event of events) {
          state = reduceAnalyzeFlow(state, event);
          if (state.view.kind === "ready") {
            assert.ok(state.view.data.rows.length > 0);
            assert.ok(state.view.data.years.length > 0);
          }
        }
      }),
      { numRuns: 1000 },
    );
  });
});
