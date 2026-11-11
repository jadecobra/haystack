#!/usr/bin/env node
/**
 * Local failure injection for browser.cjs click-through. Route mocks only.
 * Does not change app code. Each scenario must exit non-zero except retry-pass.
 */
const path = require('node:path');
const { runClickThrough, loadPlaywright } = require('./browser.cjs');

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

function pageHtml(kind, fault) {
  const logoSrc = fault === 'missing-image' ? '/broken.png' : '/logo.png';
  const wide = fault === 'clipped' ? '<div style="overflow-x:hidden;width:100%"><div style="width:2000px;height:12px">wide</div></div>' : '';
  const badge = fault === 'badge' ? '<div data-next-badge data-error="true">1 Issue</div>' : '';
  const boom = fault === 'console' ? '<script>console.error("injected console error")</script>' : '';
  const homeAlert = fault === 'valid-error' ? '<p role="alert">Couldn’t analyze AAPL.</p>' : '';
  const nav = `
    <nav data-testid="site-nav">
      <a href="/docs">How metrics are calculated</a>
      <a href="/screen">S&P 500</a>
      <a href="/sector/information-technology">Information Technology</a>
    </nav>`;
  const logo = `<a href="/"><img alt="LongMuch" src="${logoSrc}" width="500" height="500"></a>`;
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
  const metrics = `
    <h2 data-testid="company-heading">AAPL · Apple Inc. Financial Metrics</h2>
    <table><tr><td>Revenue</td><td>100</td></tr></table>
    <a href="/sector/information-technology">Information Technology</a>`;
  const emptyMetrics = `
    <h2 data-testid="company-heading">AAPL Financial Metrics</h2>
    <table><tr><td>—</td><td>—</td></tr></table>`;
  const sector = `
    <h1>Sector comparison</h1>
    <a data-testid="sector-row-link" href="/AAPL">AAPL</a>
    <a data-testid="sector-row-link" href="/MSFT">MSFT</a>`;
  const screen = `
    <h1>S&P 500 owner-earnings yield</h1>
    <span data-testid="screen-oe-yield">3.1%</span>`;
  const docs = `<h1>How metrics are calculated</h1><p>Primer</p>`;
  const invalid = `<p role="alert">We couldn’t find that ticker (ZZZZQ). Check the symbol and try again.</p>`;
  let body = '';
  if (kind === 'home') body = `${logo}${form}${homeAlert}${wide}${badge}${boom}${nav}`;
  else if (kind === 'metrics') body = `${logo}${form}${fault === 'empty-metrics' ? emptyMetrics : metrics}${nav}`;
  else if (kind === 'invalid') body = `${logo}${form}${invalid}${nav}`;
  else if (kind === 'sector') body = `${sector}${nav}`;
  else if (kind === 'screen') body = `${screen}${nav}`;
  else if (kind === 'docs') body = `${docs}${nav}`;
  else if (kind === 'missing-form') body = `${logo}${nav}`;
  else body = `${logo}${nav}`;
  return `<!doctype html><html><head><title>LongMuch</title><style>img{max-width:100%;height:auto}</style></head><body>${body}</body></html>`;
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
      if (pathname === '/broken.png') {
        await route.fulfill({ status: 404, contentType: 'text/plain', body: 'missing' });
        return;
      }
      if (pathname.startsWith('/api/analyze/')) {
        state.analyzeHits += 1;
        if (fault === 'api-500') {
          await route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"nope"}' });
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
        const html = fault === 'empty-metrics'
          ? '<h2 data-testid="company-heading">AAPL Financial Metrics</h2><table><tr><td>—</td><td>—</td></tr></table>'
          : '<h2 data-testid="company-heading">AAPL · Apple Inc. Financial Metrics</h2><table><tr><td>Revenue</td><td>100</td></tr></table><a href="/sector/information-technology">Information Technology</a>';
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
        return;
      }
      let kind = 'home';
      if (pathname === '/AAPL') kind = 'metrics';
      else if (pathname === '/ZZZZQ') kind = 'invalid';
      else if (pathname.startsWith('/sector/')) kind = fault === 'broken-link' ? 'missing' : 'sector';
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
    ['api-500', { exit: 1, includes: 'status 500' }],
    ['empty-metrics', { exit: 1, includes: 'company name is missing' }],
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
