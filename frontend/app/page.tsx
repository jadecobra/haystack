'use client';

import { Button, Card, DataTable, Input, PageShell, TextLink } from './components';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { flushSync } from 'react-dom';

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

type WaitStage = 'Looking up company…' | 'Loading filings…' | 'Building table…';

type SkeletonSpec = { groups: MetricGroup[]; years: string[] };

type View =
  | { kind: 'idle' }
  | {
      kind: 'waiting';
      ticker: string;
      startedAt: number;
      stage: WaitStage;
      skeleton: SkeletonSpec;
    }
  | { kind: 'ready'; data: Analysis }
  | { kind: 'error'; message: string };

type ContractPayload = {
  schema_version: string;
  labels: string[];
  row_count: number;
  treasury_label: string;
  groups: MetricGroup[];
};

const PLACEHOLDER_YEARS = ['…', '…', '…', '…', '…'] as const;
const STAGE_ORDER: WaitStage[] = [
  'Looking up company…',
  'Loading filings…',
  'Building table…',
];
const STAGE_AT_MS = [0, 1200, 3500] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseMetricGroup(value: unknown): MetricGroup | null {
  if (!isRecord(value)) return null;
  const { id, title, labels } = value;
  if (typeof id !== 'string' || typeof title !== 'string') return null;
  if (!Array.isArray(labels) || !labels.every((label) => typeof label === 'string')) {
    return null;
  }
  return { id, title, labels };
}

function parseContract(value: unknown): ContractPayload | null {
  if (!isRecord(value)) return null;
  if (typeof value.schema_version !== 'string') return null;
  if (!Array.isArray(value.labels) || !value.labels.every((l) => typeof l === 'string')) {
    return null;
  }
  if (typeof value.row_count !== 'number') return null;
  if (typeof value.treasury_label !== 'string') return null;
  if (!Array.isArray(value.groups)) return null;
  const groups: MetricGroup[] = [];
  for (const group of value.groups) {
    const parsed = parseMetricGroup(group);
    if (!parsed) return null;
    groups.push(parsed);
  }
  return {
    schema_version: value.schema_version,
    labels: value.labels,
    row_count: value.row_count,
    treasury_label: value.treasury_label,
    groups,
  };
}

function parseAnalysis(value: unknown): Analysis | null {
  if (!isRecord(value)) return null;
  if (typeof value.ticker !== 'string') return null;
  if (!Array.isArray(value.years) || !value.years.every((y) => typeof y === 'string')) {
    return null;
  }
  if (!Array.isArray(value.rows)) return null;
  const rows: MetricRow[] = [];
  for (const row of value.rows) {
    if (!isRecord(row) || typeof row.metric !== 'string' || !isRecord(row.values)) {
      return null;
    }
    const values: Record<string, string> = {};
    for (const [key, cell] of Object.entries(row.values)) {
      if (typeof cell !== 'string') return null;
      values[key] = cell;
    }
    rows.push({ metric: row.metric, values });
  }
  let groups: MetricGroup[] | undefined;
  if (Array.isArray(value.groups)) {
    groups = [];
    for (const group of value.groups) {
      const parsed = parseMetricGroup(group);
      if (!parsed) return null;
      groups.push(parsed);
    }
  }
  const optionalNumber = (field: unknown): number | null | undefined => {
    if (field === undefined) return undefined;
    if (field === null || typeof field === 'number') return field;
    return undefined;
  };
  const optionalString = (field: unknown): string | null | undefined => {
    if (field === undefined) return undefined;
    if (field === null || typeof field === 'string') return field;
    return undefined;
  };

  return {
    ticker: value.ticker,
    years: value.years,
    rows,
    source: typeof value.source === 'string' ? value.source : undefined,
    status: typeof value.status === 'string' ? value.status : undefined,
    message: typeof value.message === 'string' ? value.message : undefined,
    error: typeof value.error === 'string' ? value.error : undefined,
    treasury_label:
      typeof value.treasury_label === 'string' ? value.treasury_label : undefined,
    treasury_dgs30_pct: optionalNumber(value.treasury_dgs30_pct),
    treasury_dgs30_as_of: optionalString(value.treasury_dgs30_as_of),
    previous_close: optionalNumber(value.previous_close),
    previous_close_as_of: optionalString(value.previous_close_as_of),
    groups,
  };
}

function buildTableRows(args: {
  groups: MetricGroup[];
  years: string[];
  rows: MetricRow[] | null;
  treasuryLabel?: string;
  dgs30Line?: string | null;
}): Array<{ kind: 'group'; title: string } | { kind: 'data'; cells: ReactNode[] }> {
  const { groups, years, rows, treasuryLabel, dgs30Line } = args;
  const byMetric = rows ? new Map(rows.map((row) => [row.metric, row])) : null;
  const effectiveGroups =
    groups.length > 0
      ? groups
      : rows
        ? [{ id: 'all', title: '', labels: rows.map((r) => r.metric) }]
        : [];

  const tableRows: Array<
    | { kind: 'group'; title: string }
    | { kind: 'data'; cells: ReactNode[] }
  > = [];

  for (const group of effectiveGroups) {
    if (group.title) {
      tableRows.push({ kind: 'group', title: group.title });
    }
    for (const label of group.labels) {
      const row = byMetric?.get(label);
      const metricLabel =
        treasuryLabel &&
        dgs30Line &&
        row &&
        row.metric === treasuryLabel ? (
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
          label
        );
      const yearCells = years.map((year) =>
        row ? (row.values[year] ?? '—') : '—',
      );
      tableRows.push({ kind: 'data', cells: [metricLabel, ...yearCells] });
    }
  }
  return tableRows;
}

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function Home() {
  const [ticker, setTicker] = useState('');
  const [view, setView] = useState<View>({ kind: 'idle' });
  const [elapsedMs, setElapsedMs] = useState(0);

  const groupsCacheRef = useRef<MetricGroup[]>([]);
  const yearsCacheRef = useRef<string[]>([]);
  const contractPromiseRef = useRef<Promise<MetricGroup[]> | null>(null);
  const waitTimersRef = useRef<number[]>([]);
  const elapsedTimerRef = useRef<number | null>(null);
  const requestIdRef = useRef(0);

  const clearWaitTimers = useCallback(() => {
    for (const id of waitTimersRef.current) {
      window.clearTimeout(id);
    }
    waitTimersRef.current = [];
    if (elapsedTimerRef.current != null) {
      window.clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearWaitTimers(), [clearWaitTimers]);

  const loadContractGroups = useCallback((): Promise<MetricGroup[]> => {
    if (groupsCacheRef.current.length > 0) {
      return Promise.resolve(groupsCacheRef.current);
    }
    if (contractPromiseRef.current) {
      return contractPromiseRef.current;
    }
    const promise = fetch('/api/contract')
      .then(async (response) => {
        const raw: unknown = await response.json();
        if (!response.ok) {
          contractPromiseRef.current = null;
          return [] as MetricGroup[];
        }
        const contract = parseContract(raw);
        if (!contract) {
          contractPromiseRef.current = null;
          return [] as MetricGroup[];
        }
        groupsCacheRef.current = contract.groups;
        return contract.groups;
      })
      .catch(() => {
        contractPromiseRef.current = null;
        return [] as MetricGroup[];
      });
    contractPromiseRef.current = promise;
    return promise;
  }, []);

  useEffect(() => {
    void loadContractGroups();
  }, [loadContractGroups]);

  const startWaitChrome = useCallback(
    (symbol: string) => {
      clearWaitTimers();
      const startedAt = Date.now();
      const skeleton: SkeletonSpec = {
        groups: groupsCacheRef.current,
        years:
          yearsCacheRef.current.length > 0
            ? yearsCacheRef.current
            : [...PLACEHOLDER_YEARS],
      };
      setElapsedMs(0);
      flushSync(() => {
        setView({
          kind: 'waiting',
          ticker: symbol,
          startedAt,
          stage: STAGE_ORDER[0],
          skeleton,
        });
      });

      elapsedTimerRef.current = window.setInterval(() => {
        setElapsedMs(Date.now() - startedAt);
      }, 100);

      for (let i = 1; i < STAGE_ORDER.length; i += 1) {
        const stage = STAGE_ORDER[i];
        const delay = STAGE_AT_MS[i];
        const timerId = window.setTimeout(() => {
          setView((current) =>
            current.kind === 'waiting' && current.startedAt === startedAt
              ? { ...current, stage }
              : current,
          );
        }, delay);
        waitTimersRef.current.push(timerId);
      }

      void loadContractGroups().then((groups) => {
        if (groups.length === 0) return;
        setView((current) =>
          current.kind === 'waiting' && current.startedAt === startedAt
            ? {
                ...current,
                skeleton: { ...current.skeleton, groups },
              }
            : current,
        );
      });
    },
    [clearWaitTimers, loadContractGroups],
  );

  const handleSearch = async () => {
    const symbol = ticker.toUpperCase().trim();
    if (!symbol) return;

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    startWaitChrome(symbol);

    try {
      const response = await fetch(`/api/analyze/${symbol}`);
      const raw: unknown = await response.json();
      if (requestIdRef.current !== requestId) return;

      const result = parseAnalysis(raw);
      if (!response.ok) {
        clearWaitTimers();
        const message =
          (result && (result.error || result.message)) ||
          (isRecord(raw) && typeof raw.error === 'string' && raw.error) ||
          (isRecord(raw) && typeof raw.message === 'string' && raw.message) ||
          `Analyze failed (${response.status})`;
        setView({ kind: 'error', message });
        return;
      }
      if (!result || !result.rows.length || !result.years.length) {
        clearWaitTimers();
        setView({ kind: 'error', message: 'Backend returned no metric table' });
        return;
      }

      if (result.groups?.length) {
        groupsCacheRef.current = result.groups;
      }
      yearsCacheRef.current = result.years;
      clearWaitTimers();
      setView({ kind: 'ready', data: result });
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      console.error('Error fetching data:', err);
      clearWaitTimers();
      setView({ kind: 'error', message: 'Could not reach /api/analyze' });
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      void handleSearch();
    }
  };

  const waiting = view.kind === 'waiting';
  const ready = view.kind === 'ready' ? view.data : null;
  const errorMessage = view.kind === 'error' ? view.message : null;

  const displayGroups =
    view.kind === 'waiting'
      ? view.skeleton.groups
      : ready?.groups?.length
        ? ready.groups
        : groupsCacheRef.current;
  const displayYears =
    view.kind === 'waiting'
      ? view.skeleton.years
      : ready
        ? ready.years
        : [];

  const dgs30Line =
    ready &&
    ready.treasury_dgs30_pct != null &&
    ready.treasury_dgs30_as_of
      ? `30Y Treasury (DGS30): ${Number(ready.treasury_dgs30_pct).toFixed(2)}% as of ${ready.treasury_dgs30_as_of}`
      : null;

  const headers =
    view.kind === 'waiting' || view.kind === 'ready'
      ? ['Metric', ...displayYears]
      : [];

  const rows =
    view.kind === 'waiting' || view.kind === 'ready'
      ? buildTableRows({
          groups: displayGroups,
          years: displayYears,
          rows: ready?.rows ?? null,
          treasuryLabel: ready?.treasury_label,
          dgs30Line,
        })
      : [];

  const sourceLabel = (ready?.source || 'api').toUpperCase();
  const cardTicker =
    view.kind === 'waiting' ? view.ticker : ready ? ready.ticker : null;

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
          onClick={() => {
            void handleSearch();
          }}
          disabled={waiting || !ticker.trim()}
        >
          Analyze
        </Button>
      </div>

      {errorMessage && (
        <p className="text-danger mb-8" role="alert">
          {errorMessage}
        </p>
      )}

      {(view.kind === 'waiting' || view.kind === 'ready') && cardTicker && (
        <Card variant="raised" className="overflow-hidden text-left">
          {ready?.previous_close != null ? (
            <p
              className="text-lg sm:text-xl text-zinc-300 mb-1"
              data-testid="previous-close"
            >
              Previous close{' '}
              <span className="font-semibold">
                ${Number(ready.previous_close).toFixed(2)}
              </span>
              {ready.previous_close_as_of
                ? ` as of ${ready.previous_close_as_of}`
                : ''}
            </p>
          ) : null}
          <h2 className="text-lg sm:text-xl text-zinc-300 mb-4 break-words">
            {view.kind === 'waiting'
              ? `${cardTicker} 5-Year Financial Metrics`
              : `${cardTicker} 5-Year Financial Metrics | source : ${sourceLabel}`}
          </h2>
          {view.kind === 'waiting' && (
            <p
              className="text-sm sm:text-base text-zinc-400 mb-4"
              data-testid="analyze-wait-status"
              aria-live="polite"
            >
              {view.stage}{' '}
              <span data-testid="analyze-wait-elapsed">{formatElapsed(elapsedMs)}</span>
            </p>
          )}
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
