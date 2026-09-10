'use client';

import { Button, Card, DataTable, Input, PageShell, TextLink } from './components';

import { useState, type KeyboardEvent, type ReactNode } from 'react';

type MetricRow = {
  metric: string;
  values: Record<string, string>;
  raw?: Record<string, number | null>;
};

type MetricGroup = {
  id: string;
  title: string;
  labels: string[];
};

type Analysis = {
  ticker: string;
  years: string[];
  rows: MetricRow[];
  source?: string;
  status?: string;
  message?: string;
  error?: string;
  treasury_label?: string;
  treasury_dgs30_pct?: number | null;
  treasury_dgs30_as_of?: string | null;
  previous_close?: number | null;
  previous_close_as_of?: string | null;
  groups?: MetricGroup[];
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

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const dgs30Line =
    data &&
    data.treasury_dgs30_pct != null &&
    data.treasury_dgs30_as_of
      ? `30Y Treasury (DGS30): ${Number(data.treasury_dgs30_pct).toFixed(2)}% as of ${data.treasury_dgs30_as_of}`
      : null;

  const treasuryLabel = data?.treasury_label;
  const headers = data ? ['Metric', ...data.years] : [];

  const metricCells = (row: MetricRow, years: string[]) => {
    const metricLabel =
      treasuryLabel && row.metric === treasuryLabel && dgs30Line ? (
        <>
          <div>{treasuryLabel}</div>
          <div
            className="text-xs text-zinc-500 font-normal mt-0.5 whitespace-normal"
            data-testid="dgs30-as-of"
          >
            {dgs30Line}
          </div>
        </>
      ) : (
        row.metric
      );
    return [metricLabel, ...years.map((y) => row.values[y] ?? "—")];
  };

  const rows = data
    ? (() => {
        const byMetric = new Map(data.rows.map((row) => [row.metric, row]));
        const groups = data.groups?.length
          ? data.groups
          : [{ id: "all", title: "", labels: data.rows.map((r) => r.metric) }];
        const tableRows: Array<
          | { kind: "group"; title: string }
          | { kind: "data"; cells: ReactNode[] }
        > = [];
        for (const group of groups) {
          if (group.title) {
            tableRows.push({ kind: "group", title: group.title });
          }
          for (const label of group.labels) {
            const row = byMetric.get(label);
            if (!row) continue;
            tableRows.push({ kind: "data", cells: metricCells(row, data.years) });
          }
        }
        return tableRows;
      })()
    : [];

  const sourceLabel = (data?.source || "api").toUpperCase();

  return (
    <PageShell maxWidth="wide" centerViewport textAlign="center">
      <h1 className="text-4xl sm:text-6xl md:text-8xl font-bold tracking-tighter mb-3 sm:mb-6">
        LongMuch
      </h1>
      <p className="text-lg sm:text-2xl md:text-3xl text-muted mb-8 sm:mb-16">
        Fundamental Analysis to answer two questions - How much? How long?
      </p>

      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full max-w-4xl mx-auto mb-8 sm:mb-16">
        <Input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="enter stock ticker e.g. AAPL"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
        />
        <Button
          onClick={handleSearch}
          disabled={loading || !ticker.trim()}
        >
          {loading ? "Analyzing..." : "Analyze"}
        </Button>
      </div>

      {error && (
        <p className="text-danger mb-8" role="alert">
          {error}
        </p>
      )}

      {data && (
        <Card variant="raised" className="overflow-hidden text-left">
          {data.previous_close != null ? (
            <p
              className="text-lg sm:text-xl text-zinc-300 mb-1"
              data-testid="previous-close"
            >
              Previous close{" "}
              <span className="font-semibold">
                ${Number(data.previous_close).toFixed(2)}
              </span>
              {data.previous_close_as_of
                ? ` as of ${data.previous_close_as_of}`
                : ""}
            </p>
          ) : null}
          <h2 className="text-lg sm:text-xl text-zinc-300 mb-4 break-words">
            {data.ticker} 5-Year Financial Metrics | source : {sourceLabel}
          </h2>
          <DataTable headers={headers} rows={rows} />
        </Card>
      )}

      <p className="mt-8 sm:mt-12 text-muted-2 text-sm sm:text-lg px-1">
        Last 5 years of 10-K metrics. No login. No ads. No bloat.
      </p>
      <p className="mt-3 text-muted-2 text-sm sm:text-base px-1">
        <TextLink href="/docs">
          How metrics are calculated
        </TextLink>
      </p>
    </PageShell>
  );
}
