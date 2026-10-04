import { ImageResponse } from 'next/og';
import { screenRowForTicker, screenSnapshotPriceAsOf } from '../utils/screen-name';
import { normalizeTickerSegment } from '../utils/ticker';

export const alt = 'LongMuch share card';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

const canvas = '#09090b';
const surface = '#18181b';
const foreground = '#fafafa';
const muted = '#a1a1aa';
const edge = '#27272a';

function yieldLine(oeYield: number, price: number): string {
  return `Owner-earnings yield ${(oeYield * 100).toFixed(1)}% vs last close $${price.toFixed(2)}`;
}

export default async function Image({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  let tickerLabel = 'LongMuch';
  let company: string | null = null;
  let detail: string | null = null;
  let fyLine: string | null = null;
  let asOfLine: string | null = null;

  try {
    const { ticker: raw } = await params;
    const symbol = normalizeTickerSegment(typeof raw === 'string' ? raw : '');
    tickerLabel = symbol ?? (typeof raw === 'string' && raw.trim() ? raw.trim() : 'LongMuch');
    const row = symbol ? screenRowForTicker(symbol) : null;
    if (row) {
      tickerLabel = row.ticker;
      company = row.name || null;
      if (row.oe_yield != null && row.price != null) {
        detail = yieldLine(row.oe_yield, row.price);
      }
      if (row.fy != null) {
        fyLine = `Latest FY ${Math.trunc(row.fy)}`;
      }
      const asOf = row.price_as_of ?? screenSnapshotPriceAsOf();
      if (asOf) asOfLine = `As of ${asOf}`;
    }
  } catch {
    tickerLabel = 'LongMuch';
  }

  const nameOnly = !company && !detail && !fyLine && !asOfLine;

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: canvas,
          color: foreground,
          padding: '64px 72px',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', fontSize: 28, letterSpacing: 4, color: muted }}>
            LONGMUCH
          </div>
          <div
            style={{
              display: 'flex',
              marginTop: 28,
              fontSize: 92,
              fontWeight: 700,
              lineHeight: 1,
            }}
          >
            {tickerLabel}
          </div>
          {company ? (
            <div style={{ display: 'flex', marginTop: 16, fontSize: 36, color: muted }}>
              {company}
            </div>
          ) : null}
          {detail || fyLine || asOfLine ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                marginTop: 36,
                padding: '24px 28px',
                background: surface,
                border: `1px solid ${edge}`,
                borderRadius: 16,
              }}
            >
              {detail ? (
                <div style={{ display: 'flex', fontSize: 32 }}>{detail}</div>
              ) : null}
              {fyLine ? (
                <div style={{ display: 'flex', marginTop: detail ? 12 : 0, fontSize: 26, color: muted }}>
                  {fyLine}
                </div>
              ) : null}
              {asOfLine ? (
                <div style={{ display: 'flex', marginTop: 8, fontSize: 26, color: muted }}>
                  {asOfLine}
                </div>
              ) : null}
            </div>
          ) : null}
          {nameOnly ? (
            <div style={{ display: 'flex', marginTop: 28, fontSize: 40, color: muted }}>
              LongMuch · How much? How long?
            </div>
          ) : null}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 28, color: muted }}>
          <div style={{ display: 'flex' }}>LongMuch</div>
          <div style={{ display: 'flex' }}>longmuch.com</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
