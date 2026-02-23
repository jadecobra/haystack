'use client';

import { useState, useEffect } from 'react';
import { Card, DataTable, Sparkline } from './components';
import { cn } from './utils/cn';

export default function Home() {
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);

  const handleSearch = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    try {
      const response = await fetch(`/api/analyze/${ticker.toUpperCase().trim()}`);
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const kpiData = [
    { name: 'Revenue', value: data?.revenue?.growth || 0, change: data?.revenue?.change || 0 },
    { name: 'Net Income', value: data?.netIncome?.growth || 0, change: data?.netIncome?.change || 0 },
    { name: 'EPS', value: data?.eps?.growth || 0, change: data?.eps?.change || 0 },
    { name: 'FCF', value: data?.fcf?.growth || 0, change: data?.fcf?.change || 0 },
  ];

  const sparklineData = [
    { name: '2019', value: 100 },
    { name: '2020', value: 120 },
    { name: '2021', value: 150 },
    { name: '2022', value: 180 },
    { name: '2023', value: 200 },
  ];

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

        {data && (
          <div className="space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {kpiData.map((kpi, index) => (
                <Card key={index} className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-zinc-300">
                      {kpi.name}
                    </h3>
                    <span
                      className={cn(
                        "px-2 py-1 rounded-full text-xs font-medium",
                        kpi.change > 0
                          ? "bg-green-500 text-white"
                          : "bg-red-500 text-white"
                      )}
                    >
                      {kpi.change > 0 ? '+' : ''}
                      {kpi.change}%
                    </span>
                  </div>
                  <div className="text-3xl font-bold text-zinc-100">
                    {kpi.value}%
                  </div>
                  <Sparkline data={sparklineData} />
                </Card>
              ))}
            </div>

            <Card className="overflow-x-auto">
              <h2 className="text-xl font-semibold text-zinc-300 mb-4">
                5-Year Financial Metrics
              </h2>
              <DataTable
                headers={['Year', 'Revenue', 'Net Income', 'EPS', 'FCF']}
                rows={[
                  ['2023', '$200B', '$50B', '$5.00', '$30B'],
                  ['2022', '$180B', '$45B', '$4.50', '$28B'],
                  ['2021', '$150B', '$40B', '$4.00', '$25B'],
                  ['2020', '$120B', '$35B', '$3.50', '$22B'],
                  ['2019', '$100B', '$30B', '$3.00', '$20B'],
                ]}
              />
            </Card>
          </div>
        )}

        <p className="mt-12 text-zinc-500 text-lg">
          Last 5 years of 10-K metrics. No login. No ads. No bloat.
        </p>
      </div>
    </main>
  );
}
