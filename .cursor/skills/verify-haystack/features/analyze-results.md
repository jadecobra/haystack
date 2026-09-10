# Analyze results

Submitting a ticker shows a previous-close line (when the API has one) and a `Financial Metrics` table of the 32 locked rows. The Next origin proxies `GET /api/analyze/{ticker}` to FastAPI. Proof is HTTP 200 plus the locked labels in the JSON, then the same labels in the page after Analyze.

## Sub-features

- `analyze-submit` sends the trimmed uppercase ticker to `/api/analyze/:ticker` on the Next origin.
- `analyze-proxy` requires `frontend/app/api/analyze/[ticker]/route.ts` to return 200 when the backend is up.
- `analyze-table` renders `data.years` columns and `data.metrics` rows from that JSON. There are no KPI cards and no hardcoded `$200B` rows.

## How to get to it (user POV)

- Type a ticker into `enter stock ticker e.g. AAPL` and choose Analyze.
- Press Enter in the ticker field (same handler).
- GET `$FRONTEND_ORIGIN/api/analyze/AAPL` (what the button fetch hits).

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN`.
- Isolated FastAPI is healthy; `BACKEND_ORIGIN` (or `HAYSTACK_BACKEND_ORIGIN`) points at it.
- `helpers/doctor` reports `DOCTOR PASS`.
- Do not treat FastAPI `/analyze/{ticker}` alone as this feature (that is `backend-analyze`).

- **Homepage first.** Run `FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home` if not already captured. Confirm no `Financial Metrics` in SSR HTML.
- **Hit the Next API the button uses.** Run `FEATURE=analyze-results .cursor/skills/verify-haystack/helpers/http analyze-api AAPL`. Record HTTP 200, body with `schema_version` and locked labels, and `analyze-api.meta.txt`.
- **Optional click.** Run `FEATURE=analyze-results node .cursor/skills/verify-haystack/helpers/browser.cjs analyze AAPL`. After the click, the table should match the JSON rows.
- **Proof.** Status 200, locked labels in JSON, table present after Analyze. A 404 here is a fail, not expected.

## Gotchas

- Handler path is `frontend/app/api/analyze/[ticker]/route.ts`. The UI fetches `/api/analyze/${ticker}` with no query string.
- Frontend does not call FastAPI by browser origin. The proxy does.
- FastAPI 400 bodies use `detail`. The UI reads `error` / `message`, so invalid tickers may show a generic Analyze failed (400).
