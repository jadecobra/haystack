# Sector comparison table (#43)

`/sector/{slug}` and the `/{TICKER}` section render from the daily screen snapshot (`/api/screen/sp500-oe-yield`, static JSON with a seed fallback; no new API). Rows are S&P 500 only, grouped by GICS from the S&P map, sorted by OE yield (blank-OE rows last, #52). Ticker-page tables cap at 40 and always keep the page's own row. Standalone `/sector/{slug}` pages are uncapped.

- **Columns:** Ticker, Name, OE yield, Payback (yrs), NI / equity, Debt / equity, FY. D/E folds in no-debt (#51): `0 (no debt)` only for debt_state zero, the ratio for positive debt, and `—` with a `title` tooltip for n/a (financials), unknown, or debt with equity <= 0 (`[data-testid="sector-de"]`).
- **Slug resolution:** a slug matches a sub-industry first, then a sector (`technology-hardware-storage-and-peripherals`, `information-technology`).
- **Ticker page:** the default group is the sub-industry. `[data-testid="sector-widen-link"]` widens to the sector, and `[data-testid="sector-page-link"]` opens the standalone page.
- **Clicks:** a row click (`[data-testid="sector-row-link"]`) goes to `/{TICKER}`.
- **Non-S&P tickers:** no table. The classification line is the SIC label with no link.
- **Coverage:** the screen run logs `column_coverage known/total ...`, and snapshot `meta.column_coverage` holds the same counts.

Proof: HTTP 200 for `/sector/{slug}`, at least one row, a click-through to `/{TICKER}`, and 0 console errors.
