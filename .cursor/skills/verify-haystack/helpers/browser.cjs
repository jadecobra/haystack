#!/usr/bin/env node
/**
 * Skill-local optional Playwright driver for the isolated frontend origin.
 * Does NOT start Next, does NOT use ports 3000 or 8000.
 *
 * Usage (after helpers/launch):
 *   FEATURE=home-search node helpers/browser.cjs snapshot
 *   FEATURE=analyze-results node helpers/browser.cjs analyze AAPL
 *
 * If Playwright/Chromium is missing, writes browser-skipped.txt and exits 0.
 */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

const skillDir = path.resolve(__dirname, '..');
const artifactsDir = path.join(skillDir, 'artifacts');
const currentRunFile = path.join(skillDir, '.current-run');

function die(msg) {
  console.error(`verify-haystack browser: ${msg}`);
  process.exit(1);
}

function loadRun() {
  const runDir = process.env.RUN_DIR || (fs.existsSync(currentRunFile)
    ? fs.readFileSync(currentRunFile, 'utf8').trim()
    : '');
  if (!runDir) die('no RUN_DIR / .current-run; run helpers/launch first');
  const envPath = path.join(runDir, 'run.env');
  if (!fs.existsSync(envPath)) die(`missing ${envPath}`);
  const env = {};
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const i = line.indexOf('=');
    if (i > 0) env[line.slice(0, i)] = line.slice(i + 1);
  }
  return env;
}

function refuseOrigin(origin) {
  const m = String(origin).match(/:(\d+)/);
  const port = m ? m[1] : '';
  if (port === '3000' || port === '8000') {
    die(`refusing origin ${origin} (forbidden shared port)`);
  }
}

function loadPlaywright() {
  const candidates = [
    path.join(skillDir, 'node_modules', 'playwright'),
    'playwright',
  ];
  for (const spec of candidates) {
    try {
      if (spec.startsWith('/')) {
        return createRequire(path.join(skillDir, 'package.json'))(spec);
      }
      return require(spec);
    } catch {
      /* try next */
    }
  }
  return null;
}

(async () => {
  const run = loadRun();
  const origin = process.env.FRONTEND_ORIGIN || run.FRONTEND_ORIGIN;
  refuseOrigin(origin);

  const cmd = process.argv[2] || 'snapshot';
  const feature = process.env.FEATURE || 'home-search';
  const outDir = path.join(artifactsDir, feature);
  fs.mkdirSync(outDir, { recursive: true });

  const pw = loadPlaywright();
  if (!pw || !pw.chromium) {
    const msg = 'playwright module not importable; HTTP proof remains valid';
    fs.writeFileSync(path.join(outDir, 'browser-skipped.txt'), msg + '\n');
    console.log(`browser skipped: ${msg}`);
    process.exit(0);
  }

  let browser;
  try {
    browser = await pw.chromium.launch({ headless: true });
  } catch (err) {
    const msg = String(err && err.message ? err.message : err);
    fs.writeFileSync(path.join(outDir, 'browser-skipped.txt'), msg);
    console.log(`browser skipped (chromium not installed): ${msg}`);
    process.exit(0);
  }

  const page = await browser.newPage();
  try {
    await page.goto(origin + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const h1 = await page.locator('h1').first().textContent();
    const shot = path.join(outDir, `${cmd}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    fs.writeFileSync(path.join(outDir, `${cmd}.h1.txt`), String(h1 || '').trim() + '\n');

    if (cmd === 'analyze') {
      const ticker = (process.argv[3] || 'AAPL').toUpperCase();
      await page.locator('input[placeholder="AAPL or TSLA"]').fill(ticker);
      await page.locator('button', { hasText: 'Analyze' }).click();
      await page.waitForTimeout(2000);
      const html = await page.content();
      fs.writeFileSync(path.join(outDir, 'after-click.html'), html);
      await page.screenshot({ path: path.join(outDir, 'after-click.png'), fullPage: true });
      const hasTable = html.includes('5-Year Financial Metrics');
      const hasKpi = /Net Income/.test(html) && html.includes('5-Year Financial Metrics');
      fs.writeFileSync(
        path.join(outDir, 'after-click.meta.txt'),
        [
          `ticker=${ticker}`,
          `h1=${String(h1 || '').trim()}`,
          `has_table=${hasTable}`,
          `note=Table rows in page.tsx are hardcoded sample billions; KPI values come from /api/analyze JSON (currently 404 because [ticker].ts is not route.ts).`,
        ].join('\n') + '\n'
      );
      console.log(`analyze click ticker=${ticker} has_table=${hasTable} screenshot=${path.join(outDir, 'after-click.png')}`);
    } else {
      console.log(`snapshot h1=${String(h1 || '').trim()} screenshot=${shot}`);
    }
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
