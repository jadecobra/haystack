# Home search

The LongMuch landing page is a ticker search: a large heading, a subtitle, one text field, and an Analyze button. Opening `/` in a browser (or GET `/` over HTTP) is the whole feature. There is no login.

## Sub-features

- `home-heading` shows `h1` LongMuch and subtitle `Clean. Instant. Fundamental analysis.`
- `home-ticker` shows a text input with placeholder `AAPL or TSLA`.
- `home-analyze` shows a button whose idle label is `Analyze`.
- `home-footer` shows `Last 5 years of 10-K metrics. No login. No ads. No bloat.`
- `home-title` document title is still `Create Next App` (layout metadata).

## How to get to it (user POV)

- Open the Next origin `/` in a browser.
- GET `$FRONTEND_ORIGIN/` with curl (SSR HTML of the client homepage).

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN` from `helpers/launch`.
- `helpers/doctor` reports `DOCTOR PASS`.
- Do not use `http://127.0.0.1:3000`.

- **Open landing.** Visit `/`. Run `FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home`. HTTP 200. HTML contains `LongMuch`, `AAPL or TSLA`, `Analyze`, and `Clean. Instant. Fundamental analysis.`
- **Confirm identity.** Read `artifacts/home-search/home.meta.txt`. `h1` is `LongMuch`. `placeholder` is `AAPL or TSLA`. `button` is `Analyze`. `title` is `Create Next App`.
- **No side effects.** Repeat the GET. Status stays 200 and the HTML still has no `5-Year Financial Metrics` table (that block is client-only after `data` is set).
- **Optional screenshot.** Run `FEATURE=home-search node .cursor/skills/verify-haystack/helpers/browser.cjs snapshot`. If Chromium is missing, `browser-skipped.txt` is enough; HTTP proof still stands.
- **Proof.** Keep `artifacts/home-search/home.html`, `home.status`, and `home.meta.txt`. Cleanup must not delete them.

## Gotchas

- Document title is `Create Next App`, not LongMuch. Assert `h1`, not `<title>`.
- Homepage is `'use client'`. SSR still emits the heading, placeholder, and Analyze button; KPI cards and the 5-year table are not in the first HTML.
- Agent orchestrator `ao start` also wants :3000. This skill never uses that origin.
- Analyze is disabled while the ticker is empty, so the SSR button has a `disabled` attribute. That is expected on first paint.
