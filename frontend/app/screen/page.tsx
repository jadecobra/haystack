"use client";

import { Card, DataTable, PageShell, TextLink } from "../components";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useElapsedMs } from "../hooks/use-elapsed-ms";
import { formatBuiltLabel } from "@/lib/formatBuilt";
import { parseSicQuery, sicForTicker, sicIndustryName } from "@/lib/screenSic";
import {
  indexLabel,
  parseScreenIndex,
  parseSectorSnapshot,
  sliceSnapshotByIndex,
  type ScreenIndex,
  type SectorSnapshot,
} from "@/lib/sectorTable";
import { listUnranked } from "@/lib/unranked";

const WAIT_STATUS = "Working…";
const SKELETON_ROW_COUNT = 12;
const BASE_HEADERS = ["Rank", "Ticker", "Name", "OE yield", "OE / share", "Prior close", "FY"];
const INDEX_OPTIONS: ScreenIndex[] = ["sp500", "sp400", "sp600", "sp1500"];

type ScreenSlug = "sp500-oe-yield" | "sp1500-oe-yield";
type CachedSnapshot = { snap: SectorSnapshot; raw: unknown };

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtPct(value: number | null): string {
  if (value === null) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function fmtMoney(value: number | null): string {
  if (value === null) return "—";
  return `$${value.toFixed(2)}`;
}

const DEFAULT_CAVEAT =
  "Trailing annual owner earnings per share divided by prior close — not live, not a growth screen.";

function skeletonRows(columnCount: number): Array<{ kind: "data"; cells: ReactNode[] }> {
  const dash = Array.from({ length: columnCount }, () => "—");
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
  const sectorFilter = searchParams.get("sector");
  const sicFilter = parseSicQuery(searchParams.get("sic"));
  const rawIndex = searchParams.get("index");
  const activeIndex: ScreenIndex =
    rawIndex !== null
      ? parseScreenIndex(rawIndex)
      : sicFilter != null
        ? "sp1500"
        : "sp500";

  const [cache, setCache] = useState<Partial<Record<ScreenSlug, CachedSnapshot>>>({});
  const [errors, setErrors] = useState<Partial<Record<ScreenSlug, string>>>({});

  const neededSlug: ScreenSlug =
    activeIndex === "sp500" && !cache["sp1500-oe-yield"]
      ? "sp500-oe-yield"
      : "sp1500-oe-yield";
  const cachedEntry = cache[neededSlug];
  const loadError = errors[neededSlug] ?? null;
  const waiting = !cachedEntry && !loadError;
  const elapsedMs = useElapsedMs(waiting);

  useEffect(() => {
    void fetch("/api/contract", { cache: "no-store" }).catch(() => {});
  }, []);

  useEffect(() => {
    if (cachedEntry || loadError) return;
    let cancelled = false;

    void (async () => {
      try {
        const response = await fetch(`/api/screen/${neededSlug}`, {
          cache: "no-store",
        });
        const json: unknown = await response.json();
        const parsed = parseSectorSnapshot(json);
        if (cancelled) return;
        if (!parsed || parsed.rows.filter((r) => r.price != null).length === 0) {
          setErrors((prev) => ({
            ...prev,
            [neededSlug]: "Screen snapshot is empty.",
          }));
          return;
        }
        setCache((prev) => ({
          ...prev,
          [neededSlug]: { snap: parsed, raw: json },
        }));
      } catch {
        if (cancelled) return;
        setErrors((prev) => ({
          ...prev,
          [neededSlug]: `Could not load the ${indexLabel(activeIndex)} screen.`,
        }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [neededSlug, cachedEntry, loadError, activeIndex]);

  const data = cachedEntry ? sliceSnapshotByIndex(cachedEntry.snap, activeIndex) : null;
  const sicName =
    sicFilter == null
      ? null
      : (data?.sicNames?.[String(sicFilter)] ?? sicIndustryName(sicFilter));
  const pricedRows = data ? data.rows.filter((row) => row.price != null) : [];
  const shownRows = pricedRows
    .filter((row) => !debtNone || row.debt_state === "zero")
    .filter((row) => !sectorFilter || row.sector === sectorFilter)
    .filter((row) => sicFilter == null || (row.sic ?? sicForTicker(row.ticker)) === sicFilter);
  const filtered = debtNone || Boolean(sectorFilter) || sicFilter != null;
  const unknownExcluded = data
    ? pricedRows.length > 0
      ? pricedRows.filter((row) => row.debt_state === "unknown").length
      : (data.debtCoverage?.unknown ?? 0)
    : 0;
  const unrankedIndex =
    cachedEntry && cachedEntry.snap.universe !== activeIndex && activeIndex !== "sp1500"
      ? activeIndex
      : undefined;
  const unranked = cachedEntry ? listUnranked(cachedEntry.raw, unrankedIndex) : [];

  const selectIndex = (next: ScreenIndex) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "sp500" && sicFilter == null) {
      params.delete("index");
    } else {
      params.set("index", next);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const toggleDebt = () => {
    const params = new URLSearchParams(searchParams.toString());
    if (debtNone) params.delete("debt");
    else params.set("debt", "none");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const showIndexCol = activeIndex === "sp1500";
  const headers = showIndexCol ? [...BASE_HEADERS, "Index"] : BASE_HEADERS;

  const rows = shownRows.map((row, index) => {
    const cells: ReactNode[] = [
      String(index + 1),
      <Link
        key={row.ticker}
        href={`/${row.ticker}`}
        className="underline underline-offset-4 text-zinc-100 hover:text-white"
      >
        {row.ticker}
      </Link>,
      row.name ?? "—",
      <span key="oe-yield" data-testid="screen-oe-yield">
        {fmtPct(row.oe_yield)}
        {row.oe_yield != null && row.oe_basis_note ? (
          <span className="ml-1 text-xs text-zinc-500">{row.oe_basis_note}</span>
        ) : null}
      </span>,
      fmtMoney(row.oe_per_share ?? null),
      fmtMoney(row.price ?? null),
      String(row.fy ?? "—"),
    ];
    if (showIndexCol) {
      cells.push(row.index ? indexLabel(row.index) : "—");
    }
    return { kind: "data" as const, cells };
  });

  const showTable = waiting || data !== null;
  const heading =
    activeIndex === "sp500"
      ? "S&P 500 owner-earnings yield"
      : `${indexLabel(activeIndex)} owner-earnings yield`;

  return (
    <PageShell maxWidth="wide" textAlign="start">
      <p className="mb-6 text-sm text-zinc-500">
        <TextLink href="/">Back to LongMuch</TextLink>
      </p>
      <h1 className="text-3xl sm:text-5xl font-bold tracking-tighter mb-4">{heading}</h1>
      <div
        className="flex flex-wrap items-center gap-1.5 mb-4"
        role="group"
        aria-label="Index universe"
        data-testid="screen-index-toggle"
      >
        {INDEX_OPTIONS.map((idx) => (
          <button
            key={idx}
            type="button"
            aria-pressed={activeIndex === idx}
            data-testid={`screen-index-${idx}`}
            onClick={() => selectIndex(idx)}
            className={`text-sm rounded border px-2.5 py-1 ${
              activeIndex === idx
                ? "border-zinc-400 bg-zinc-800 text-zinc-100"
                : "border-zinc-600 text-zinc-300 hover:text-zinc-100"
            }`}
          >
            {indexLabel(idx)}
          </button>
        ))}
      </div>
      {data && !waiting ? (
        <p
          className="text-xl sm:text-3xl text-zinc-200 mb-3"
          data-testid="screen-as-of"
        >
          Prices as of {data.priceAsOf ?? "—"}
          <span className="block text-base sm:text-xl text-zinc-400 mt-1">
            {formatBuiltLabel(data.builtAt)}
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
                  {filtered
                    ? `${shownRows.length} of ${pricedRows.length} names`
                    : `${pricedRows.length} names`}
                  {` · ${indexLabel(activeIndex)} constituents (list may lag index changes)`}
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
          {sectorFilter ? (
            <p
              className="text-sm text-zinc-300 mb-3"
              data-testid="screen-sector-filter"
            >
              Sector: {sectorFilter} · <TextLink href="/screen">clear</TextLink>
              {sectorFilter === "Financials"
                ? " · Owner earnings fit banks and insurers poorly; Financials are left out of the No debt view."
                : ""}
            </p>
          ) : null}
          {sicFilter != null ? (
            <p className="text-sm text-zinc-300 mb-3" data-testid="screen-sic-filter">
              Industry: {sicName ?? `SIC ${sicFilter}`}
              {sicName ? ` (SIC ${sicFilter})` : ""} · <TextLink href="/screen">clear</TextLink>
            </p>
          ) : null}
          <DataTable
            headers={headers}
            rows={waiting ? skeletonRows(headers.length) : rows}
          />
        </Card>
      )}
      {data && !waiting && unranked.length > 0 ? (
        <section className="mt-8 text-left" data-testid="screen-unranked">
          <h2 className="text-lg font-semibold mb-3">Not ranked ({unranked.length})</h2>
          <ul className="space-y-2 text-sm text-zinc-300">
            {unranked.map((item) => (
              <li key={item.ticker} data-testid="screen-unranked-row">
                <Link
                  href={`/${item.ticker}`}
                  className="underline underline-offset-4 text-zinc-100 hover:text-white"
                >
                  {item.ticker}
                </Link>
                {item.name ? <span className="text-zinc-400"> {item.name}</span> : null}
                <span> — {item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
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
        <DataTable headers={BASE_HEADERS} rows={skeletonRows(BASE_HEADERS.length)} />
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
