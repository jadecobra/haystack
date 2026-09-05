# Home search

The LongMuch landing page is a ticker search: a large heading, a subtitle, one text field, and an Analyze button. Opening `/` in a browser (or GET `/` over HTTP) is the whole feature. There is no login.

## Sub-features

- `home-heading` shows `h1` LongMuch and subtitle including `How much? How long?`
- `home-ticker` shows a text input with placeholder `enter stock ticker e.g. AAPL`.
- `home-analyze` shows a button whose idle label is `Analyze`.
- `home-footer` shows `Last 5 years of 10-K metrics. No login. No ads. No bloat.`
- `home-title` document title is `LongMuch - How much? How long?` (layout metadata).

## How to get to it (user POV)

- Open the Next origin `/` in a browser.
- GET `$FRONTEND_ORIGIN/` with curl (SSR HTML of the client homepage).

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN` from `helpers/launch`.
- `helpers/doctor` reports `DOCTOR PASS`.
- Do not use `http://127.0.0.1:3000`.

- **Open landing.** Visit `/`. Run `FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home`. HTTP 200. HTML contains `LongMuch`, `enter stock ticker e.g. AAPL`, `Analyze`, and `How much? How long?`
- **Confirm identity.** Read `artifacts/home-search/home.meta.txt`. `h1` is `LongMuch`. `placeholder` is `enter stock ticker e.g. AAPL`. `button` is `Analyze`. `title` is `LongMuch - How much? How long?`.
- **No side effects.** Repeat the GET. Status stays 200 and the HTML still has no `5-Year Financial Metrics` table (that block is client-only after `data` is set).
- **Optional screenshot.** Run `FEATURE=home-search node .cursor/skills/verify-haystack/helpers/browser.cjs snapshot`. If Chromium is missing, `browser-skipped.txt` is enough; HTTP proof still stands.
- **Next issues gate.** `helpers/http home` and doctor run `browser.cjs check-issues`. A visible Next.js `1 Issue` / `N Issues` badge fails the prove. Ignoring it is invalid.
- **Proof.** Keep `artifacts/home-search/home.html`, `home.status`, and `home.meta.txt`. Leave servers up after prove; run `helpers/cleanup` only when asked (artifacts survive cleanup).

## Gotchas

- Document title and `h1` both say LongMuch. Prefer `h1` for identity; `<title>` should match `LongMuch - How much? How long?`.
- Homepage is `'use client'`. SSR still emits the heading, placeholder, and Analyze button; KPI cards and the 5-year table are not in the first HTML.
- Agent orchestrator `ao start` also wants :3000. This skill never uses that origin.
- Analyze is disabled while the ticker is empty, so the SSR button has a `disabled` attribute. That is expected on first paint.
