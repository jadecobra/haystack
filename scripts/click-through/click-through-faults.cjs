#!/usr/bin/env node
/**
 * Local failure injection for browser.cjs click-through. Route mocks only.
 * Does not change app code. Each scenario must exit non-zero except retry-pass
 * and allowed stale-snapshot cases.
 */
const path = require('node:path');
const { runClickThrough, loadPlaywright } = require('./browser.cjs');

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

function metricsHtml(fault) {
  const sectorCard =
    fault === 'sector-missing-card-link'
      ? ''
      : '<section data-testid="sector-table"><a href="/sector/information-technology" data-testid="sector-widen-link">Widen to Information Technology</a></section>';

  if (fault === 'missing-company-name' || fault === 'empty-metrics') {
    return `<h2 data-testid="company-heading">AAPL Financial Metrics | source : EDGAR</h2><table><tbody><tr><td>Revenue</td><td>100</td></tr></tbody></table>${sectorCard}`;
  }
  if (fault === 'empty-metrics-values') {
    return `<h2 data-testid="company-heading">AAPL · Apple Inc. Financial Metrics | source : EDGAR</h2><table><tbody><tr><td>Revenue</td><td>—</td><td>NaN</td></tr></tbody></table>${sectorCard}`;
  }
  return `<h2 data-testid="company-heading">AAPL · Apple Inc. Financial Metrics | source : EDGAR</h2><table><tbody><tr><td>Revenue</td><td>100</td></tr></tbody></table>${sectorCard}`;
}

function pageHtml(kind, fault) {
  const logoSrc = fault === 'missing-image' ? '/broken.png' : '/logo.png';
  const wide =
    fault === 'clipped'
      ? '<div style="overflow-x:hidden;width:100%"><div style="width:2000px;height:12px">wide</div></div>'
      : '';
  const badge = fault === 'badge' ? '<div data-next-badge data-error="true">1 Issue</div>' : '';
  const boom = fault === 'console' ? '<script>console.error("injected console error")</script>' : '';
  const brokenAsset = fault === 'broken-asset' ? '<script src="/_next/static/broken.js"></script>' : '';
  const homeAlert =
    fault === 'valid-error'
      ? '<p role="alert">Couldn’t analyze AAPL.</p>'
      : fault === 'stale-snapshot-wrong-path'
        ? '<p role="alert">Stale snapshot.</p>'
        : '';
  const nav = `
    <nav data-testid="site-nav">
      <a href="/docs">How metrics are calculated</a>
      <a href="/screen">S&P 500</a>
      <a href="/sector/communication-services">Communication Services</a>
      <a href="/sector/information-technology">Information Technology</a>
    </nav>`;
  const logoHrefClick =
    fault === 'broken-logo-noop' ? ' onclick="event.preventDefault()"' : '';
  const logo = `<a href="/"${logoHrefClick}><img alt="LongMuch" src="${logoSrc}" width="500" height="500"></a>`;
  const form = `
    <input placeholder="enter stock ticker e.g. AAPL">
    <button>Analyze</button>
    <script>
      document.querySelector('button').addEventListener('click', async () => {
        const ticker = document.querySelector('input').value || 'AAPL';
        const res = await fetch('/api/analyze/' + ticker);
        if (!res.ok) {
          const p = document.createElement('p');
          p.setAttribute('role', 'alert');
          p.textContent = 'Couldn’t analyze ' + ticker + '.';
          document.body.appendChild(p);
          return;
        }
        const html = await res.text();
        document.body.insertAdjacentHTML('beforeend', html);
      });
    </script>`;
  const sector = `
    <h1>Sector comparison</h1>
    <a data-testid="sector-row-link" href="/AAPL">AAPL</a>
    <a data-testid="sector-row-link" href="/MSFT">MSFT</a>`;
  const screenAlert =
    fault === 'stale-snapshot-aged'
      ? '<p role="alert">Stale snapshot.</p>'
      : fault === 'stale-snapshot-backend-error'
        ? '<p role="alert">Stale snapshot. serving last-good snapshot</p>'
        : '';
  const screenFetch =
    fault === 'non-edgar-timeout'
      ? '<script>fetch("/api/screen/sp500-oe-yield").catch(() => {});</script>'
      : '';
  const screen = `
    <h1>S&P 500 owner-earnings yield</h1>
    ${screenAlert}
    ${screenFetch}
    <span data-testid="screen-oe-yield">3.1%</span>`;
  const docs = `<h1>How metrics are calculated</h1><p>Primer</p>`;
  const invalidFetch =
    fault === 'invalid-ticker-500' || fault === 'invalid-ticker-missing'
      ? `<script>fetch('/api/analyze/ZZZZQ').then(async (r) => { ${
          fault === 'invalid-ticker-missing'
            ? ''
            : 'const p = document.createElement("p"); p.setAttribute("role", "alert"); p.textContent = "We couldn’t find that ticker (ZZZZQ). Check the symbol and try again."; document.body.appendChild(p);'
        } }).catch(() => {});</script>`
      : '';
  const invalid =
    fault === 'invalid-ticker-500' || fault === 'invalid-ticker-missing'
      ? `${invalidFetch}`
      : `<p role="alert">We couldn’t find that ticker (ZZZZQ). Check the symbol and try again.</p>`;

  let body = '';
  if (kind === 'home') body = `${logo}${form}${homeAlert}${wide}${badge}${boom}${brokenAsset}${nav}`;
  else if (kind === 'metrics') body = `${logo}${form}${metricsHtml(fault)}${nav}`;
  else if (kind === 'invalid') body = `${logo}${form}${invalid}${nav}`;
  else if (kind === 'sector') body = `${sector}${nav}`;
  else if (kind === 'sector-missing') {
    body = `<h1>Sector comparison</h1><p role="alert" data-testid="sector-table-missing">No S&P 500 sector or sub-industry matches this page.</p>${nav}`;
  } else if (kind === 'screen') body = `${screen}${nav}`;
  else if (kind === 'docs') body = `${docs}${nav}`;
  else if (kind === 'missing-form') body = `${logo}${nav}`;
  else body = `${logo}${nav}`;
  return `<!doctype html><html><head><meta charset="utf-8"><title>LongMuch</title><style>img{max-width:100%;height:auto}</style></head><body>${body}</body></html>`;
}

function install(fault, state) {
  return async (page) => {
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      const pathname = url.pathname;
      if (pathname === '/logo.png') {
        await route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
        return;
      }
      if (pathname === '/broken.png' || pathname === '/_next/static/broken.js') {
        await route.fulfill({ status: 404, contentType: 'text/plain', body: 'missing' });
        return;
      }
      if (pathname === '/api/screen/sp500-oe-yield') {
        if (fault === 'non-edgar-timeout') {
          await route.fulfill({ status: 504, contentType: 'application/json', body: '{"error":"timeout"}' });
          return;
        }
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{"rows":[]}' });
        return;
      }
      if (pathname.startsWith('/api/analyze/')) {
        state.analyzeHits += 1;
        if (fault === 'api-500') {
          await route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"nope"}' });
          return;
        }
        if (fault === 'invalid-ticker-500' && pathname === '/api/analyze/ZZZZQ') {
          await route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"boom"}' });
          return;
        }
        if (fault === 'invalid-ticker-missing' && pathname === '/api/analyze/ZZZZQ') {
          await route.fulfill({ status: 400, contentType: 'application/json', body: '{"detail":"unknown ticker"}' });
          return;
        }
        if (fault === 'timeout-once' && state.analyzeHits === 1) {
          await new Promise((resolve) => setTimeout(resolve, 4000));
          await route.fulfill({ status: 504, contentType: 'application/json', body: '{"error":"timeout"}' });
          return;
        }
        if (fault === 'timeout-twice') {
          await new Promise((resolve) => setTimeout(resolve, 4000));
          await route.fulfill({ status: 504, contentType: 'application/json', body: '{"error":"timeout"}' });
          return;
        }
        await route.fulfill({ status: 200, contentType: 'text/html', body: metricsHtml(fault) });
        return;
      }
      let kind = 'home';
      if (pathname === '/AAPL') kind = 'metrics';
      else if (pathname === '/ZZZZQ') kind = 'invalid';
      else if (pathname === '/sector/communication-services' && fault === 'broken-nav-sector-alert') {
        kind = 'sector-missing';
      } else if (pathname.startsWith('/sector/')) kind = fault === 'broken-link' ? 'missing' : 'sector';
      else if (pathname === '/screen') kind = 'screen';
      else if (pathname === '/docs') kind = fault === 'broken-link' ? 'missing' : 'docs';
      else if (pathname === '/' && fault === 'missing-element') kind = 'missing-form';
      if (fault === 'broken-link' && (pathname === '/docs' || pathname.startsWith('/sector/'))) {
        await route.fulfill({
          status: 404,
          contentType: 'text/html',
          body: '<!doctype html><title>404</title><body>This page could not be found</body>',
        });
        return;
      }
      if (fault === 'timeout-once' && pathname === '/AAPL' && state.docHits === 0) {
        state.docHits += 1;
        await route.fulfill({
          status: 200,
          contentType: 'text/html',
          body: pageHtml('home', fault),
        });
        return;
      }
      if (fault === 'timeout-twice' && pathname === '/AAPL') {
        await route.fulfill({
          status: 200,
          contentType: 'text/html',
          body: pageHtml('home', fault),
        });
        return;
      }
      if (pathname === '/AAPL') state.docHits += 1;
      await route.fulfill({ status: 200, contentType: 'text/html', body: pageHtml(kind, fault) });
    });
  };
}

async function scenario(name, expect) {
  const outDir = path.join('/tmp', `click-through-fault-${name}`);
  const state = { analyzeHits: 0, docHits: 0 };
  const logs = [];
  const orig = console.log;
  console.log = (...args) => {
    logs.push(args.join(' '));
    orig.apply(console, args);
  };
  let code = 1;
  try {
    code = await runClickThrough({
      origin: 'http://127.0.0.1:9',
      outDir,
      widths: [390],
      metricsTimeoutMs: name.startsWith('timeout') ? 1500 : 8000,
      playwright: loadPlaywright(),
      headers: {},
      installRoutes: install(name, state),
    });
  } finally {
    console.log = orig;
  }
  const text = logs.join('\n');
  const ok = expect.exit === 0 ? code === 0 : code !== 0;
  const has = expect.includes ? text.includes(expect.includes) : true;
  const lacks = expect.excludes ? !text.includes(expect.excludes) : true;
  if (!ok || !has || !lacks) {
    console.error(`FAULT HARNESS FAIL ${name} exit=${code} includes=${has} excludes=${lacks}`);
    process.exit(1);
  }
  console.error(`FAULT HARNESS OK ${name} exit=${code}`);
}

(async () => {
  const cases = [
    ['api-500', { exit: 1, includes: 'status 500', excludes: 'two EDGAR timeouts' }],
    ['empty-metrics-values', { exit: 1, includes: 'metrics table values are empty' }],
    ['missing-company-name', { exit: 1, includes: 'company name is missing' }],
    ['sector-missing-card-link', { exit: 1, includes: 'path=sector width=390 result=fail' }],
    ['stale-snapshot-aged', { exit: 0, excludes: 'result=fail' }],
    ['stale-snapshot-backend-error', { exit: 1, includes: 'valid path shows an error message' }],
    ['stale-snapshot-wrong-path', { exit: 1, includes: 'valid path shows an error message' }],
    ['invalid-ticker-500', { exit: 1, includes: 'status 500', excludes: 'two EDGAR timeouts' }],
    ['invalid-ticker-missing', { exit: 1, includes: 'invalid ticker does not show its error message', excludes: 'two EDGAR timeouts' }],
    ['broken-asset', { exit: 1, includes: 'request /_next/static/broken.js status 404' }],
    ['broken-nav-sector-alert', { exit: 1, includes: 'path=header-footer-links width=390 result=fail' }],
    ['broken-logo-noop', { exit: 1, includes: 'path=logo width=390 result=fail' }],
    ['non-edgar-timeout', { exit: 1, includes: 'status 504', excludes: 'two EDGAR timeouts' }],
    ['broken-link', { exit: 1, includes: 'status 404' }],
    ['missing-image', { exit: 1, includes: 'image did not load' }],
    ['missing-element', { exit: 1, includes: 'ticker form is missing' }],
    ['console', { exit: 1, includes: 'console error' }],
    ['badge', { exit: 1, includes: 'issues badge' }],
    ['valid-error', { exit: 1, includes: 'valid path shows an error message' }],
    ['clipped', { exit: 1, includes: 'clipped at mobile width' }],
    ['timeout-once', { exit: 0, includes: 'passed after retry' }],
    ['timeout-twice', { exit: 1, includes: 'two EDGAR timeouts' }],
  ];
  const only = process.argv[2];
  for (const [name, expect] of cases) {
    if (only && only !== name) continue;
    await scenario(name, expect);
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
