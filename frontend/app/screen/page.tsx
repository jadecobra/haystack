"use client";

import { Card, DataTable, PageShell, TextLink } from "../components";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { formatBuiltLabel } from "@/lib/formatBuilt";

const WAIT_STATUS = "Working…";
const SKELETON_ROW_COUNT = 12;
const HEADERS = ["Rank", "Ticker", "Name", "OE yield", "OE / share", "Prior close", "FY"];

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

type DebtState = "zero" | "positive" | "unknown" | "n/a";

type DebtCoverage = {
  zero: number;
  positive: number;
  unknown: number;
  "n/a": number;
  unknown_tickers: string[];
};

type ScreenRow = {
  ticker: string;
  name: string | null;
  oe_yield: number;
  oe_per_share: number;
  price: number;
  fy: number;
  price_as_of: string | null;
  debt: number | null;
  debt_state: DebtState;
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
  meta?: { debt_coverage?: DebtCoverage };
};

function parseDebtState(value: unknown): DebtState {
  if (value === "zero" || value === "positive" || value === "unknown" || value === "n/a") {
    return value;
  }
  return "unknown";
}

function parseDebt(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

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
    debt: parseDebt(value.debt),
    debt_state: parseDebtState(value.debt_state),
  };
}

function parseCoverage(value: unknown): DebtCoverage | undefined {
  if (!isRecord(value)) return undefined;
  const num = (key: string) => (typeof value[key] === "number" ? value[key] : 0);
  const tickers = Array.isArray(value.unknown_tickers)
    ? value.unknown_tickers.filter((item): item is string => typeof item === "string")
    : [];
  return {
    zero: num("zero"),
    positive: num("positive"),
    unknown: num("unknown"),
    "n/a": num("n/a"),
    unknown_tickers: tickers,
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
    meta: isRecord(value.meta)
      ? { debt_coverage: parseCoverage(value.meta.debt_coverage) }
      : undefined,
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

function ScreenPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const debtNone = searchParams.get("debt") === "none";
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
    // waiting=true / elapsedMs=0 are the initial state; no sync setState here.
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

  const shownRows = data
    ? debtNone
      ? data.rows.filter((row) => row.debt_state === "zero")
      : data.rows
    : [];
  const unknownExcluded = data
    ? data.rows.length > 0
      ? data.rows.filter((row) => row.debt_state === "unknown").length
      : (data.meta?.debt_coverage?.unknown ?? 0)
    : 0;

  const toggleDebt = () => {
    const params = new URLSearchParams(searchParams.toString());
    if (debtNone) params.delete("debt");
    else params.set("debt", "none");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const rows =
    shownRows.map((row, index) => ({
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
            {formatBuiltLabel(data.built_at)}
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
            <div className="mb-3">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-zinc-400">
                  {debtNone
                    ? `${shownRows.length} of ${data.count} names`
                    : `${data.count} names`}
                  {" · S&P 500 constituents (list may lag index changes)"}
                  {typeof data.skipped === "number" && data.skipped > 0
                    ? ` · ${data.skipped} skipped`
                    : ""}
                </p>
                <button
                  type="button"
                  aria-pressed={debtNone}
                  data-testid="screen-debt-toggle"
                  onClick={toggleDebt}
                  className={`text-sm rounded border px-2 py-1 ${
                    debtNone
                      ? "border-zinc-400 bg-zinc-800 text-zinc-100"
                      : "border-zinc-600 text-zinc-300 hover:text-zinc-100"
                  }`}
                >
                  No debt
                </button>
              </div>
              {debtNone ? (
                <p
                  className="text-sm text-zinc-500 mt-2"
                  data-testid="screen-debt-caveat"
                >
                  debt-free per reported XBRL; {unknownExcluded} unknown excluded; financials excluded
                </p>
              ) : null}
            </div>
          ) : null}
          <DataTable headers={HEADERS} rows={waiting ? skeletonRows() : rows} />
        </Card>
      )}
    </PageShell>
  );
}

function ScreenFallback() {
  return (
    <PageShell maxWidth="wide" textAlign="start">
      <p className="mb-6 text-sm text-zinc-500">
        <TextLink href="/">Back to LongMuch</TextLink>
      </p>
      <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">
        S&P 500 owner-earnings yield
      </h1>
      <p
        className="text-sm sm:text-base text-zinc-400 mb-3"
        data-testid="screen-wait-status"
        aria-live="polite"
      >
        {WAIT_STATUS}{" "}
        <span data-testid="screen-wait-elapsed">{formatElapsed(0)}</span>
      </p>
      <p className="text-zinc-400 mb-6 text-sm sm:text-base">{DEFAULT_CAVEAT}</p>
      <Card variant="raised" className="overflow-hidden text-left">
        <DataTable headers={HEADERS} rows={skeletonRows()} />
      </Card>
    </PageShell>
  );
}

export default function ScreenPage() {
  return (
    <Suspense fallback={<ScreenFallback />}>
      <ScreenPageInner />
    </Suspense>
  );
}
