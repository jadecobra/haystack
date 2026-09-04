'use client';

import { useState } from 'react';
import { Card, DataTable } from './components';

type MetricRow = { metric: string; values: Record<string, string> };

type Analysis = {
  ticker: string;
  years: string[];
  rows: MetricRow[];
  source?: string;
  status?: string;
  message?: string;
  error?: string;
};

export default function Home() {
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Analysis | null>(null);

  const handleSearch = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/analyze/${ticker.toUpperCase().trim()}`);
      const result = (await response.json()) as Analysis;
      if (!response.ok) {
        setData(null);
        setError(result.error || result.message || `Analyze failed (${response.status})`);
        return;
      }
      if (!result.rows?.length || !result.years?.length) {
        setData(null);
        setError('Backend returned no metric table');
        return;
      }
      setData(result);
    } catch (err) {
      console.error('Error fetching data:', err);
      setData(null);
      setError('Could not reach /api/analyze');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const headers = data ? ['Metric', ...data.years] : [];
  const rows = data
    ? data.rows.map((row) => [row.metric, ...data.years.map((y) => row.values[y] ?? '—')])
    : [];

  return (
    <main className="min-h-screen bg-zinc-950 text-white flex items-center justify-center">
      <div className="max-w-7xl mx-auto text-center px-6">
        <h1 className="text-8xl font-bold tracking-tighter mb-6">LongMuch</h1>
        <p className="text-3xl text-zinc-400 mb-16">
          Clean. Instant. Fundamental analysis.
        </p>

        <div className="flex gap-4 max-w-4xl mx-auto mb-16">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={handleKeyDown}
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

        {error && (
          <p className="text-red-400 mb-8" role="alert">
            {error}
          </p>
        )}

        {data && (
          <Card className="overflow-x-auto text-left">
            <h2 className="text-xl font-semibold text-zinc-300 mb-4">
              5-Year Financial Metrics
            </h2>
            <p className="text-sm text-zinc-500 mb-4">
              {data.ticker} · {data.rows.length} metrics · source {data.source || "api"}
            </p>
            <DataTable headers={headers} rows={rows} />
          </Card>
        )}

        <p className="mt-12 text-zinc-500 text-lg">
          Last 5 years of 10-K metrics. No login. No ads. No bloat.
        </p>
      </div>
    </main>
  );
}
