# Backend analyze

GET `/analyze/{ticker}` returns the locked 26-row metric table. **Default source is live EDGAR** (SEC companyfacts + FRED). Fixture mode is opt-in only.

## Sub-features

- `analyze-path` GET `$BACKEND_ORIGIN/analyze/{ticker}` with the ticker uppercased (live EDGAR).
- `analyze-fixture` CLI `--local`, or caller-exported / helper-set `HAYSTACK_PREFER_FIXTURE=1`, returns `source=fixture` and 26 locked labels. The `?fixture=` query is ignored.
- `analyze-not-frontend` the Next UI does not call this URL; it fetches `/api/analyze/:ticker` on the frontend origin.

## How to get to it (user POV)

- There is no UI control that hits FastAPI `/analyze/{ticker}` today.
- A service client would GET `$BACKEND_ORIGIN/analyze/AAPL` (live). For deterministic fixture, export `HAYSTACK_PREFER_FIXTURE=1` or use CLI `--local`.
- Agents proving table logic without HTTP: `uv run longmuch analyze AAPL --local`.

## Driving it with verify-haystack

Preconditions:

- Launch recorded `BACKEND_OK=1`.
- Do not use `:8000`.
- Launch must not set `HAYSTACK_PREFER_FIXTURE` (live default).

- **HTTP prove (live).** `FEATURE=backend-analyze .cursor/skills/verify-haystack/helpers/http backend-analyze AAPL` — expects 200, `source=edgar`, treasury label. No fixture env.
- **HTTP fixture (opt-in).** `VERIFY_FIXTURE=1 FEATURE=backend-analyze .cursor/skills/verify-haystack/helpers/http backend-analyze AAPL` or `... backend-analyze AAPL --fixture` (helper sets `HAYSTACK_PREFER_FIXTURE=1` for that curl).
- **Local logic.** From repo root: `uv run longmuch analyze AAPL --local` (fixture JSON stdout, exit 0).
- **Proof.** Live JSON with 26 rows (`source=edgar`) unless fixture was explicitly requested. Do not treat FastAPI success as proof that the Analyze button works.
- **Leave-up.** Do not cleanup after prove unless asked; open `FRONTEND_ORIGIN` to browse.

## Gotchas

- Do not invent a second verify skill. CLI is for logic; `helpers/http` is for the UI/HTTP path.
- Do not rely on `?fixture=1` — the query is ignored; use env or CLI `--local`.
- Caller may export `HAYSTACK_PREFER_FIXTURE=1`; launch must not set it. The http helper sets it only for an explicit fixture prove.
