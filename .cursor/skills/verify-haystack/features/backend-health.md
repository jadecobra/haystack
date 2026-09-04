# Backend health

The FastAPI sidecar exposes GET `/health` so a client can tell the LongMuch API process is up. This is a service path, not the Next homepage. Proof is HTTP to the isolated backend origin, not unittest `TestClient`.

## Sub-features

- `health-200` returns HTTP 200 JSON with `"status": "healthy"`.
- `health-message` live body also includes `"message": "LongMuch API is running 🚀"` (the rocket may be present).
- `health-isolated` only the launch backend origin is in scope; never `:8000`.

## How to get to it (user POV)

- GET `$BACKEND_ORIGIN/health` (no auth).
- There is no health link on the Next homepage.

## Driving it with verify-haystack

Preconditions:

- Launch recorded `BACKEND_OK=1` and `BACKEND_ORIGIN`.
- `helpers/doctor` reports `DOCTOR PASS` including `http_health=200`.
- If `BACKEND_OK=0`, report `verified-unreachable` with the launch warning; do not curl `:8000`.

- **GET health.** Run `FEATURE=backend-health .cursor/skills/verify-haystack/helpers/http backend-health`. HTTP 200. Body JSON `status` is `healthy`.
- **Proof.** Keep `artifacts/backend-health/health.json`, `health.status`, and `health.meta.txt`. Compare against the live body, not `backend/tests/test_analysis.py`.

## Gotchas

- `backend/tests/test_analysis.py` `test_health_endpoint` asserts `{"status": "healthy"}` with dict equality. Live `/health` also returns `message`. Using the unittest as the only proof would fail or hide the extra field. Doctor checks the live `status` field.
- README default port 8000 is occupied by other projects. This skill's origin is 8015-8022 on `127.0.0.1`.
- CORS allows `*`. That does not mean the Next UI calls this endpoint today.
