# Backend contract

GET `/contract` returns `schema_version` and the locked metric labels so agents can assert table shape without scraping docs.

## Sub-features

- `contract-path` GET `$BACKEND_ORIGIN/contract` returns labels matching `LOCKED_LABELS`.
- `contract-cli` `uv run longmuch contract` prints the same JSON; non-zero if remote labels drift.

## How to get to it (user POV)

- Not shown in the UI. Service/agent clients only.

## Driving it with verify-haystack

Preconditions:

- Launch recorded `BACKEND_OK=1` for HTTP.
- CLI contract has no server requirement.

- **HTTP.** `FEATURE=backend-contract .cursor/skills/verify-haystack/helpers/http backend-contract`
- **CLI.** `uv run longmuch contract` and optionally `uv run longmuch contract --base $BACKEND_ORIGIN`

## Gotchas

- Product HTTP surface is still `/health`, `/analyze/{ticker}`, and this shape endpoint. No RPC/GraphQL/agent-auth.
