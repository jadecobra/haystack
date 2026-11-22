# Post-Filing Stock Split Adjustment (#139)

Date: 2026-11-21
Status: Accepted

## Context

SEC `companyfacts` JSON reflects filings submitted up to each fact's `filed` date, and multi-class issuers fall back to 10-K XBRL cover/weighted counts in `share_classes`. When an issuer executes a stock split after a statement year's share count was filed or restated (before a subsequent filing restates that year's shares), the market `previous_close` quote reflects the post-split price while the statement's `shares` and any reported `dividends_per_share` remain on the pre-split basis. This mismatches per-share and yield-on-price metrics against `previous_close`. Using a single payload-wide `latest_filed` across all `us-gaap` facts would let a later non-restating 10-Q suppress an un-restated post-10-K split, and dotted tickers like `BRK.B` require hyphenated symbols on Yahoo while Yahoo `query1` can fail transiently. Once a later SEC filing arrives with restated counts, the basis-jump logic in `split_adjusted_shares` (`backend/app/edgar.py`) already brings historical years onto the post-split basis.

## Decision

Fetch recent split events in `backend/app/quote.py` via `_fetch_splits` using a three-source fallback chain: Yahoo chart on `query1.finance.yahoo.com`, then Yahoo chart on `query2.finance.yahoo.com` (`range=2y`, `interval=3mo`, `events=splits`, normalizing dotted tickers such as `BRK.B` to `BRK-B` via `_yahoo_symbol` while keeping `{symbol}.splits.json` cache keys), then CNBC's quote endpoint (`EventData.split_ex_date` and `EventData.split_factor`, computing `ratio = 1.0 / factor` and filtering out announced future splits beyond `today + 3 days`). `recent_splits` caches the first non-`None` result on disk in `{symbol}.splits.json` with a 24-hour TTL (no memory cache or request coalescing), falling back to stale disk cache or `[]` when all sources fail.

In `backend/app/edgar.py` and `backend/app/share_classes.py`, record a per-year `shares_basis_date` on each statement row: for `companyfacts` shares, `split_adjusted_shares` sets it from the share count's own filing date or the upper bound `j.hi` of any applied basis jump (or the continuation tag's max annual instant filing date); for multi-class overrides in `share_classes.apply`, set it from the 10-K's `cover_date` (falling back to `period_end`). In `statements_for_ticker`, after `share_classes.apply` and the empty-years check, call `apply_market_splits(statements, quote.recent_splits(ticker), basis=latest_filed(payload))`. Per row, `apply_market_splits` resolves `row_basis = row.get("shares_basis_date") or basis`, applies splits with `ex_date > row_basis`, multiplies non-null `shares` by the combined `factor`, and divides non-null `dividends_per_share` by `factor`, leaving dollar totals and `AnalysisResponse` untouched.

## Consequences

- **Resilient split discovery across tickers and endpoints**: Fallback to Yahoo `query2` and CNBC `EventData` protects against transient `query1` errors, and `_yahoo_symbol` keeps dotted tickers working on Yahoo without splitting disk cache keys.
- **Non-restating 10-Qs no longer mask post-10-K splits**: Per-year `shares_basis_date` anchors each year to when its own share count was last filed or restated (or its `share_classes` 10-K cover date), while still avoiding double adjustment when a 10-Q genuinely restates prior shares.
- **One extra split request per ticker per day on cold cache**: Analyzing an uncached ticker adds one split fetch per 24-hour disk cache window (`{symbol}.splits.json`), separate from the quote cache (`{symbol}.json`).
- **Fail-soft fallback to SEC-only behavior**: If all three split sources fail and no stale `{symbol}.splits.json` exists on disk, `recent_splits` returns `[]` and never raises, degrading cleanly to pre-change SEC-only behavior.
