import os

import dotenv
import fastapi
import fastapi.middleware.cors
import pydantic

from app.metrics import (
    LOCKED_LABELS,
    SCHEMA_VERSION,
    TREASURY_LABEL,
    groups_payload,
)
from app.screen import load_snapshot, rebuild_token, screen_build
from app.sources import analyze

dotenv.load_dotenv()

app = fastapi.FastAPI(title="LongMuch API", version="1.0.0")

_PROD_ORIGINS = [
    "https://longmuch.com",
    "https://www.longmuch.com",
]
_LOCAL_VERIFY_ORIGINS = [
    *(f"http://127.0.0.1:{p}" for p in range(3457, 3465)),
    *(f"http://localhost:{p}" for p in range(3457, 3465)),
]


def _cors_origins() -> list[str]:
    """Prod + local verify ports; CORS_ORIGINS adds comma-separated extras."""
    origins = list(_PROD_ORIGINS) + list(_LOCAL_VERIFY_ORIGINS)
    extra = (os.environ.get("CORS_ORIGINS") or "").strip()
    if extra:
        for part in extra.split(","):
            origin = part.strip()
            if origin and origin not in origins:
                origins.append(origin)
    return origins


app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MetricRow(pydantic.BaseModel):
    metric: str
    values: dict[str, str]
    raw: dict[str, float | None]


class MetricGroup(pydantic.BaseModel):
    id: str
    title: str
    labels: list[str]


class AnalysisResponse(pydantic.BaseModel):
    ticker: str
    company_name: str | None = None
    years: list[str]
    rows: list[MetricRow]
    source: str
    status: str
    message: str
    treasury_label: str
    treasury_dgs30_pct: float | None = None
    treasury_dgs30_as_of: str | None = None
    previous_close: float | None = None
    previous_close_as_of: str | None = None
    groups: list[MetricGroup]
    schema_version: str | None = None
    labels: list[str] | None = None


@app.get("/health")
async def health():
    return {"status": "healthy", "message": "LongMuch API is running 🚀"}


class ContractResponse(pydantic.BaseModel):
    schema_version: str
    labels: list[str]
    row_count: int
    treasury_label: str
    groups: list[MetricGroup]


@app.get("/contract", response_model=ContractResponse)
async def contract():
    return {
        "schema_version": SCHEMA_VERSION,
        "labels": list(LOCKED_LABELS),
        "row_count": len(LOCKED_LABELS),
        "treasury_label": TREASURY_LABEL,
        "groups": groups_payload(),
    }


@app.get("/screen/sp500-oe-yield")
async def screen_sp500_oe_yield():
    payload = load_snapshot()
    if payload is None:
        raise fastapi.HTTPException(status_code=503, detail="screen snapshot missing")
    return payload


@app.post("/screen/sp500-oe-yield/rebuild")
async def screen_sp500_rebuild(
    authorization: str | None = fastapi.Header(default=None),
):
    token = rebuild_token()
    if not token:
        raise fastapi.HTTPException(status_code=403, detail="rebuild disabled")
    expected = f"Bearer {token}"
    if (authorization or "") != expected:
        raise fastapi.HTTPException(status_code=403, detail="unauthorized")
    try:
        payload = screen_build(fail_soft=True, also_seed=False)
    except Exception as exc:
        raise fastapi.HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "universe": payload.get("universe"),
        "count": payload.get("count"),
        "skipped": payload.get("skipped"),
        "built_at": payload.get("built_at"),
        "stale": payload.get("stale"),
        "error": payload.get("error"),
    }


@app.get("/analyze/{ticker}", response_model=AnalysisResponse)
async def analyze_ticker(ticker: str):
    try:
        payload = analyze(ticker)
    except ValueError as exc:
        raise fastapi.HTTPException(status_code=400, detail=str(exc)) from exc
    if len(payload["rows"]) != len(LOCKED_LABELS):
        raise fastapi.HTTPException(status_code=500, detail="metric table incomplete")
    if [r["metric"] for r in payload["rows"]] != list(LOCKED_LABELS):
        raise fastapi.HTTPException(status_code=500, detail="metric labels drifted")
    payload = {
        **payload,
        "groups": groups_payload(),
        "schema_version": SCHEMA_VERSION,
        "labels": list(LOCKED_LABELS),
    }
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
