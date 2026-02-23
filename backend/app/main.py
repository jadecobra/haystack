import dotenv
import edgar
import fastapi
import fastapi.middleware.cors
import pydantic
import os

dotenv.load_dotenv()

app = fastapi.FastAPI(title="LongMuch API", version="1.0.0")

app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisResponse(pydantic.BaseModel):
    ticker: str
    data: dict
    status: str
    message: str

@app.get("/health")
async def health():
    return {"status": "healthy", "message": "LongMuch API is running 🚀"}

@app.get("/analyze/{ticker}", response_model=AnalysisResponse)
async def analyze_ticker(ticker: str):
    ticker = ticker.upper().strip()
    try:
        # Real edgar call - agents will expand this into full 5yr ratios
        company = edgar.Company(ticker)
        facts = company.get_facts()  # or companyfacts JSON API for max speed
        return {
            "ticker": ticker,
            "data": {"facts_count": len(facts) if facts else 0, "raw": facts[:5]},  # placeholder
            "status": "success",
            "message": "Analysis stub ready for full ratio calculations"
        }
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
