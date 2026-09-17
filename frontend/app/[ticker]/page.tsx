import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { AnalyzePage } from '../analyze-page';
import { normalizeTickerSegment } from '../utils/ticker';

const META_TIMEOUT_MS = 15_000;
const META_REVALIDATE_SECONDS = 86_400;

type PageProps = {
  params: Promise<{ ticker: string }>;
};

function backendOrigin(): string {
  return (
    process.env.BACKEND_ORIGIN ||
    process.env.HAYSTACK_BACKEND_ORIGIN ||
    'http://127.0.0.1:8000'
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function companyNameFromAnalyze(raw: unknown): string | null {
  if (!isRecord(raw)) return null;
  const name = raw.company_name;
  if (typeof name !== 'string') return null;
  const trimmed = name.trim();
  return trimmed || null;
}

async function fetchCompanyName(symbol: string): Promise<string | null> {
  const url = `${backendOrigin()}/analyze/${encodeURIComponent(symbol)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), META_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      next: { revalidate: META_REVALIDATE_SECONDS },
    });
    if (!response.ok) return null;
    const raw: unknown = await response.json();
    return companyNameFromAnalyze(raw);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function shareTitle(symbol: string, company: string | null): string {
  return company ? `${symbol} · ${company} | LongMuch` : `${symbol} | LongMuch`;
}

function shareDescription(symbol: string, company: string | null): string {
  if (company) {
    return `How much? How long? for ${company} (${symbol}) — multi-year 10-K ratios and per-share fundamentals.`;
  }
  return `How much? How long? for ${symbol} — multi-year 10-K ratios and per-share fundamentals.`;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { ticker: raw } = await params;
  const symbol = normalizeTickerSegment(raw);
  if (!symbol) {
    return {
      title: 'LongMuch',
      description: 'How much? How long?',
    };
  }

  let company: string | null = null;
  try {
    company = await fetchCompanyName(symbol);
  } catch {
    company = null;
  }

  const title = shareTitle(symbol, company);
  const description = shareDescription(symbol, company);

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `/${symbol}`,
      type: 'website',
    },
    twitter: {
      card: 'summary',
      title,
      description,
    },
  };
}

export default async function TickerPage({ params }: PageProps) {
  const { ticker: raw } = await params;
  const symbol = normalizeTickerSegment(raw);
  if (!symbol) {
    notFound();
  }

  return <AnalyzePage initialTicker={symbol} />;
}
