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
  treasury_dgs30_pct?: number | null;
  treasury_dgs30_as_of?: string | null;
  previous_close?: number | null;
  previous_close_as_of?: string | null;
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

  const dgs30Line =
    data &&
    data.treasury_dgs30_pct != null &&
    data.treasury_dgs30_as_of
      ? `30Y Treasury (DGS30): ${Number(data.treasury_dgs30_pct).toFixed(2)}% as of ${data.treasury_dgs30_as_of}`
      : null;

  const previousCloseLine =
    data && data.previous_close != null
      ? `Previous close: $${Number(data.previous_close).toFixed(2)}${
          data.previous_close_as_of ? ` as of ${data.previous_close_as_of}` : ""
        }`
      : null;

  return (
    <main className="min-h-screen bg-zinc-950 text-white flex items-start sm:items-center justify-center overflow-x-hidden">
      <div className="w-full max-w-7xl mx-auto text-center px-4 sm:px-6 py-10 sm:py-16">
        <h1 className="text-4xl sm:text-6xl md:text-8xl font-bold tracking-tighter mb-3 sm:mb-6">
          LongMuch
        </h1>
        <p className="text-lg sm:text-2xl md:text-3xl text-zinc-400 mb-8 sm:mb-16">
          Clean. Instant. Fundamental analysis.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full max-w-4xl mx-auto mb-8 sm:mb-16">
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="AAPL or TSLA"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            className="w-full sm:flex-1 min-w-0 bg-zinc-900 border border-zinc-700 rounded-2xl sm:rounded-3xl px-4 sm:px-8 py-3.5 sm:py-5 text-lg sm:text-2xl focus:outline-none focus:border-white placeholder-zinc-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading || !ticker.trim()}
            className="w-full sm:w-auto bg-white hover:bg-zinc-100 text-black px-6 sm:px-12 py-3.5 sm:py-5 rounded-2xl sm:rounded-3xl font-semibold text-base sm:text-xl transition-all disabled:opacity-50 flex items-center justify-center sm:min-w-[160px] shrink-0"
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
          <Card className="overflow-hidden text-left p-4 sm:p-6">
            <h2 className="text-lg sm:text-xl font-semibold text-zinc-300 mb-3 sm:mb-4">
              5-Year Financial Metrics
            </h2>
            <p className="text-xs sm:text-sm text-zinc-500 mb-2 break-words">
              {data.ticker} · {data.rows.length} metrics · source {data.source || "api"}
            </p>
            {previousCloseLine ? (
              <p className="text-2xl sm:text-3xl font-semibold text-white mb-3" data-testid="previous-close">
                {previousCloseLine}
              </p>
            ) : null}
            {dgs30Line ? (
              <p className="text-sm text-zinc-500 mb-4" data-testid="dgs30-as-of">
                {dgs30Line}
              </p>
            ) : (
              <div className="mb-4" />
            )}
            <DataTable headers={headers} rows={rows} />
          </Card>
        )}

        <p className="mt-8 sm:mt-12 text-zinc-500 text-sm sm:text-lg px-1">
          Last 5 years of 10-K metrics. No login. No ads. No bloat.
        </p>
      </div>
    </main>
  );
}
