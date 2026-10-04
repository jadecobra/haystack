import type { Metadata } from 'next';
import { notFound, permanentRedirect } from 'next/navigation';
import { AnalyzePage } from '../analyze-page';
import { companyNameFromScreen } from '../utils/screen-name';
import { normalizeTickerSegment } from '../utils/ticker';

type PageProps = {
  params: Promise<{ ticker: string }>;
};

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

  const company = companyNameFromScreen(symbol);

  const title = shareTitle(symbol, company);
  const description = shareDescription(symbol, company);

  return {
    title,
    description,
    alternates: {
      canonical: `/${symbol}`,
    },
    openGraph: {
      title,
      description,
      url: `/${symbol}`,
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
    },
  };
}

function decodedSegment(raw: string): string | null {
  try {
    return decodeURIComponent(raw);
  } catch {
    return null;
  }
}

export default async function TickerPage({ params }: PageProps) {
  const { ticker: raw } = await params;
  const decoded = decodedSegment(raw);
  const symbol = normalizeTickerSegment(raw);
  if (!decoded || !symbol) {
    notFound();
  }
  if (decoded !== symbol) {
    permanentRedirect(`/${symbol}`);
  }

  return <AnalyzePage initialTicker={symbol} />;
}
