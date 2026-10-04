import snapshot from '../../public/screen/sp500-oe-yield.json';

type ScreenRow = {
  ticker?: unknown;
  name?: unknown;
  oe_yield?: unknown;
  price?: unknown;
  fy?: unknown;
  price_as_of?: unknown;
};

export type ScreenCardRow = {
  ticker: string;
  name: string;
  oe_yield: number | null;
  price: number | null;
  fy: number | null;
  price_as_of: string | null;
};

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function dateString(value: unknown): string | null {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function companyNameFromScreen(ticker: string): string | null {
  const symbol = ticker.trim().toUpperCase();
  if (!symbol) return null;
  if (!isRecord(snapshot) || !Array.isArray(snapshot.rows)) return null;
  for (const row of snapshot.rows as ScreenRow[]) {
    if (!isRecord(row)) continue;
    if (typeof row.ticker !== 'string') continue;
    if (row.ticker.trim().toUpperCase() !== symbol) continue;
    if (typeof row.name !== 'string') return null;
    const name = row.name.trim();
    return name || null;
  }
  return null;
}

export function screenSnapshotPriceAsOf(): string | null {
  if (!isRecord(snapshot)) return null;
  return dateString(snapshot.price_as_of);
}

/** Bundled S&P 500 row for a ticker, or null when the snapshot has no match. */
export function screenRowForTicker(ticker: string): ScreenCardRow | null {
  const symbol = ticker.trim().toUpperCase();
  if (!symbol) return null;
  if (!isRecord(snapshot) || !Array.isArray(snapshot.rows)) return null;
  for (const row of snapshot.rows as ScreenRow[]) {
    if (!isRecord(row)) continue;
    if (typeof row.ticker !== 'string') continue;
    if (row.ticker.trim().toUpperCase() !== symbol) continue;
    const name = typeof row.name === 'string' ? row.name.trim() : '';
    return {
      ticker: symbol,
      name,
      oe_yield: finiteNumber(row.oe_yield),
      price: finiteNumber(row.price),
      fy: finiteNumber(row.fy),
      price_as_of: dateString(row.price_as_of),
    };
  }
  return null;
}
