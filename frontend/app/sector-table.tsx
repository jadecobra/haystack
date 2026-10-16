"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DataTable } from "./components";
import {
  DEBT_CELL_INDEX,
  SECTOR_TABLE_HEADERS,
  debtCell,
  groupCountNote,
  groupForTicker,
  groupHeading,
  parseSectorRow,
  resolveSlug,
  sectorCells,
  sortPeerRows,
  type PeerSortKey,
  sectorHref,
  type SectorGroup,
  type SectorRow,
} from "@/lib/sectorTable";

type Snapshot = { rows: SectorRow[]; builtAt: string | null; priceAsOf: string | null };

async function loadSnapshot(): Promise<Snapshot | null> {
  try {
    const res = await fetch("/api/screen/sp500-oe-yield", { cache: "no-store" });
    const json: unknown = await res.json();
    if (typeof json !== "object" || json === null) return null;
    const body = json as Record<string, unknown>;
    if (!Array.isArray(body.rows)) return null;
    const rows = body.rows.map(parseSectorRow).filter((r): r is SectorRow => r !== null);
    return {
      rows,
      builtAt: typeof body.built_at === "string" ? body.built_at : null,
      priceAsOf: typeof body.price_as_of === "string" ? body.price_as_of : null,
    };
  } catch {
    return null;
  }
}

export type SectorTableProps =
  | { kind: "ticker"; ticker: string; subIndustry: string | null; sector: string | null }
  | { kind: "slug"; slug: string };

export function SectorTable(props: SectorTableProps) {
  const [snap, setSnap] = useState<Snapshot | null | undefined>(undefined);
  const [sortKey, setSortKey] = useState<PeerSortKey>("oe_yield");
  useEffect(() => {
    let cancelled = false;
    void loadSnapshot().then((s) => {
      if (!cancelled) setSnap(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (snap === undefined) {
    return props.kind === "slug" ? (
      <p className="text-zinc-400" data-testid="sector-table-loading">Working…</p>
    ) : null;
  }
  const group: SectorGroup | null = snap
    ? props.kind === "ticker"
      ? groupForTicker(snap.rows, props.ticker, props.subIndustry, props.sector)
      : resolveSlug(snap.rows, props.slug)
    : null;
  if (!group || group.rows.length === 0) {
    return props.kind === "slug" ? (
      <p className="text-danger" role="alert" data-testid="sector-table-missing">
        No S&P 500 sector or sub-industry matches this page.
      </p>
    ) : null;
  }
  const current = props.kind === "ticker" ? props.ticker.toUpperCase() : null;
  const shown = sortPeerRows(group.rows, sortKey);
  const headers = SECTOR_TABLE_HEADERS.map((header) => {
    const key = header === "OE yield" ? "oe_yield" : header === "NI margin" ? "ni_margin" : null;
    if (!key) return header;
    const active = sortKey === key;
    return (
      <button
        key={header}
        type="button"
        onClick={() => setSortKey(key)}
        className={active ? "text-white" : "hover:text-white"}
      >
        {header}
      </button>
    );
  });
  const rows = shown.map((row) => ({
    kind: "data" as const,
    cells: [
      <Link
        key={row.ticker}
        href={`/${row.ticker}`}
        data-testid="sector-row-link"
        aria-current={row.ticker === current ? "true" : undefined}
        className={`underline underline-offset-4 hover:text-white ${
          row.ticker === current ? "font-bold text-white" : "text-zinc-200"
        }`}
      >
        {row.ticker}
      </Link>,
      ...sectorCells(row).map((text, i) => {
        if (i !== DEBT_CELL_INDEX) return text;
        const { title } = debtCell(row);
        return (
          <span
            key="de"
            data-testid="sector-de"
            title={title ?? undefined}
            className={title ? "cursor-help underline decoration-dotted underline-offset-4" : undefined}
          >
            {text}
          </span>
        );
      }),
    ],
  }));
  const widen =
    group.level === "sub_industry" && group.sector ? (
      <Link
        href={sectorHref(group.sector)}
        data-testid="sector-widen-link"
        className="underline underline-offset-4 text-zinc-300 hover:text-white"
      >
        Widen to {group.sector}
      </Link>
    ) : null;
  const page =
    props.kind === "ticker" ? (
      <Link
        href={sectorHref(group.name)}
        data-testid="sector-page-link"
        className="underline underline-offset-4 text-zinc-300 hover:text-white"
      >
        Open table
      </Link>
    ) : null;

  return (
    <section className="mt-6 text-left" data-testid="sector-table" data-level={group.level}>
      <h3 className="text-base sm:text-lg text-zinc-300 mb-1" data-testid="sector-table-heading">
        {groupHeading(group)}
      </h3>
      <p className="text-sm text-zinc-500 mb-2" data-testid="sector-table-note">
        {groupCountNote(group)}
        {snap?.priceAsOf ? ` · daily snapshot, prices as of ${snap.priceAsOf}` : " · daily snapshot"}
        {page ? <> · {page}</> : null}
        {widen ? <> · {widen}</> : null}
      </p>
      {current && !group.rows.some((r) => r.ticker === current) && snap?.rows.every((r) => r.ticker !== current) ? (
        <p className="text-sm text-zinc-500 mb-2" data-testid="sector-table-own-missing">
          {current} is not in the snapshot: no SEC annual facts or no price for it.
        </p>
      ) : null}
      <DataTable headers={headers} rows={rows} />
    </section>
  );
}
