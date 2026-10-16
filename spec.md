## LongMuch product spec

Reference for what the running product does. The locked table is `LOCKED_LABELS` and `SCHEMA_VERSION` in `backend/app/metrics.py` (`GET /contract`). This file explains owner earnings and the intended rows. If this file and `/contract` disagree, `/contract` wins.

### 1. Goal

Users type a ticker and see available annual years of ratios and per-share metrics derived from SEC 10-K facts.

### 2. Behavior

**Input.** One ticker field and Analyze (or Enter). Invalid tickers return HTTP 400.

**Sources.**

- SEC companyfacts JSON (US-GAAP FY series tied to 10-K), every mapped annual year (newest-first). Not a per-filing XBRL instance parse.
- **Fiscal-year labels** come from each 10-K's own period end, not the filer's `fy` (DocumentFiscalYearFocus), which filers sometimes tag wrong (STX fy=2027 for the year ended 2025-06-27; FRT fy=2024 for 2025-12-31). Label = calendar year of the period end. 52/53-week convention: a year ending in the first 7 days of January (e.g. 2026-01-03) is the prior year's FY. Early ends in other months keep the end year (STX 2026-07-03 → FY2026, AAPL 2025-09-27 → FY2025). Retailers whose year ends in late January or early February show the end year (HD year ended 2026-02-01 → FY2026), even where the company calls it "fiscal 2025".
- **Transition periods (10-KT).** After a fiscal year-end change, a 10-KT covers the short stub between the old and new year-ends (FERG: 2025-08-01 → 2025-12-31). A stub is never shown as a fiscal year. Any 10-KT fact that ends after the filing's latest full-year (300–380 day) period is dropped from annual selection. The 10-KT's full-year comparatives are kept and labelled by their own period end. The first full year on the new year-end is its own FY when its 10-K arrives. ADM 2012, GPN 2016, LHX 2019 and MOS 2013 follow the same rule.
- **Predecessor filings (8-K12B successors).** Predecessor facts merge in filing by filing (deduped on accession + period), so a predecessor 10-K keeps its own current year even when the successor repeats that period as a comparative.
- **Multi-class issuers (#53).** SEC companyfacts omits dimensional (per-class) XBRL facts, so issuers that tag share counts only per class of stock have no share count there. For issuers in `backend/data/share_classes.json` (BRK.B, V, BKR, ERIE, STZ), per-class counts are read from each 10-K's own XBRL instance (EDGAR submissions → accession → instance) by `longmuch share-classes-refresh` into `backend/data/share_class_counts.json` (accession provenance; refreshed by the nightly screen job; never fetched at request time). Shares are traded-class equivalents. The first choice is the traded class's diluted weighted-average count. Other classes are added at their per-class basic count (else their cover count) × ratio, unless the filer's diluted count is already as-converted (`true`, or `auto`: true when diluted ≥ basic traded + converted others, so not in anti-dilutive loss years). With no diluted count, use the dei cover-page counts per class × ratio. Every ratio cites the filing. A class without a ratio leaves the year blank with the reason. These counts only fill years companyfacts left blank.
- FRED series DGS30 (30-year Treasury).
- Previous close from Yahoo, then NASDAQ. The same last close is used for every year column in rows that divide by Last Close Price.

**Owner earnings.** Cash after maintenance reinvestment, before allocation. Internal field name is `owner_earnings`.

```
OE = OCF − min(|capex|, D&A)
```

OCF is the reported operating-cash tag when present. If missing: `ΔCash − CFI − CFF − FX` (FX = 0 if absent). If still missing: `NI + D&A − ΔNWC` using AR / inventory / AP pairs that exist in both the year and the prior year. Do not use NI + D&A with no working-capital pair. Capex is PPE (or the combined PPE+intangibles tag if present), plus capitalized software, without double-counting ProductiveAssets on top of PPE. If OCF cannot be resolved, or both capex and D&A are missing, owner earnings is null.

**Table rows.** Exact strings from `LOCKED_LABELS` (CI fails if this list diverges). Groups from `LOCKED_GROUPS` / `GET /contract` `groups`:

- Owner Earnings / Last Close Price
- Cash per Share / Last Close Price
- Dividends per Share / Last Close Price
- Net Income per Share / Last Close Price
- Equity per Share / Last Close Price
- Assets per Share / Last Close Price
- Revenue per Share / Last Close Price
- Net Income / Equity
- Net Income / Assets
- Net Income / Revenue
- Net Income / Total Liabilities
- Net Income / Debt
- Owner Earnings / Equity
- Owner Earnings / Assets
- Owner Earnings / Revenue
- Owner Earnings / Total Liabilities
- Owner Earnings / Debt
- Dividends / Equity
- Dividends / Owner Earnings
- Dividends / Net Income
- Owner Earnings per Share
- Cash per Share
- Dividends per Share
- Net Income per Share
- Equity per Share
- Assets per Share
- Revenue per Share
- Liabilities per Share
- Debt per Share
- Shares Outstanding
- 30 Year Treasury (DGS30)
- Owner Earnings / 30 Year Treasury per Share

**UI.** Next.js App Router page: ticker, previous close when present, one metric×year table with six group header rows from the API `groups` field. No KPI cards. No charts.

**S&P 500 screen snapshot.** Every ticker in the S&P map gets a row when SEC has annual 10-K facts and a previous close exists. OE yield, NI margin, and payback are stored as the up-to-five-year average and also as the latest fiscal year. The tables show the conservative pair: the lower yield, the lower margin, and the longer payback (a non-positive latest owner earnings per share blanks payback), labeled `latest` or `Ny avg`. The average fields stay on the row. When owner earnings per share can't be computed, the row stays with a blank OE yield, OE/share and payback, and `oe_note` gives the reason: no operating cash flow with capex or D&A (common for banks and insurers), no undimensioned share count (multi-class issuers), or a scale error (|yield| > 100%). NI/equity and debt/equity still fill. Blank-OE rows rank last. Tickers without facts or price go to `excluded[]` with a reason. `count` is rows, `ranked` is rows with an OE yield, and `skipped` is `len(excluded)`.

**Peers (#54, #55).** Every ticker, S&P 500 included, lists peers from all SEC filers with the same 4-digit SIC code (from EDGAR submissions), ranked by latest annual revenue (SEC XBRL frames), top 10. Candidates need latest annual revenue of at least $10M; filers below it or with no revenue are dropped. When fewer than 5 same-SIC peers clear the floor, the list widens to the 3-digit SIC group, ranked by revenue. With no candidates, the section is blank and gives the reason. Peers come from the committed `backend/data/sic_peers.json`, refreshed monthly by `sic-peers.yml` (PR only on change, no auto-merge); pages never fetch SEC for peers. GICS sector/sub-industry labels and the /sector tables are separate and unchanged.

### 3. Stack

- Backend: Python FastAPI (`GET /health`, `/analyze/{ticker}`, `/contract`).
- Frontend: Next.js; `GET /api/analyze/{ticker}` proxies to the API.
- Cache: process memory and `backend/.cache/` files. No Postgres, DynamoDB, or Redis.
- Deploy: Next.js on Vercel; API on Render (`render.yaml`). GitHub Actions on `main`.

### 4. Tests

Unit and integration tests cover parsing, owner earnings, metric rows, and API status codes. Schema bumps change `SCHEMA_VERSION` and verify-haystack contract recipes together.
