# LongMuch / haystack verification map

This directory is the maintained source for verifying the user-facing behavior of LongMuch (haystack). Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch with `.cursor/skills/verify-haystack/helpers/launch` (isolated Next origin on 3457-3464 and FastAPI origin on 8015-8022).
- Run `.cursor/skills/verify-haystack/helpers/doctor` and require `DOCTOR PASS`.
- Drive only `FRONTEND_ORIGIN` / `BACKEND_ORIGIN` printed by launch. Helpers refuse ports 3000 and 8000.
- No login. No seed database.
- Never drive an instance that was not started by this verification run.
- Homepage GET is enough for `home-search`. Do not treat unittest `TestClient` as the user path.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Prefer `h1` LongMuch, the ticker `input` placeholder from `page.tsx`, and the `Analyze` button over coordinates. Keep those strings in sync with SKILL.md Stable handles.
- Treat every command as literal.
- HTTP via `helpers/http`. Browser via `node helpers/browser.cjs`. Both require launch first.
- Table logic: `uv run longmuch analyze AAPL --local`. HTTP/UI: `helpers/http`. Do not invent a parallel verify skill.
- Default `/analyze` is **live EDGAR**. Fixture only via `VERIFY_FIXTURE=1`, `helpers/http backend-analyze TICKER --fixture` (env), CLI `--local`, or caller-exported `HAYSTACK_PREFER_FIXTURE=1`. The `?fixture=` query is ignored.
- After prove, leave servers up (`FRONTEND_ORIGIN`); run `helpers/cleanup` only when explicitly asked.
- A visible Next.js `1 Issue` / `N Issues` badge fails prove/doctor. Ignoring it is invalid.

## Proof and skip reporting

- Capture the user action and the resulting state, not only the final screen.
- UI proof includes HTML snapshot (title, h1, placeholder, Analyze) and a screenshot when Chromium is installed.
- Record the feature ID and entry point used with every artifact under `.cursor/skills/verify-haystack/artifacts/`.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.
- Prove Next `/api/analyze/:ticker` against the live response. If it 404s, record that; if it returns the locked table, prove the labels from GET `/contract`.
- Isolated doctor is not www.longmuch.com. After merge, `helpers/live-origin` must pass (public title + Render `/contract` vs this checkout) before calling the product shipped.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify-haystack` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map except where they change what the user can observe.

## Features

- [Home search](./home-search.md) covers the LongMuch landing page: heading, ticker field, Analyze.
- [Metrics docs](./metrics-docs.md) covers `/docs` formulas and the home link.
- [Analyze results](./analyze-results.md) covers submitting a ticker and the 5-year metrics table from analyze JSON.
- [Backend health](./backend-health.md) covers GET `/health` on the isolated FastAPI origin.
- [Backend analyze](./backend-analyze.md) maps GET `/analyze/{ticker}` (live EDGAR default; fixture via env or CLI `--local`) plus `uv run longmuch analyze TICKER --local`.
- [Empty ticker](./empty-ticker.md) covers Analyze disabled when the input is empty.
