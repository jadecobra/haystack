import os

import dotenv
import fastapi
import fastapi.middleware.cors
import pydantic

from app.metrics import LOCKED_LABELS, SCHEMA_VERSION
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


class AnalysisResponse(pydantic.BaseModel):
    ticker: str
    years: list[str]
    rows: list[MetricRow]
    source: str
    status: str
    message: str
    treasury_label: str
    treasury_dgs30_pct: float | None = None
    treasury_dgs30_as_of: str | None = None


def _env_prefer_fixture() -> bool:
    return os.environ.get("HAYSTACK_PREFER_FIXTURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "message": "LongMuch API is running 🚀"}


class ContractResponse(pydantic.BaseModel):
    schema_version: str
    labels: list[str]
    row_count: int
    treasury_label: str


@app.get("/contract", response_model=ContractResponse)
async def contract():
    return {
        "schema_version": SCHEMA_VERSION,
        "labels": list(LOCKED_LABELS),
        "row_count": len(LOCKED_LABELS),
        "treasury_label": "FCF / 30 Year Treasury per Share",
    }


@app.get("/analyze/{ticker}", response_model=AnalysisResponse)
async def analyze_ticker(
    ticker: str,
    fixture: int | None = fastapi.Query(
        default=None,
        description="1 = deterministic fixture; omit = live EDGAR unless HAYSTACK_PREFER_FIXTURE=1",
    ),
):
    # Omitted query → live (prefer_fixture False) unless env forces fixture.
    if fixture is None:
        prefer_fixture = _env_prefer_fixture()
    else:
        prefer_fixture = bool(fixture)
    try:
        payload = analyze(ticker, prefer_fixture=prefer_fixture)
    except ValueError as exc:
        raise fastapi.HTTPException(status_code=400, detail=str(exc)) from exc
    if len(payload["rows"]) != len(LOCKED_LABELS):
        raise fastapi.HTTPException(status_code=500, detail="metric table incomplete")
    if [r["metric"] for r in payload["rows"]] != list(LOCKED_LABELS):
        raise fastapi.HTTPException(status_code=500, detail="metric labels drifted")
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
