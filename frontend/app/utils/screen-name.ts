import snapshot from '../../public/screen/sp500-oe-yield.json';

type ScreenRow = {
  ticker?: unknown;
  name?: unknown;
};

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
