/** Names the S&P 500 screen does not rank (#71). Ranking math stays in the snapshot. */

import type { IndexId } from "./sectorTable";

export type UnrankedName = {
  ticker: string;
  name: string | null;
  reason: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function matchesIndex(
  item: Record<string, unknown>,
  payloadUniverse: unknown,
  indexFilter?: IndexId,
): boolean {
  if (!indexFilter) return true;
  if (typeof item.index === "string") return item.index === indexFilter;
  // Legacy sp500 snapshots lack per-item index tags; match via payload.universe.
  return payloadUniverse === indexFilter;
}

/** Drop the snapshot's category prefix. Keep the clause that says why. */
export function shortReason(reason: string): string {
  const text = reason.replace(/\s+/g, " ").trim();
  if (/no SEC annual/i.test(text)) return "no SEC annual facts";
  const owner = text.match(/^no owner earnings:\s*(.+)$/i);
  if (owner) return owner[1].replace(/\.$/, "");
  return text;
}

function tickerOf(value: unknown): string | null {
  if (!isRecord(value) || typeof value.ticker !== "string") return null;
  const ticker = value.ticker.trim().toUpperCase();
  return ticker || null;
}

function nameOf(value: Record<string, unknown>): string | null {
  return typeof value.name === "string" && value.name.trim() ? value.name.trim() : null;
}

/** Why parseRow drops the row. Null when the row can stay in the table. */
export function dropReason(value: unknown): string | null {
  if (!isRecord(value) || tickerOf(value) === null) return null;
  if (typeof value.price !== "number" || !Number.isFinite(value.price)) return "no price";
  if (typeof value.fy !== "number" || !Number.isFinite(value.fy)) return "no fiscal year";
  return null;
}

function blankReason(row: Record<string, unknown>): string | null {
  if (typeof row.oe_yield === "number" && Number.isFinite(row.oe_yield)) return null;
  if (typeof row.oe_note === "string" && row.oe_note.trim()) return shortReason(row.oe_note);
  return "no owner earnings";
}

/**
 * Excluded names, blank OE-yield rows, then rows parseRow drops.
 * One entry per ticker. Order follows the snapshot.
 */
export function listUnranked(payload: unknown, indexFilter?: IndexId): UnrankedName[] {
  if (!isRecord(payload)) return [];
  const out: UnrankedName[] = [];
  const seen = new Set<string>();
  const push = (ticker: string, name: string | null, reason: string) => {
    if (seen.has(ticker)) return;
    seen.add(ticker);
    out.push({ ticker, name, reason });
  };

  if (Array.isArray(payload.excluded)) {
    for (const item of payload.excluded) {
      const ticker = tickerOf(item);
      if (!ticker || !isRecord(item)) continue;
      if (!matchesIndex(item, payload.universe, indexFilter)) continue;
      const reason =
        typeof item.reason === "string" && item.reason.trim()
          ? shortReason(item.reason)
          : "excluded";
      push(ticker, nameOf(item), reason);
    }
  }

  if (Array.isArray(payload.rows)) {
    const dropped: UnrankedName[] = [];
    for (const row of payload.rows) {
      const ticker = tickerOf(row);
      if (!ticker || !isRecord(row)) continue;
      if (!matchesIndex(row, payload.universe, indexFilter)) continue;
      const droppedBecause = dropReason(row);
      if (droppedBecause) {
        dropped.push({ ticker, name: nameOf(row), reason: droppedBecause });
        continue;
      }
      const blank = blankReason(row);
      if (blank) push(ticker, nameOf(row), blank);
    }
    for (const item of dropped) push(item.ticker, item.name, item.reason);
  }

  return out;
}

/** Ranked count plus not-ranked count equals rows plus excluded. */
export function universeBalances(payload: unknown, indexFilter?: IndexId): boolean {
  if (!isRecord(payload)) return false;
  const rows = Array.isArray(payload.rows)
    ? payload.rows.filter((r) => isRecord(r) && matchesIndex(r, payload.universe, indexFilter))
    : [];
  const excluded = Array.isArray(payload.excluded)
    ? payload.excluded.filter((e) => isRecord(e) && matchesIndex(e, payload.universe, indexFilter))
    : [];
  const unranked = listUnranked(payload, indexFilter).length;
  const ranked =
    !indexFilter && typeof payload.ranked === "number" && Number.isFinite(payload.ranked)
      ? payload.ranked
      : rows.filter((row) => {
          if (dropReason(row)) return false;
          return typeof row.oe_yield === "number" && Number.isFinite(row.oe_yield);
        }).length;
  return ranked + unranked === rows.length + excluded.length;
}
