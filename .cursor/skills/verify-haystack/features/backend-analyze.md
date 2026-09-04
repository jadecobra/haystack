# Backend analyze

GET `/analyze/{ticker}` returns the locked 23-row metric table. Default source is the in-process fixture (deterministic). Pass `?fixture=1` explicitly for agent runs. Live EDGAR is not shipped.

## Sub-features

- `analyze-path` GET `$BACKEND_ORIGIN/analyze/{ticker}` with the ticker uppercased.
- `analyze-fixture` `?fixture=1` (and the default with no query) returns `source=fixture` and 23 locked labels.
- `analyze-not-frontend` the Next UI does not call this URL; it fetches `/api/analyze/:ticker` on the frontend origin.

## How to get to it (user POV)

- There is no UI control that hits FastAPI `/analyze/{ticker}` today.
- A service client would GET `$BACKEND_ORIGIN/analyze/AAPL?fixture=1`.
- Agents proving table logic without HTTP: `uv run longmuch analyze AAPL --local`.

## Driving it with verify-haystack

Preconditions:

- Launch recorded `BACKEND_OK=1`.
- Do not use `:8000`.

- **HTTP prove.** `FEATURE=backend-analyze .cursor/skills/verify-haystack/helpers/http backend-analyze AAPL` — expects 200 and the treasury label. Uses `fixture=1`.
- **Local logic.** From repo root: `uv run longmuch analyze AAPL --local` (JSON stdout, exit 0).
- **Proof.** Fixture JSON with 23 rows. Do not treat FastAPI success as proof that the Analyze button works.

## Gotchas

- Do not invent a second verify skill. CLI is for logic; `helpers/http` is for the UI/HTTP path.
- Never require a live SEC call.
