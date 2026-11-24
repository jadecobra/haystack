"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DataTable } from "./components";
import {
  DEBT_CELL_INDEX,
  OE_YIELD_CELL_INDEX,
  PRICE_CELL_INDEX,
  SECTOR_TABLE_HEADERS,
  debtCell,
  groupForTicker,
  indexLabel,
  parseSectorSnapshot,
  priceCell,
  resolveSlug,
  sectorCells,
  sectorHref,
  sectorOwnMissingNote,
  sectorTableHeading,
  sectorTableNote,
  sliceSnapshotByIndex,
  sortPeerRows,
  tickerIndex,
  type PeerSortKey,
  type SectorGroup,
  type SectorScope,
  type SectorSnapshot,
} from "@/lib/sectorTable";

async function loadSnapshot(): Promise<SectorSnapshot | null> {
  for (const slug of ["sp1500-oe-yield", "sp500-oe-yield"]) {
    try {
      const res = await fetch(`/api/screen/${slug}`, { cache: "no-store" });
      if (!res.ok) continue;
      const json: unknown = await res.json();
      const parsed = parseSectorSnapshot(json);
      if (parsed && parsed.rows.length > 0) return parsed;
    } catch {
      // Fall back to S&P 500 when the S&P 1500 snapshot is unavailable.
    }
  }
  return null;
}

export type SectorTableProps =
  | { kind: "ticker"; ticker: string; subIndustry: string | null; sector: string | null }
  | { kind: "slug"; slug: string; initialScope?: SectorScope };

export function SectorTable(props: SectorTableProps) {
  const [snap, setSnap] = useState<SectorSnapshot | null | undefined>(undefined);
  const [sortKey, setSortKey] = useState<PeerSortKey>("oe_yield");
  const [userScope, setUserScope] = useState<SectorScope | null>(null);

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

  const ownIndex = snap && props.kind === "ticker" ? tickerIndex(snap, props.ticker) : null;
  const detectedDefault: SectorScope =
    props.kind === "ticker"
      ? ownIndex === "sp400" || ownIndex === "sp600"
        ? "sp1500"
        : "sp500"
      : (props.initialScope ?? "sp500");
  const activeScope: SectorScope = userScope ?? detectedDefault;
  const hasSp1500 = snap?.universe === "sp1500";
  const effectiveScope: SectorScope = hasSp1500 ? activeScope : "sp500";
  const scopedSnap = snap ? sliceSnapshotByIndex(snap, effectiveScope) : null;

  const group: SectorGroup | null = scopedSnap
    ? props.kind === "ticker"
      ? groupForTicker(scopedSnap.rows, props.ticker, props.subIndustry, props.sector)
      : resolveSlug(scopedSnap.rows, props.slug)
    : null;

  const scopeToggle = hasSp1500 ? (
    <div
      className="flex items-center gap-1"
      role="group"
      aria-label="Peer universe"
      data-testid="sector-scope-toggle"
    >
      {(["sp500", "sp1500"] as const).map((scope) => (
        <button
          key={scope}
          type="button"
          aria-pressed={effectiveScope === scope}
          data-testid={`sector-scope-${scope}`}
          onClick={() => setUserScope(scope)}
          className={`text-xs rounded border px-2 py-0.5 ${
            effectiveScope === scope
              ? "border-zinc-400 bg-zinc-800 text-zinc-100"
              : "border-zinc-600 text-zinc-300 hover:text-zinc-100"
          }`}
        >
          {indexLabel(scope)}
        </button>
      ))}
    </div>
  ) : null;

  if (!group || group.rows.length === 0) {
    if (props.kind !== "slug") return null;
    return (
      <section className="mt-6 text-left">
        {scopeToggle ? <div className="mb-3">{scopeToggle}</div> : null}
        <p className="text-danger" role="alert" data-testid="sector-table-missing">
          No {indexLabel(effectiveScope)} sector or sub-industry matches this page.
        </p>
      </section>
    );
  }

  const current = props.kind === "ticker" ? props.ticker.toUpperCase() : null;
  const shown = sortPeerRows(group.rows, sortKey);
  const baseHeaders = SECTOR_TABLE_HEADERS.map((header) => {
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
  const headers = effectiveScope === "sp1500" ? [...baseHeaders, "Index"] : baseHeaders;

  const rows = shown.map((row) => {
    const cells = [
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
        if (i === OE_YIELD_CELL_INDEX) {
          return (
            <span key="oe-yield" data-testid="sector-oe-yield">
              {text}
              {row.oe_yield != null && row.oe_basis_note ? (
                <span className="ml-1 text-xs text-zinc-500">{row.oe_basis_note}</span>
              ) : null}
            </span>
          );
        }
        if (i === PRICE_CELL_INDEX) {
          const cell = priceCell(row);
          return (
            <span key="price" data-testid="sector-price" title={cell.title ?? undefined}>
              {cell.amount}
              {cell.asOf ? <span className="ml-1 text-xs text-zinc-500">{cell.asOf}</span> : null}
            </span>
          );
        }
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
    ];
    if (effectiveScope === "sp1500") {
      cells.push(row.index ? indexLabel(row.index) : "—");
    }
    return { kind: "data" as const, cells };
  });

  const widenHref =
    group.sector && effectiveScope === "sp1500"
      ? `${sectorHref(group.sector)}?index=sp1500`
      : group.sector
        ? sectorHref(group.sector)
        : null;
  const widen =
    group.level === "sub_industry" && group.sector && widenHref ? (
      <Link
        href={widenHref}
        data-testid="sector-widen-link"
        className="underline underline-offset-4 text-zinc-300 hover:text-white"
      >
        Widen to {group.sector}
      </Link>
    ) : null;
  const ownMissingNote = snap
    ? sectorOwnMissingNote(snap, group, current, effectiveScope)
    : null;

  return (
    <section className="mt-6 text-left" data-testid="sector-table" data-level={group.level}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h3 className="text-base sm:text-lg text-zinc-300" data-testid="sector-table-heading">
          {sectorTableHeading(props.kind, group, effectiveScope)}
        </h3>
        {scopeToggle}
      </div>
      <p className="text-sm text-zinc-500 mb-2" data-testid="sector-table-note">
        {sectorTableNote(group, snap?.priceAsOf ?? null)}
        {widen ? <> · {widen}</> : null}
      </p>
      {ownMissingNote ? (
        <p className="text-sm text-zinc-500 mb-2" data-testid="sector-table-own-missing">
          {ownMissingNote}
        </p>
      ) : null}
      <DataTable headers={headers} rows={rows} />
    </section>
  );
}
