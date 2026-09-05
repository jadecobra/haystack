# LongMuch — How much? How Long?

Instant 5-year 10-K metrics. No paywall. No bloat.

* **Comprehensive Metric Calculation:** Calculates and displays a wide array of financial ratios and per-share metrics, including:

    * **Ratios:**
        - Net Income/Revenue
        - Net Income/Equity
        - Net Income/Assets
        - Net Income/Total Liabilities
        - Net Income/Debt
        - Owner Earnings/Revenue
        - Owner Earnings/Equity
        - Owner Earnings/Assets
        - Owner Earnings/Total Liabilities
        - Owner Earnings/Debt
        - Dividends/Net Income
        - Dividends/Owner Earnings
        - Dividends/Equity

    * **Per Share Metrics:**
        - Debt per Share
        - Revenue per Share
        - Net Income per Share
        - Owner Earnings per Share
        - Dividends per Share
        - Equity per Share
        - Assets per Share
        - Cash per Share
        - Liabilities per Share
        - Owner Earnings/30 yr Treasury per Share

## Quick Start

```bash
# Terminal 1 — Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && npm run dev

# Terminal 3 — Agent Orchestrator
ao start   # opens dashboard at http://localhost:3000

# CLI (JSON on stdout)
uv run longmuch health --base http://127.0.0.1:8000
uv run longmuch analyze AAPL --local
uv run longmuch contract
```

## Deploy (push to `main`)

GitHub Actions deploys the Next.js site to Vercel on every push to `main` (`.github/workflows/deploy.yml`).

Set these repository secrets:

| Secret | Where |
| --- | --- |
| `VERCEL_TOKEN` | Vercel → Account → Tokens |
| `VERCEL_ORG_ID` | Vercel project → Settings → General |
| `VERCEL_PROJECT_ID` | same |

In the Vercel project, set `BACKEND_ORIGIN` to the Render API URL (e.g. `https://longmuch-api.onrender.com`). The Vercel project root must be `frontend`.

API hosting is the Render Blueprint in `render.yaml` (live EDGAR; do not set `HAYSTACK_PREFER_FIXTURE`).
