# Haystack (LongMuch)

LongMuch computes annual SEC 10-K metrics, owner earnings yields, and peer tables with no login or database. The repository is `haystack`, the web product is LongMuch (`longmuch.com`), the Python CLI is `longmuch`, the Next.js app is `longmuch-web`, and `HAYSTACK_BACKEND_ORIGIN` is the legacy fallback env var for `BACKEND_ORIGIN`.

## Where things live

- `backend/app/` holds the FastAPI API (`main.py`), CLI (`cli.py`), EDGAR mapper (`edgar.py`), locked contract (`metrics.py`), and screen or peer builders.
- `backend/data/` holds committed factory rules and generated JSON snapshots.
- `backend/tests/` holds pytest suites for EDGAR parsing, metric math, contracts, and comment linting.
- `frontend/app/` holds Next.js App Router pages (`/`, `/[ticker]`, `/screen`, `/sector/[slug]`, `/docs`) and API proxies under `api/`.
- `frontend/lib/` holds pure TypeScript helpers, static label copies, and `node:test` suites.
- `frontend/public/screen/` holds copies of `sp500-oe-yield.json` and `sp1500-oe-yield.json` for API fallback and OG metadata.
- `docs/CONTEXT.md` maps data ownership and change impact across the repo and workflows.
- `docs/adr/` holds accepted architecture decision records.
- `.github/workflows/` defines CI, Vercel and Render deploys, click-through checks, and scheduled data refreshes.
- `scripts/click-through/` holds Playwright suites run in PR CI and post-deploy checks.
- `.cursor/skills/verify-haystack/` holds the isolated local verification harness (`launch`, `doctor`, `http`, `live-origin`).

## Commands

- Run backend tests and lint with `cd backend && uv run pytest tests/ && uv run ruff check .`.
- Run frontend tests, build, and lint with `cd frontend && pnpm test && BACKEND_ORIGIN=https://example.invalid pnpm run build && pnpm run lint`.
- Print the locked metric contract with `uv run longmuch contract`.
- Run local fixture analysis with `uv run longmuch analyze AAPL --local`.

## Where to go next

- Read [spec.md](spec.md) for product behavior, SEC rules, and the 32 locked metric labels.
- Read [docs/CONTEXT.md](docs/CONTEXT.md) before changing schemas, workflows, snapshots, or UI selectors.
- Read [docs/adr/](docs/adr/) for post-filing splits and NASDAQ ICB taxonomy decisions.
- Read [.cursor/skills/verify-haystack/SKILL.md](.cursor/skills/verify-haystack/SKILL.md) before driving isolated dev servers or `live-origin`.
