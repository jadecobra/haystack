function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const UNKNOWN_TICKER =
  /unknown ticker|no cik|company not found|no companyfacts|no company \/ no annual facts|no annual us-gaap facts|unsupported ticker|not a filer|etf/i;
const HTTP_NOT_FOUND = /\b404\b|not found/i;
const SEC_HOST = /sec\.gov|companyfacts|data\.sec\.gov/i;
const TIMEOUT =
  /timeout|timed out|aborted|abort|taking too long|504|gateway/i;
const UNSAFE =
  /traceback|find_company|pass a cik|file ".+\.py"|^\s*at /im;
const SEC_URL = /https?:\/\/[^\s]*sec\.gov[^\s]*/gi;

export const ANALYZE_TIMEOUT_MS = 20_000;
export const ANALYZE_TIMEOUT_MESSAGE =
  'This is taking too long. Try again.';

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
    .replace(SEC_URL, '')
    .replace(/\s*Tip:[\s\S]*$/i, '')
    .replace(/\s*Use find_company[\s\S]*$/i, '')
    .replace(/\s{2,}/g, ' ')
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
  const combined = [detail, typeof args.raw === 'string' ? args.raw : '']
    .filter(Boolean)
    .join(' ');

  if (TIMEOUT.test(combined)) {
    return ANALYZE_TIMEOUT_MESSAGE;
  }

  if (
    (detail && UNKNOWN_TICKER.test(detail)) ||
    (detail && HTTP_NOT_FOUND.test(detail) && SEC_HOST.test(detail)) ||
    (detail && SEC_HOST.test(detail) && HTTP_NOT_FOUND.test(detail))
  ) {
    return `We couldn’t find that ticker (${ticker}). Check the symbol and try again.`;
  }

  if (detail) {
    const cleaned = stripTips(detail);
    if (UNKNOWN_TICKER.test(cleaned) || SEC_HOST.test(cleaned)) {
      return `We couldn’t find that ticker (${ticker}). Check the symbol and try again.`;
    }
    if (cleaned && isSafeHumanDetail(cleaned)) {
      return cleaned;
    }
  }

  return `Couldn’t analyze ${ticker}. If this keeps happening, report the ticker.`;
}
