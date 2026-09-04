#!/bin/bash
# Haystack One-Command Bootstrap - FastAPI + Next.js 16 + Agent Orchestrator
# Run with: ./bootstrap-haystack.sh

set -e

echo "🚀 Starting Haystack Full Bootstrap..."

# === 1. Prerequisites ===
if ! command -v uv &> /dev/null; then
  echo "Installing uv (modern Python tool)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

if ! command -v node &> /dev/null; then
  echo "❌ Node.js is required. Please install it (nvm or https://nodejs.org)."
  exit 1
fi

# === 2. Directory Structure & Backend ===
echo "📦 Setting up FastAPI backend with uv + edgartools..."
mkdir -p backend
cd backend

uv init --app --name haystack-backend --python 3.12
uv add fastapi "uvicorn[standard]" edgartools pydantic-settings python-dotenv redis httpx pandas pyarrow
uv add --dev ruff pytest

mkdir -p app
cat > app/main.py << 'EOT'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edgartools
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Haystack API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisResponse(BaseModel):
    ticker: str
    data: dict
    status: str
    message: str

@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Haystack API is running 🚀"}

@app.get("/analyze/{ticker}", response_model=AnalysisResponse)
async def analyze_ticker(ticker: str):
    ticker = ticker.upper().strip()
    try:
        # Real edgartools call - agents will expand this into full 5yr ratios
        company = edgartools.Company(ticker)
        facts = company.get_facts()  # or companyfacts JSON API for max speed
        return {
            "ticker": ticker,
            "data": {"facts_count": len(facts) if facts else 0, "raw": facts[:5]},  # placeholder
            "status": "success",
            "message": "Analysis stub ready for full ratio calculations"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOT

cd ..

# === 3. Frontend - Next.js 16 ===
echo "⚛️ Setting up Next.js 16 frontend..."
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --yes

cd frontend

# Beautiful dark search UI (agents will add shadcn + Recharts next)
cat > app/page.tsx << 'EOT'
'use client';

import { useState } from 'react';

export default function Home() {
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    window.location.href = `/analyze/${ticker.toUpperCase().trim()}`;
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-white flex items-center justify-center">
      <div className="max-w-3xl mx-auto text-center px-6">
        <h1 className="text-8xl font-bold tracking-tighter mb-6">haystack</h1>
        <p className="text-3xl text-zinc-400 mb-16">Clean. Instant. Fundamental analysis.</p>

        <div className="flex gap-4 max-w-xl mx-auto">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="AAPL or TSLA"
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-3xl px-8 py-5 text-2xl focus:outline-none focus:border-white placeholder-zinc-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading || !ticker.trim()}
            className="bg-white hover:bg-zinc-100 text-black px-12 rounded-3xl font-semibold text-xl transition-all disabled:opacity-50 flex items-center justify-center min-w-[160px]"
          >
            {loading ? "Analyzing..." : "Analyze"}
          </button>
        </div>

        <p className="mt-12 text-zinc-500 text-lg">Last 5 years of 10-K metrics. No login. No ads. No bloat.</p>
      </div>
    </main>
  );
}
EOT

cd ..

# === 4. Agent Orchestrator Config ===
echo "🧠 Setting up Agent Orchestrator..."
cat > agent-orchestrator.yaml << 'EOL'
port: 3000

defaults:
  runtime: tmux
  agent: claude-code
  workspace: worktree
  notifiers: [desktop]

projects:
  haystack:
    repo: jadecobra/haystack
    path: .
    defaultBranch: main
    sessionPrefix: hs

reactions:
  ci-failed:
    auto: true
    action: send-to-agent
    retries: 3
  changes-requested:
    auto: true
    action: send-to-agent
    escalateAfter: 25m
  approved-and-green:
    auto: false
    action: notify
EOL

ao init --auto || true

# === 5. Final polish ===
cat > README.md << 'EOF'
# LongMuch — How much? How Long?

Instant 5-year 10-K metrics. No paywall. No bloat.

## Quick Start

```bash
# Terminal 1 — Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && npm run dev

# Terminal 3 — Agent Orchestrator
ao start   # opens dashboard at http://localhost:3000
EOF

echo ""
echo "🎉 Bootstrap complete!"
echo ""
echo "=== NEXT STEPS (do these now) ==="
echo "1. Start the orchestrator →  ao start"
echo "2. In two more terminals:"
echo "   cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000"
echo "   cd frontend && npm run dev"
echo ""
echo "3. Open http://localhost:3000 (dashboard) — you now have a live self-improving system."
echo ""
echo "4. Start the improvement loop with these one-liners:"
echo "   ao spawn haystack "Implement full 5-year ratio calculations + Redis caching""
echo "   ao spawn haystack "Add shadcn/ui DataTable + Recharts KPI cards""
echo "   ao spawn haystack "Add background cache warmer for S&P 500 tickers""
echo ""
echo "Haystack is now alive and will keep getting better while you sleep. 🚀"
echo ""
echo "Run ./bootstrap-haystack.sh again anytime to reset (safe — it overwrites only skeleton)."