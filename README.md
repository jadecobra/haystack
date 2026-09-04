# LongMuch — How much? How Long?

Instant 5-year 10-K metrics. No paywall. No bloat.

* **Comprehensive Metric Calculation:** Calculates and displays a wide array of financial ratios and per-share metrics, including:

    * **Ratios:**
        - Net Income/Revenue
        - Net Income/Equity
        - Net Income/Assets
        - Net Income/Total Liabilities
        - Net Income/Debt
        - Free Cash Flow/Revenue
        - Free Cash Flow/Equity
        - Free Cash Flow/Assets
        - Free Cash Flow/Total Liabilities
        - Free Cash Flow/Debt
        - Dividends/Net Income
        - Dividends/Free Cash Flow
        - Dividends/Equity

    * **Per Share Metrics:**
        - Debt per Share
        - Revenue per Share
        - Net Income per Share
        - Free Cash Flow per Share
        - Dividends per Share
        - Equity per Share
        - Assets per Share
        - Cash per Share
        - Liabilities per Share
        - Free Cash Flow/30 yr Treasury per Share

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
