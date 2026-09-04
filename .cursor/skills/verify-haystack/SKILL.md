---
name: verify-haystack
description: "Drive LongMuch / haystack Next.js web UI (ticker search, 5-year 10-K metrics) plus FastAPI sidecar on isolated ports. Use when proving homepage Analyze, KPI/table rendering, GET /health, or GET /analyze without attaching to :3000 or :8000."
---

# Verify haystack (LongMuch)

LongMuch (repo folder haystack) is a ticker search that is supposed to show 5-year 10-K metrics. Primary surface is the Next.js 16 web UI. There is no login. Agent orchestrator `ao start` on :3000 is out of scope.

## Surfaces

- Primary (this skill): Next.js 16 App Router UI in `frontend/`. Homepage `frontend/app/page.tsx` is a client component: `h1` LongMuch, subtitle `Clean. Instant. Fundamental analysis.`, text input placeholder `AAPL or TSLA`, button `Analyze`. After client state `data` is set, KPI cards (Revenue / Net Income / EPS / FCF) and a table titled `5-Year Financial Metrics` appear. `frontend/app/layout.tsx` metadata title is still `Create Next App`.
- Secondary: FastAPI in `backend/app/main.py` — product endpoints GET `/health` and GET `/analyze/{ticker}` plus GET `/contract` (locked labels + `schema_version`). Optional `?fixture=1` on analyze for deterministic runs. Default analyze is fixture until EDGAR ships. No RPC, GraphQL, or agent-auth. Do not require a live SEC call for prove steps.
- Frontend currently `fetch('/api/analyze/${ticker}')` on the Next origin. `frontend/app/api/analyze/[ticker].ts` is a loose `.ts` file, not App Router `route.ts`, so the Next API 404s. The file returns mock KPI JSON and reads `searchParams.ticker`, not the path param. Document the 404; do not pretend KPIs are live 10-K data.
- Table rows in `page.tsx` are hardcoded sample billions (`$200B`). That is a fixture in the React tree, not live 10-K proof. Distinguish it from the mock KPI JSON (also not live, and currently not even served).
- No Playwright/Cypress in the repo. Drive with curl against isolated origins. `helpers/browser.cjs` is an optional skill-local Playwright helper for the Analyze click; homepage SSR HTML is enough for the mandatory proof feature.
- `ao start` / agent-orchestrator.yaml port 3000 is out of scope.

## Isolation (hard rule)

- Dedicated ports only. Bind `127.0.0.1`. Never attach to existing 3000 (Next default / `ao start`) or 8000 (README uvicorn; other gym projects already listen there).
- `helpers/lib.sh` FORBIDDEN_FRONTEND_PORTS=`3000`, FORBIDDEN_BACKEND_PORTS=`8000`. Doctor refuses those ports and any listen PID this run did not start.
- Two instances are OK if ports differ. No shared DB (this app has none).
- Snapshot whatever is on 3000/8000 before launch; leave those PIDs alone.

## Launch

From the haystack repo root:

```bash
.cursor/skills/verify-haystack/helpers/launch
```

What it does:

1. Picks the first free frontend port in 3457-3464 and backend port in 8015-8022 (`lsof` listen check). Refuses 3000 and 8000.
2. Snapshots listeners on 3000 and 8000 for isolation proof. Does not touch those processes.
3. Restores the frontend toolchain when `frontend/node_modules/.bin/next` is missing (`helpers/ensure-frontend.py`).
4. If `frontend/app/components/index.ts` is missing, writes a short barrel marked `verify-haystack scaffolding` so `page.tsx`'s `from './components'` compiles. Cleanup deletes that file if this run created it.
5. Syncs backend deps with `uv` in `backend/`.
6. Double-forks (`helpers/daemonize.py` plus setsid) so agent shells cannot reap the servers. Frontend: Next dev `--hostname 127.0.0.1 --port $FRONTEND_PORT` with CWD `frontend/`. Backend: uvicorn `app.main:app --host 127.0.0.1 --port $BACKEND_PORT` with CWD `backend/`.
7. Ready when GET `$FRONTEND_ORIGIN/` is HTTP 200 and HTML contains `LongMuch`. Backend ready when GET `$BACKEND_ORIGIN/health` is HTTP 200. If backend fails, launch still succeeds for homepage proof (`BACKEND_OK=0`) but API features must skip.
8. Records PIDs, PGIDs, origins in `/tmp/haystack-verify-$RUN_ID/run.env` and points `.cursor/skills/verify-haystack/.current-run` at that dir. Copies `run.env` and isolation snapshot into `artifacts/`.

Ready when the helper prints `verify-haystack launch ok` and `FRONTEND_ORIGIN=http://127.0.0.1:<port>`.

## Doctor

Run before driving, and whenever anything looks off:

```bash
.cursor/skills/verify-haystack/helpers/doctor
```

Pass means: frontend port is not 3000, listen PID is one we started (or its descendant), GET `$FRONTEND_ORIGIN/` is HTTP 200, HTML contains `LongMuch`. If `BACKEND_OK=1`, backend port is not 8000, listen PID is ours, GET `$BACKEND_ORIGIN/health` is HTTP 200 with JSON `status=healthy` (live body also has a `message` field). Fail means do not drive.

## Drive

Launch with this skill's helpers, then:

- Pure table logic (no server): `uv run longmuch analyze AAPL --local` (JSON on stdout; non-zero on incomplete rows). Also `uv run longmuch contract` and `uv run longmuch health --base $BACKEND_ORIGIN`.
- UI / HTTP path: the `helpers/http` commands below against isolated origins. Do not invent a parallel verify skill.

Use the skill helpers against the origins from `run.env`. Never curl `:3000` or `:8000`.

```bash
FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home
FEATURE=analyze-results .cursor/skills/verify-haystack/helpers/http analyze-api AAPL
FEATURE=backend-health .cursor/skills/verify-haystack/helpers/http backend-health
FEATURE=backend-analyze .cursor/skills/verify-haystack/helpers/http backend-analyze AAPL
FEATURE=backend-contract .cursor/skills/verify-haystack/helpers/http backend-contract
FEATURE=empty-ticker .cursor/skills/verify-haystack/helpers/http empty-ticker
```

`backend-analyze` GETs `/analyze/{ticker}?fixture=1` (deterministic). Live EDGAR is still optional (`VERIFY_EDGAR=1` without fixture).

Optional browser (Analyze click / screenshot). If Playwright/Chromium is missing, `browser.cjs` writes `browser-skipped.txt` and exits 0 — that is not a failed HTTP proof:

```bash
FEATURE=home-search node .cursor/skills/verify-haystack/helpers/browser.cjs snapshot
FEATURE=analyze-results node .cursor/skills/verify-haystack/helpers/browser.cjs analyze AAPL
```

### Stable handles (from `frontend/app/page.tsx` and `layout.tsx`)

- `h1` text `LongMuch`
- subtitle `Clean. Instant. Fundamental analysis.`
- `input[placeholder="AAPL or TSLA"]`
- `button` text `Analyze` (while loading: `Analyzing...`); disabled when loading or ticker is blank, so it is disabled on the empty SSR homepage
- footer `Last 5 years of 10-K metrics. No login. No ads. No bloat.`
- After `data` is set: KPI `h3` names Revenue / Net Income / EPS / FCF; table `h2` `5-Year Financial Metrics`
- Document title `Create Next App` (layout metadata, not LongMuch)
- Next API path `/api/analyze/:ticker` (currently 404)
- FastAPI GET `/health`, GET `/analyze/{ticker}` (`?fixture=1` optional), GET `/contract` on the backend origin only

## Evidence

Write under `.cursor/skills/verify-haystack/artifacts/` (survives cleanup). Per feature, capture:

- HTTP status of the user-facing request
- HTML or JSON snapshot
- title / h1 / placeholder / Analyze button text
- Screenshot when `browser.cjs` can launch Chromium

Proof standards:

- Exercise the real user path (browser or HTTP to the Next page). Do not treat `unittest` `TestClient` as the only proof of `/health`.
- Capture the action and the resulting HTML, not only the final screen.
- Homepage GET has no side effects (no writes, no EDGAR).
- Mocks only at the EDGAR boundary. The hardcoded table is a fixture in the React tree — when proving `analyze-results`, distinguish mock KPI JSON (unserved, inside `[ticker].ts`) from that hardcoded table (only rendered after `data` is set). A 404 on `/api/analyze/AAPL` is the current real user path.

Feature recipes: `features/README.md` and one file per feature.

## Cleanup

```bash
.cursor/skills/verify-haystack/helpers/cleanup
```

Kills only the process groups / PIDs this launch recorded. Refuses to kill anything listening on 3000/8000. Removes `/tmp/haystack-verify-$RUN_ID` and the scaffolding barrel if this run created it. Never deletes `artifacts/`. Never kills whatever is on 3000/8000 that we did not start.

## Helpers

All under `.cursor/skills/verify-haystack/helpers/`, executable. Invocations:

- `helpers/launch` — isolated frontend + backend
- `helpers/doctor` — read-only health plus isolation gate
- `helpers/http home|analyze-api|backend-health|backend-analyze|backend-contract|empty-ticker` — curl against isolated origins
- `node helpers/browser.cjs snapshot|analyze` — optional Playwright vs `$FRONTEND_ORIGIN` only
- `helpers/cleanup` — teardown our instance
- `python3 helpers/ensure-frontend.py` — restore Next toolchain if `node_modules` is missing (called by launch)

`helpers/lib.sh`, `helpers/launch.py`, `helpers/ensure-frontend.py`, and `helpers/daemonize.py` are internals used by the scripts above.

## Maintenance

Keep the map honest with `/maintain-verification-skill` as the UI changes.
