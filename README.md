# LongMuch — How much? How Long?

Instant 10-K metrics for all available annual years. No paywall. No bloat.

Row names and order live in `backend/app/metrics.py` (`LOCKED_LABELS`). `uv run longmuch contract` prints them. `spec.md` must list the same strings.

## Quick Start

```bash
# Terminal 1 — Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && pnpm install && pnpm dev

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
