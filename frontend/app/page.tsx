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
        <h1 className="text-8xl font-bold tracking-tighter mb-6">LongMuch</h1>
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
