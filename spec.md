## LongMuch product spec

Reference for what the running product does. The locked table is `LOCKED_LABELS` and `SCHEMA_VERSION` in `backend/app/metrics.py` (`GET /contract`). This file explains owner earnings and the intended rows. If this file and `/contract` disagree, `/contract` wins.

### 1. Goal

Users type a ticker and see five years of ratios and per-share metrics derived from SEC 10-K annual facts.

### 2. Behavior

**Input.** One ticker field and Analyze (or Enter). Invalid tickers return HTTP 400.

**Sources.**

- SEC companyfacts JSON (US-GAAP FY series tied to 10-K), last five years. Not a per-filing XBRL instance parse.
- FRED series DGS30 (30-year Treasury).
- Previous close from Yahoo, then NASDAQ. The same last close is used for every year column in rows that divide by Last Close Price.

**Owner earnings.** Cash after maintenance reinvestment, before allocation. Internal field name is `owner_earnings`.

```
OE = OCF − min(|capex|, D&A)
```

OCF is the reported operating-cash tag when present. If missing: `ΔCash − CFI − CFF − FX` (FX = 0 if absent). If still missing: `NI + D&A − ΔNWC` using AR / inventory / AP pairs that exist in both the year and the prior year. Do not use NI + D&A with no working-capital pair. Capex is PPE (or the combined PPE+intangibles tag if present), plus capitalized software, without double-counting ProductiveAssets on top of PPE. If OCF cannot be resolved, or both capex and D&A are missing, owner earnings is null.

**Table rows.** Exact strings from `LOCKED_LABELS` (CI fails if this list diverges):

- Net Income / Revenue
- Net Income / Equity
- Net Income / Assets
- Net Income / Total Liabilities
- Net Income / Debt
- Owner Earnings / Revenue
- Owner Earnings / Equity
- Owner Earnings / Assets
- Owner Earnings / Total Liabilities
- Owner Earnings / Debt
- Owner Earnings / Last Close Price
- Cash per Share / Last Close Price
- Revenue per Share / Last Close Price
- Dividends per Share / Last Close Price
- Net Income per Share / Last Close Price
- Assets per Share / Last Close Price
- Equity per Share / Last Close Price
- Dividends / Net Income
- Dividends / Owner Earnings
- Dividends / Equity
- Shares Outstanding
- Debt per Share
- Revenue per Share
- Net Income per Share
- Owner Earnings per Share
- Dividends per Share
- Equity per Share
- Assets per Share
- Cash per Share
- Liabilities per Share
- Owner Earnings / 30 Year Treasury per Share
- 30 Year Treasury (DGS30)

**UI.** Next.js App Router page: ticker, previous close when present, one metric×year table. No KPI cards. No charts.

### 3. Stack

- Backend: Python FastAPI (`GET /health`, `/analyze/{ticker}`, `/contract`).
- Frontend: Next.js; `GET /api/analyze/{ticker}` proxies to the API.
- Cache: process memory and `backend/.cache/` files. No Postgres, DynamoDB, or Redis.
- Deploy: Next.js on Vercel; API on Render (`render.yaml`). GitHub Actions on `main`.

### 4. Tests

Unit and integration tests cover parsing, owner earnings, metric rows, and API status codes. Schema bumps change `SCHEMA_VERSION` and verify-haystack contract recipes together.
