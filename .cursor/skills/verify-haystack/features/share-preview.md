# Share preview

A ticker URL shares a canonical LongMuch card: uppercase path, Open Graph and Twitter large-image tags, and a 1200×630 PNG. Tickers in the bundled S&P 500 snapshot include owner-earnings yield; others still return a name-only card. After the table is ready, the page links to SEC EDGAR 10-K filings.

## Sub-features

- `canonical-url` serves `/{TICKER}` and permanently redirects a lowercase segment to it.
- `share-meta` emits `og:title`, `og:image`, `og:url`, `twitter:card=summary_large_image`, `twitter:image`, and `link rel=canonical` `https://longmuch.com/{TICKER}`.
- `share-image` is a 1200×630 `image/png`. Next copies the opengraph image onto Twitter when `twitter.images` is unset, so `twitter:image` is present without a separate file.
- `name-only-card` still returns that PNG for a ticker absent from the snapshot, such as `ZZZZQ`.
- `sec-source` shows `Source: SEC filings` (`data-testid="sec-source-link"`) once the analyze view is ready.

## How to get to it (user POV)

- Open `$FRONTEND_ORIGIN/AAPL` (or another ticker).
- Open `$FRONTEND_ORIGIN/aapl` and land on `/AAPL`.
- After Analyze finishes, use `Source: SEC filings` next to the metrics heading.

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN` from `helpers/launch`, or set `LIVE=1` / `ORIGIN=https://longmuch.com`.
- `helpers/doctor` reports `DOCTOR PASS` for an isolated run.
- Do not use `http://127.0.0.1:3000`.

- **Share tags and image.** Run `FEATURE=share-preview .cursor/skills/verify-haystack/helpers/http share-preview AAPL`. Page HTTP 200. HTML contains `og:title`, `og:image`, `og:url`, `twitter:card` `summary_large_image`, `twitter:image`, and canonical `https://longmuch.com/AAPL`. The image URL is HTTP 200, `content-type` `image/png`, PNG IHDR 1200×630.
- **Lowercase redirect.** The same command GETs `/aapl` without following redirects. Status is 307 or 308. `Location` ends with `/AAPL`.
- **Missing snapshot row.** The same command GETs the `ZZZZQ` `og:image` URL. HTTP 200, `image/png`, 1200×630.
- **Production.** Run `LIVE=1 FEATURE=share-preview .cursor/skills/verify-haystack/helpers/http share-preview AAPL` (or `ORIGIN=https://longmuch.com`). Same checks. Refuses port 3000.
- **Proof.** Keep `artifacts/share-preview/page.html`, `page.status`, `og-image.png`, `og-image.status`, `lower.headers`, `lower.status`, `missing-og.png`, and `missing-og.status`.

## Gotchas

- Canonical host is `https://longmuch.com` from layout `metadataBase`, even when the page is served from an isolated origin.
- The share image reads the bundled snapshot only. It does not call `/analyze`.
- `Source: SEC filings` is client-rendered after `ready`. SSR HTML of `/{TICKER}` does not include that link. Curl proof covers the card, not the link.
- Twitter uses the opengraph image via Next's metadata fallback. Do not require a second `twitter-image` file when `twitter:image` is already in the HTML.
