---
name: verify-haystack
description: "Drive LongMuch / haystack Next.js web UI (ticker search, 5-year 10-K metrics) plus FastAPI sidecar on isolated ports, or prove www.longmuch.com is shipped. Use when proving homepage Analyze, KPI/table rendering, GET /health, GET /analyze, or production title+/contract after merge, without attaching to :3000 or :8000."
---

# Verify haystack (LongMuch)

LongMuch (repo folder haystack) is a ticker search that is supposed to show 5-year 10-K metrics. Primary surface is the Next.js 16 web UI. There is no login. Agent orchestrator `ao start` on :3000 is out of scope.

## Surfaces

- Primary (this skill): Next.js 16 App Router UI in `frontend/`. Homepage `frontend/app/page.tsx` is a client component: `h1` LongMuch, subtitle includes `How much? How long?`, text input placeholder `enter stock ticker e.g. AAPL`, button `Analyze`. After client state `data` is set, a table titled `5-Year Financial Metrics` appears. `frontend/app/layout.tsx` metadata title is `LongMuch - How much? How long?`.
- Secondary: FastAPI in `backend/app/main.py` — product endpoints GET `/health` and GET `/analyze/{ticker}` plus GET `/contract` (locked labels + `schema_version`). **Default analyze is live EDGAR**. Fixture mode only via CLI `uv run longmuch analyze TICKER --local`, or `HAYSTACK_PREFER_FIXTURE=1` on the **backend process**. The `?fixture=` query param is ignored. Curl-local env does not switch a running uvicorn. Verify HTTP prove uses live analyze by default; `VERIFY_FIXTURE=1` / `--fixture` runs CLI `--local`.
- Frontend `fetch('/api/analyze/${ticker}')` on the Next origin. Prove that path; do not document a 404 or mock KPI payload unless the live helper still returns one.
- The metrics table is client-rendered from analyze JSON after `data` is set. SSR homepage HTML has no table. Do not treat leftover sample rows in docs as live proof.
- No Playwright/Cypress in the repo. Drive with curl against isolated origins. `helpers/browser.cjs` is an optional skill-local Playwright helper for the Analyze click; homepage SSR HTML is enough for the mandatory proof feature.
- `ao start` / agent-orchestrator.yaml port 3000 is out of scope.

## Isolation (hard rule)

- Dedicated ports only. Bind `127.0.0.1`. Never attach to existing 3000 (Next default / `ao start`) or 8000 (README uvicorn; other gym projects already listen there).
- `helpers/lib.sh` FORBIDDEN_FRONTEND_PORTS=`3000`, FORBIDDEN_BACKEND_PORTS=`8000`. Doctor refuses those ports and any listen PID this run did not start.
- One `next dev` per `frontend/` tree. Turbopack's `.next/dev/lock` is shared; a second isolated port still fails to acquire the lock.
- If `.current-run` doctor-passes, **reuse it**. Do not launch another frontend.
- If the lock is held by a prior verify frontend, run `helpers/cleanup` for that run, then launch. Do not kill listeners on 3000 or 8000.
- Snapshot whatever is on 3000/8000 before launch; leave those PIDs alone.

## Launch

From the haystack repo root:

```bash
.cursor/skills/verify-haystack/helpers/launch
```

What it does:

0. Reuses `.current-run` when doctor would pass. Otherwise, if `.next/dev/lock` is held by a prior verify frontend, cleans that run first.
1. Picks the first free frontend port in 3457-3464 and backend port in 8015-8022 (`lsof` listen check). Refuses 3000 and 8000.
2. Snapshots listeners on 3000 and 8000 for isolation proof. Does not touch those processes.
3. Restores the frontend toolchain when `frontend/node_modules/.bin/next` is missing (`helpers/ensure-frontend.py`).
4. If `frontend/app/components/index.ts` is missing, writes a short barrel marked `verify-haystack scaffolding` so `page.tsx`'s `from './components'` compiles. Cleanup deletes that file if this run created it.
5. Syncs backend deps with `uv` in `backend/`.
6. Double-forks (`helpers/daemonize.py` plus setsid) so agent shells cannot reap the servers. Frontend: Next dev `--hostname 127.0.0.1 --port $FRONTEND_PORT` with CWD `frontend/`. Backend: uvicorn `app.main:app --host 127.0.0.1 --port $BACKEND_PORT` with CWD `backend/`.
7. Ready when GET `$FRONTEND_ORIGIN/` is HTTP 200 and HTML contains `LongMuch`. Backend ready when GET `$BACKEND_ORIGIN/health` is HTTP 200. If backend fails, launch still succeeds for homepage proof (`BACKEND_OK=0`) but API features must skip.
8. Records PIDs, PGIDs, origins in `/tmp/haystack-verify-$RUN_ID/run.env` and points `.cursor/skills/verify-haystack/.current-run` at that dir. Copies `run.env` and isolation snapshot into `artifacts/`.
9. Does **not** set `HAYSTACK_PREFER_FIXTURE` (live EDGAR default). Leaves servers up for browse; does not call cleanup.

Ready when the helper prints `verify-haystack launch ok` and `FRONTEND_ORIGIN=http://127.0.0.1:<port>`. Also prints `left up for browse: FRONTEND_ORIGIN=...` — run `helpers/cleanup` only when done.

## Doctor

Run before driving, and whenever anything looks off:

```bash
.cursor/skills/verify-haystack/helpers/doctor
```

Pass means: frontend port is not 3000, listen PID is one we started (or its descendant), GET `$FRONTEND_ORIGIN/` is HTTP 200, HTML contains `LongMuch`. If `BACKEND_OK=1`, backend port is not 8000, listen PID is ours, GET `$BACKEND_ORIGIN/health` is HTTP 200 with JSON `status=healthy` (live body also has a `message` field). Also runs `browser.cjs check-issues`: a visible Next.js `1 Issue` / `N Issues` badge is **DOCTOR FAIL**. Missing Playwright is hard-flagged (`next_issues_status=skipped-no-playwright`); a prove that ignores that gate is invalid. Fail means do not drive.

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
FEATURE=metrics-docs .cursor/skills/verify-haystack/helpers/http docs
```

`backend-analyze` GETs `/analyze/{ticker}` (**live EDGAR** by default). Fixture when `VERIFY_FIXTURE=1` or `helpers/http backend-analyze TICKER --fixture` / `--local` (CLI `--local`). Launch never sets `HAYSTACK_PREFER_FIXTURE`.

Optional browser (Analyze click / screenshot) **and required Next issues gate**. `browser.cjs snapshot|analyze|check-issues` fails if the Next.js Dev Tools badge shows a visible `1 Issue` / `N Issues` (`data-next-badge[data-error=true]`). A prove that ignores that badge is **invalid**. If Playwright/Chromium is missing, `snapshot`/`analyze` write `browser-skipped.txt` and exit 0 (HTTP proof still stands), but `check-issues` exits 2 (hard-flag: gate not run). Doctor and `helpers/http home` invoke `check-issues`.

```bash
FEATURE=home-search node .cursor/skills/verify-haystack/helpers/browser.cjs snapshot
FEATURE=home-search node .cursor/skills/verify-haystack/helpers/browser.cjs check-issues
FEATURE=analyze-results node .cursor/skills/verify-haystack/helpers/browser.cjs analyze AAPL
```

### Stable handles (from `frontend/app/page.tsx` and `layout.tsx`)

- `h1` text `LongMuch`
- subtitle `Fundamental Analysis to answer two questions - How much? How long?`
- `input[placeholder="enter stock ticker e.g. AAPL"]`
- `button` text `Analyze` (while loading: `Analyzing...`); disabled when loading or ticker is blank, so it is disabled on the empty SSR homepage
- footer `Last 5 years of 10-K metrics. No login. No ads. No bloat.` plus link `How metrics are calculated` to `/docs`
- `/docs` SSR: `h1` `How metrics are calculated`; all 32 `LOCKED_LABELS` strings in contract order
- After `data` is set: table `h2` includes `5-Year Financial Metrics`; rows use Owner Earnings labels (schema 8) with six group headers from `groups`
- Document title `LongMuch - How much? How long?` (layout metadata)
- Next API path `/api/analyze/:ticker` (proxies to FastAPI; prove HTTP 200 with locked metric labels from `/contract`)
- FastAPI GET `/health`, GET `/analyze/{ticker}` (live EDGAR default; fixture via `HAYSTACK_PREFER_FIXTURE` or CLI `--local` only), GET `/contract` on the backend origin only

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
- Default backend analyze is **live EDGAR**. Fixture/mocks only when explicitly requested (CLI `--local`, `VERIFY_FIXTURE=1` / helper `--fixture` via CLI, or backend-process `HAYSTACK_PREFER_FIXTURE=1`). The `?fixture=` query is ignored. The table appears only after client `data` is set; SSR `/` has no metric rows.
- **Next issues badge:** if the page shows a visible Next.js `1 Issue` / `N Issues` badge, prove **fails**. Ignoring that badge is invalid. Detect via Playwright (`helpers/browser.cjs check-issues`); SSR/curl cannot see it.
- **Live origin (ship).** Isolated doctor on 3457–3464 / 8015–8022 is not production. Merged `main` is git, not runtime. A green **Deploy website** / `deploy-frontend` job is not ship. Vercel HTML and Render `/contract` deploy independently. Do not tell the user the job is done until `helpers/live-origin` passes: public HTML `<title>` is `LongMuch - How much? How long?` (no `Create Next App`) **and** `GET {LIVE_API}/contract` `schema_version` matches `uv run longmuch contract` from this checkout. Frontend 200 with an `h1` of LongMuch is not enough. If the API host is asleep or still on an old schema, that is a failed ship. Deploy or wake `longmuch-api`, then re-run the gate. Defaults: `LIVE_WEB=https://www.longmuch.com`, `LIVE_API=https://longmuch-api.onrender.com`. GitHub job `prove-live` after `deploy-frontend` is the same check. Do not treat isolated `helpers/http home` as that gate.

Feature recipes: `features/README.md` and one file per feature.

## Leave-up / browse mode (default) + Cleanup (opt-in)

After launch / prove, **servers stay up** so Jacob can open `FRONTEND_ORIGIN` in a browser. Do **not** run cleanup unless the user/agent explicitly asks. Launch prints `left up for browse: FRONTEND_ORIGIN=...` and reminds that cleanup is opt-in.

```bash
.cursor/skills/verify-haystack/helpers/cleanup
```

`helpers/cleanup` is **optional**. When requested, it kills only the process groups / PIDs this launch recorded. Refuses to kill anything listening on 3000/8000. Removes `/tmp/haystack-verify-$RUN_ID` and the scaffolding barrel if this run created it. Never deletes `artifacts/`. Never kills whatever is on 3000/8000 that we did not start. Isolated ports only — never touch 3000/8000.

## Helpers

All under `.cursor/skills/verify-haystack/helpers/`, executable. Invocations:

- `helpers/launch` — isolated frontend + backend
- `helpers/doctor` — read-only health plus isolation gate
- `helpers/http home|analyze-api|backend-health|backend-analyze|backend-contract|empty-ticker` — curl against isolated origins
- `helpers/live-origin` — production ship gate (www.longmuch.com title + Render `/contract` vs local schema)
- `node helpers/browser.cjs snapshot|analyze` — optional Playwright vs `$FRONTEND_ORIGIN` only
- `helpers/cleanup` — **optional** teardown of our instance (leave-up is the default after prove)
- `node helpers/browser.cjs check-issues` — fail if Next.js shows a visible Issues badge
- `python3 helpers/ensure-frontend.py` — restore Next toolchain if `node_modules` is missing (called by launch)

`helpers/lib.sh`, `helpers/launch.py`, `helpers/ensure-frontend.py`, and `helpers/daemonize.py` are internals used by the scripts above.

## Maintenance

Keep the map honest with `/maintain-verification-skill` as the UI changes.

If an implementation change alters copy, placeholders, locked labels, schema version, or contract fields that helpers grep, update `helpers/http`, `helpers/browser.cjs`, Stable handles above, and the matching `features/*.md` **in that same change**. Do not wait for `/verify-haystack` to discover drift.
