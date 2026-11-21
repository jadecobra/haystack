# Post-Filing Stock Split Adjustment (#139)

Date: 2026-11-21
Status: Accepted

## Context

SEC `companyfacts` JSON reflects filings submitted up to the latest `filed` date in the payload. When an issuer executes a stock split after its latest SEC filing (before a subsequent 10-Q or 10-K is filed), the market `previous_close` quote reflects the post-split price while `companyfacts` share counts and any reported `dividends_per_share` remain on the pre-split basis. This mismatches per-share and yield-on-price metrics against `previous_close`. Once a later SEC filing arrives with restated counts, the basis-jump logic in `split_adjusted_shares` (`backend/app/edgar.py`) already brings historical years onto the post-split basis.

## Decision

Fetch recent split events for the ticker from Yahoo Finance's chart endpoint (`https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` with `range=2y`, `interval=3mo`, `events=splits`) via `recent_splits` in `backend/app/quote.py`, cached on disk in `{symbol}.splits.json` with a 24-hour TTL (no memory cache or request coalescing). Parse each event as `Split(ex_date, ratio)` where `ratio = numerator / denominator`, skipping malformed or non-positive entries.

In `backend/app/edgar.py`, compute `latest_filed(payload)` as the maximum `filed` date across all `us-gaap` facts after merging predecessor facts. In `statements_for_ticker`, after `share_classes.apply` and the empty-years check, call `apply_market_splits(statements, quote.recent_splits(ticker), basis=latest_filed(payload))`. Only splits with `ex_date > basis` apply; their ratios multiply into a combined `factor` that scales non-null `shares` and divides non-null `dividends_per_share`, leaving dollar totals and `AnalysisResponse` untouched.

## Consequences

- **One extra Yahoo request per ticker per day**: Analyzing an uncached ticker adds one Yahoo chart request for split events per 24-hour disk cache window (`{symbol}.splits.json`), separate from the quote cache (`{symbol}.json`).
- **Fail-soft fallback to today's behavior**: If the Yahoo split fetch fails or returns invalid data, `recent_splits` falls back to any stale `{symbol}.splits.json` cache or `[]` and never raises, so requests degrade cleanly to pre-change SEC-only behavior.
- **Split missed when Yahoo is down and no cache exists**: If Yahoo is unreachable (or has not yet published the split) and no cached splits file exists on disk, a post-filing split will not be applied until a subsequent fetch succeeds or a new SEC filing restates the share count.
