# Analyze results

Submitting a ticker is supposed to show KPI cards (Revenue / Net Income / EPS / FCF) and a `5-Year Financial Metrics` table. Today the Next fetch 404s, so those blocks do not appear. If JSON ever parsed, KPI numbers would come from mock growth fields and the table rows would still be hardcoded sample billions — not live 10-K data.

## Sub-features

- `analyze-submit` sends the trimmed uppercase ticker to `/api/analyze/:ticker` on the Next origin.
- `analyze-404` records that this path currently 404s because `frontend/app/api/analyze/[ticker].ts` is not an App Router `route.ts`.
- `analyze-mock-json` notes the unserved mock KPI payload (`revenue.growth` 15.2, etc.) inside that file; it also reads `searchParams.ticker`, not the path param.
- `analyze-hardcoded-table` notes that table rows in `page.tsx` are fixtures (`2023 $200B` … `2019 $100B`) rendered only after `data` is set.
- `analyze-click` optional Playwright fill + Analyze click; still not live 10-K proof.

## How to get to it (user POV)

- Type a ticker into `AAPL or TSLA` and choose `Analyze`.
- Press Enter in the ticker field (same handler).
- GET `$FRONTEND_ORIGIN/api/analyze/AAPL` (what the button fetch hits).

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN`.
- `helpers/doctor` reports `DOCTOR PASS`.
- Do not call FastAPI `/analyze/{ticker}` as a substitute for this feature (that is `backend-analyze`, EDGAR-bounded).

- **Homepage first.** Run `FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home` if not already captured. Confirm no `5-Year Financial Metrics` in SSR HTML.
- **Hit the Next API the button uses.** Run `FEATURE=analyze-results .cursor/skills/verify-haystack/helpers/http analyze-api AAPL`. Record HTTP status (currently 404), body, and `analyze-api.meta.txt`.
- **Optional click.** Run `FEATURE=analyze-results node .cursor/skills/verify-haystack/helpers/browser.cjs analyze AAPL`. After the click, `after-click.html` should still lack a live 10-K table. If Playwright is missing, keep `browser-skipped.txt`.
- **Proof.** A 404 (or other real status) plus homepage HTML is the proof. Do not claim mock KPI JSON was served unless the status is 200 and the body matches that JSON. Do not claim the `$200B` rows are 10-K data even if they appear — they are hardcoded in `page.tsx`.

## Gotchas

- Valid App Router handler would be `frontend/app/api/analyze/[ticker]/route.ts`. The loose `[ticker].ts` file is never registered; leftover `.next/dev/server/app-paths-manifest.json` only lists `/page`.
- Even if renamed to `route.ts`, the handler reads `searchParams.get('ticker')`, while the UI fetches `/api/analyze/${ticker}` with no query string, so `ticker` would be null.
- Mock KPI JSON is growth/change percents. The table is dollar billions. They are two different fixtures.
- Frontend does not call FastAPI. There is no rewrite in `next.config.ts`.
- `response.json()` on a 404 HTML body throws; `data` stays null; KPI cards never mount.
