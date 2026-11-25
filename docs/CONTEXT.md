# Haystack Context and Change-Impact Map

This file indexes committed data ownership and cross-component change impact.

## Data assets in backend/data/

| File | Kind | Owner or generator | Readers |
|---|---|---|---|
| `cik_predecessors.json` | Factory (hand-authored) | Manual edits with filing citations | `backend/app/edgar.py` |
| `share_classes.json` | Factory (hand-authored) | Manual edits with ratio citations | `backend/app/share_classes.py` |
| `share_class_counts.json` | Product (generated) | `longmuch share-classes-refresh` via `.github/workflows/screen-sp500.yml` | `backend/app/share_classes.py` |
| `sp1500_map.json` | Product (generated) | `python -m app.sp1500_map` via `.github/workflows/sp500-map.yml` | `backend/app/sp1500_map.py`, `classification.py`, `screen.py` |
| `us_taxonomy.json` | Product (generated) | `python -m app.us_taxonomy` via `.github/workflows/us-taxonomy.yml` | `backend/app/us_taxonomy.py`, `classification.py`, `sic_peers.py` |
| `sic_peers.json` | Product (generated) | `python -m app.sic_peers` via `sic-peers.yml` and `us-taxonomy.yml` | `backend/app/sic_peers.py`, `classification.py`, `screen.py` |
| `peer_metrics.json` | Product (generated) | `python -m app.peer_metrics` via `.github/workflows/sic-peers.yml` | `backend/app/peer_metrics.py` |
| `sp1500-oe-yield.json` | Product (generated) | `longmuch screen-build --universe sp1500 --seed` via `screen-sp500.yml` | `backend/app/screen.py`, `peer_metrics.py`, `frontend/public/screen/sp1500-oe-yield.json` |
| `sp500-oe-yield.json` | Product (sliced copy) | `screen.slice_payload` inside `screen_build` via `screen-sp500.yml` | `backend/app/screen.py`, `peer_metrics.py`, `frontend/public/screen/sp500-oe-yield.json` |

Runtime caches live under gitignored `backend/.cache/`. Never treat `backend/.cache/` as committed source.

## Change-impact index

| If you change | Hits | Does not hit |
|---|---|---|
| `LOCKED_LABELS` or `LOCKED_GROUPS` in `backend/app/metrics.py` | `spec.md`, `frontend/lib/locked-labels.ts`, `frontend/lib/metrics-catalog.ts`, `backend/tests/test_docs_contract.py`, `.cursor/skills/verify-haystack/helpers/http` | `backend/data/sp1500-oe-yield.json` schema or peer rows |
| `SCHEMA_VERSION` in `backend/app/metrics.py` | `spec.md`, `.cursor/skills/verify-haystack/helpers/http`, `.cursor/skills/verify-haystack/helpers/live-origin`, `backend/tests/test_docs_contract.py` | `frontend/lib/locked-labels.ts` unless labels also change |
| `PeerRow` fields in `backend/app/main.py` | `backend/app/peer_metrics.py` (`ROW_KEYS`), `backend/app/screen.py`, `frontend/lib/sectorTable.ts` (`SectorRow`), `backend/tests/test_docs_contract.py` | `LOCKED_LABELS` or `GET /contract` |
| Screen snapshot schema in `backend/app/screen.py` | `backend/data/sp*-oe-yield.json`, `frontend/public/screen/sp*-oe-yield.json`, `frontend/app/utils/screen-name.ts`, `frontend/lib/sectorTable.ts`, `frontend/app/screen/page.tsx` | `backend/app/metrics.py` (`LOCKED_LABELS`) |
| Workflow `name:` in `.github/workflows/*.yml` | `.github/workflows/main-red-issue.yml`, `.github/workflows/deploy-catchup.yml`, `.github/workflows/click-through-prod.yml`, `backend/tests/test_docs_contract.py` | Application runtime on Vercel or Render |
| DOM `data-testid` or copy in `frontend/app/` | `scripts/click-through/browser.cjs`, `scripts/click-through/click-through-faults.cjs`, `.cursor/skills/verify-haystack/SKILL.md`, `.cursor/skills/verify-haystack/helpers/http` | `backend/app/` or `backend/tests/` |
| Comment lint rules in `frontend/eslint.config.mjs` | `backend/tests/test_no_comments.py` (`COMMENT_POLICY` parity check) | Runtime code behavior |
| Backend ports, origin, or deploy config | `render.yaml`, `.github/workflows/deploy.yml`, Vercel `BACKEND_ORIGIN` env var, `frontend/app/api/*/route.ts` | Local `verify-haystack` ports (`3457` to `3464`, `8015` to `8022`) |
