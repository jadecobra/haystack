/** Normalize a path/search segment to an uppercase ticker, or null if reserved/nonsense. */
export function normalizeTickerSegment(raw: string): string | null {
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null;
  }
  const symbol = decoded.toUpperCase().trim();
  if (!symbol) return null;
  if (symbol === '.' || symbol === '..') return null;
  if (/[/\\]/.test(symbol)) return null;
  // Static app folders already win over [ticker]; reject as a safety net.
  if (symbol === 'API' || symbol === 'DOCS') return null;
  return symbol;
}
