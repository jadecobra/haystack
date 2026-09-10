# Metrics docs

The public `/docs` page explains how locked table metrics are calculated and how the Analyze table displays them. It is a static Next App Router page. It does not call `/analyze`.

## Sub-features

- `docs-heading` shows `h1` `How metrics are calculated`.
- `docs-primer` covers owner earnings, sources, and last close in plain English bullets.
- `docs-catalog` lists all 32 locked labels in contract order.
- `docs-home-link` is reachable from `/` via `How metrics are calculated`.

## How to get to it (user POV)

- Open `$FRONTEND_ORIGIN/docs`.
- From `/`, follow `How metrics are calculated`.

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN` from `helpers/launch`.
- `helpers/doctor` reports `DOCTOR PASS`.
- Do not use `http://127.0.0.1:3000`.

- **Open docs.** Run `FEATURE=metrics-docs .cursor/skills/verify-haystack/helpers/http docs`. HTTP 200. HTML contains `How metrics are calculated`, spelled-out EDGAR / US-GAAP / FRED / NASDAQ, `Owner Earnings / Last Close Price`, `Owner Earnings / 30 Year Treasury per Share`, and `30 Year Treasury (DGS30)`. No Table contract or Two DGS30 clocks copy.
- **Home still links.** Run `FEATURE=home-search .cursor/skills/verify-haystack/helpers/http home`. HTML contains `How metrics are calculated`.
- **Proof.** Keep `artifacts/metrics-docs/docs.html` and `docs.status`.

## Gotchas

- SSR `/docs` is the proof. The Analyze table is not on this page.
- Label order is the backend contract. `backend/tests/test_docs_contract.py` pins the TS catalog to `LOCKED_LABELS`.
