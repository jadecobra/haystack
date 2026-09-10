function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const UNKNOWN_TICKER = /unknown ticker|no cik|company not found/i;
const UNSAFE =
  /traceback|find_company|pass a cik|file ".+\.py"|^\s*at /im;

function firstHumanField(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (Array.isArray(value)) {
    const parts: string[] = [];
    for (const item of value) {
      if (typeof item === 'string' && item.trim()) {
        parts.push(item.trim());
      } else if (isRecord(item) && typeof item.msg === 'string' && item.msg.trim()) {
        parts.push(item.msg.trim());
      }
    }
    if (parts.length > 0) return parts.join('; ');
  }
  return null;
}

function extractRawMessage(raw: unknown): string | null {
  if (!isRecord(raw)) return null;
  return (
    firstHumanField(raw.error) ||
    firstHumanField(raw.message) ||
    firstHumanField(raw.detail)
  );
}

function stripTips(text: string): string {
  return text
    .replace(/\s*Tip:[\s\S]*$/i, '')
    .replace(/\s*Use find_company[\s\S]*$/i, '')
    .trim();
}

function isSafeHumanDetail(text: string): boolean {
  if (text.length > 180) return false;
  if (UNSAFE.test(text)) return false;
  if (text.split('\n').length > 2) return false;
  return true;
}

export function analyzeErrorMessage(args: {
  raw: unknown;
  ticker: string;
}): string {
  const ticker = args.ticker.trim().toUpperCase() || 'that ticker';
  const detail = extractRawMessage(args.raw);

  if (detail && UNKNOWN_TICKER.test(detail)) {
    return `We couldn’t find that ticker (${ticker}). Check the symbol and try again.`;
  }

  if (detail) {
    const cleaned = stripTips(detail);
    if (cleaned && isSafeHumanDetail(cleaned) && !UNKNOWN_TICKER.test(cleaned)) {
      return cleaned;
    }
  }

  return `Couldn’t analyze ${ticker}. If this keeps happening, report the ticker.`;
}
