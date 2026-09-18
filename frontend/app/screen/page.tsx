"use client";

import { Card, DataTable, PageShell, TextLink } from "../components";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

const WAIT_STATUS = "Working…";
const SKELETON_ROW_COUNT = 12;
const HEADERS = ["Rank", "Ticker", "Name", "OE yield", "OE / share", "Prior close", "FY"];

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

type ScreenRow = {
  ticker: string;
  name: string | null;
  oe_yield: number;
  oe_per_share: number;
  price: number;
  fy: number;
  price_as_of: string | null;
};

type ScreenPayload = {
  universe: string;
  count: number;
  skipped?: number;
  built_at: string | null;
  price_as_of: string | null;
  stale?: boolean;
  error?: string | null;
  caveat?: string;
  rows: ScreenRow[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseRow(value: unknown): ScreenRow | null {
  if (!isRecord(value)) return null;
  if (typeof value.ticker !== "string") return null;
  if (typeof value.oe_yield !== "number") return null;
  if (typeof value.oe_per_share !== "number") return null;
  if (typeof value.price !== "number") return null;
  if (typeof value.fy !== "number") return null;
  return {
    ticker: value.ticker.toUpperCase(),
    name: typeof value.name === "string" ? value.name : null,
    oe_yield: value.oe_yield,
    oe_per_share: value.oe_per_share,
    price: value.price,
    fy: value.fy,
    price_as_of: typeof value.price_as_of === "string" ? value.price_as_of : null,
  };
}

function parsePayload(value: unknown): ScreenPayload | null {
  if (!isRecord(value)) return null;
  if (!Array.isArray(value.rows)) return null;
  const rows: ScreenRow[] = [];
  for (const row of value.rows) {
    const parsed = parseRow(row);
    if (parsed) rows.push(parsed);
  }
  return {
    universe: typeof value.universe === "string" ? value.universe : "sp500",
    count: typeof value.count === "number" ? value.count : rows.length,
    skipped: typeof value.skipped === "number" ? value.skipped : undefined,
    built_at: typeof value.built_at === "string" ? value.built_at : null,
    price_as_of: typeof value.price_as_of === "string" ? value.price_as_of : null,
    stale: value.stale === true,
    error: typeof value.error === "string" ? value.error : null,
    caveat: typeof value.caveat === "string" ? value.caveat : undefined,
    rows,
  };
}

function fmtPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function fmtMoney(value: number): string {
  return `$${value.toFixed(2)}`;
}

const DEFAULT_CAVEAT =
  "Trailing annual owner earnings per share divided by prior close — not live, not a growth screen.";

function skeletonRows(): Array<{ kind: "data"; cells: ReactNode[] }> {
  const dash = Array.from({ length: HEADERS.length }, () => "—");
  return Array.from({ length: SKELETON_ROW_COUNT }, () => ({
    kind: "data" as const,
    cells: dash,
  }));
}

export default function ScreenPage() {
  const [data, setData] = useState<ScreenPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(true);
  const [elapsedMs, setElapsedMs] = useState(0);
  const elapsedTimerRef = useRef<number | null>(null);

  useEffect(() => {
    void fetch("/api/contract", { cache: "no-store" }).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();
    setWaiting(true);
    setElapsedMs(0);
    elapsedTimerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 100);

    const stopClock = () => {
      if (elapsedTimerRef.current != null) {
        window.clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    };

    void (async () => {
      try {
        const response = await fetch("/api/screen/sp500-oe-yield", {
          cache: "no-store",
        });
        const json: unknown = await response.json();
        const parsed = parsePayload(json);
        if (cancelled) return;
        stopClock();
        setWaiting(false);
        if (!parsed || parsed.rows.length === 0) {
          setLoadError("Screen snapshot is empty.");
          return;
        }
        setData(parsed);
      } catch {
        if (cancelled) return;
        stopClock();
        setWaiting(false);
        setLoadError("Could not load the S&P 500 screen.");
      }
    })();
    return () => {
      cancelled = true;
      stopClock();
    };
  }, []);

  const rows =
    data?.rows.map((row, index) => ({
      kind: "data" as const,
      cells: [
        String(index + 1),
        <Link
          key={row.ticker}
          href={`/${row.ticker}`}
          className="underline underline-offset-4 text-zinc-100 hover:text-white"
        >
          {row.ticker}
        </Link>,
        row.name ?? "—",
        fmtPct(row.oe_yield),
        fmtMoney(row.oe_per_share),
        fmtMoney(row.price),
        String(row.fy),
      ],
    })) ?? skeletonRows();

  const showTable = waiting || data !== null;

  return (
    <PageShell maxWidth="wide" textAlign="start">
      <p className="mb-6 text-sm text-zinc-500">
        <TextLink href="/">Back to LongMuch</TextLink>
      </p>
      <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">
        S&P 500 owner-earnings yield
      </h1>
      {data && !waiting ? (
        <p
          className="text-xl sm:text-3xl text-zinc-200 mb-3"
          data-testid="screen-as-of"
        >
          Prices as of {data.price_as_of ?? "—"}
          <span className="block text-base sm:text-xl text-zinc-400 mt-1">
            Built {data.built_at ?? "—"}
          </span>
        </p>
      ) : waiting ? (
        <p
          className="text-sm sm:text-base text-zinc-400 mb-3"
          data-testid="screen-wait-status"
          aria-live="polite"
        >
          {WAIT_STATUS}{" "}
          <span data-testid="screen-wait-elapsed">{formatElapsed(elapsedMs)}</span>
        </p>
      ) : null}
      <p className="text-zinc-400 mb-6 text-sm sm:text-base">
        {data?.caveat ?? DEFAULT_CAVEAT}
      </p>
      {!waiting && (data?.stale || data?.error || loadError) && (
        <p className="text-danger mb-6" role="alert">
          {loadError ||
            (data?.stale
              ? `Stale snapshot. ${data.error ?? ""}`.trim()
              : data?.error)}
        </p>
      )}
      {showTable && (
        <Card variant="raised" className="overflow-hidden text-left">
          {data && !waiting ? (
            <p className="text-sm text-zinc-400 mb-3">
              {data.count} names · S&P 500 constituents (list may lag index changes)
              {typeof data.skipped === "number" && data.skipped > 0
                ? ` · ${data.skipped} skipped`
                : ""}
            </p>
          ) : null}
          <DataTable headers={HEADERS} rows={waiting ? skeletonRows() : rows} />
        </Card>
      )}
    </PageShell>
  );
}
