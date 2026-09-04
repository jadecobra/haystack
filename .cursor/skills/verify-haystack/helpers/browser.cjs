#!/usr/bin/env node
/**
 * Skill-local optional Playwright driver for the isolated frontend origin.
 * Does NOT start Next, does NOT use ports 3000 or 8000.
 *
 * Usage (after helpers/launch):
 *   FEATURE=home-search node helpers/browser.cjs snapshot
 *   FEATURE=analyze-results node helpers/browser.cjs analyze AAPL
 *   FEATURE=home-search node helpers/browser.cjs check-issues
 *
 * check-issues FAILS (exit 1) when the Next.js overlay / badge shows a visible
 * "1 Issue" / "N Issues" (data-error=true). A prove that ignores that badge is invalid.
 *
 * If Playwright/Chromium is missing, writes browser-skipped.txt and exits 0 for
 * snapshot/analyze (HTTP proof remains valid). For check-issues, missing Playwright
 * exits 2 (hard-flag: issues gate not run).
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

/**
 * Detect Next.js Dev Tools "N Issues" badge / error indicator.
 * Prefer DOM attrs on [data-next-badge]; also scan visible text + open shadow roots.
 */
async function detectNextIssues(page) {
  // Give the badge a moment to hydrate after navigation / HMR.
  await page.waitForTimeout(800);
  return page.evaluate(() => {
    function collectShadowText(root, depth) {
      if (!root || depth > 6) return '';
      let text = '';
      const walk = (node, d) => {
        if (!node || d > 6) return;
        if (node.nodeType === 3) {
          text += node.textContent || '';
          return;
        }
        if (node.nodeType !== 1) return;
        if (node.shadowRoot) walk(node.shadowRoot, d + 1);
        const children = node.childNodes || [];
        for (let i = 0; i < children.length; i++) walk(children[i], d + 1);
      };
      walk(root, depth);
      return text;
    }

    const badges = Array.from(document.querySelectorAll('[data-next-badge]'));
    const badgeInfos = badges.map((el) => ({
      error: el.getAttribute('data-error'),
      errorExpanded: el.getAttribute('data-error-expanded'),
      status: el.getAttribute('data-status'),
      text: ((el.innerText || el.textContent || '') + '').trim(),
      aria: el.getAttribute('aria-label') || '',
    }));

    const roots = Array.from(
      document.querySelectorAll('[data-next-badge-root], nextjs-portal, [data-nextjs-toast]')
    );
    let shadowBlob = '';
    for (const r of roots) shadowBlob += ' ' + collectShadowText(r, 0);

    const bodyText = (document.body && document.body.innerText) || '';
    const blob = [bodyText, shadowBlob, ...badgeInfos.map((b) => `${b.text} ${b.aria}`)].join('\n');
    const issueRe = /\b(\d+)\s+Issues?\b/i;
    const m = blob.match(issueRe);

    const errorBadge = badgeInfos.find((b) => b.error === 'true');
    const issueCount = m ? Number(m[1]) : errorBadge ? 1 : 0;
    const hasIssues = Boolean(errorBadge) || (m !== null && issueCount > 0);

    return {
      hasIssues,
      issueCount: hasIssues ? issueCount || 1 : 0,
      matchText: m ? m[0] : '',
      badgeInfos,
      errorBadge: Boolean(errorBadge),
      note: hasIssues
        ? 'Next.js issues badge/overlay visible'
        : 'no Next.js issues badge text / data-error=true',
    };
  });
}

async function writeIssueArtifacts(outDir, label, detection, page) {
  const lines = [
    `NEXT ISSUE CHECK (${label})`,
    `hasIssues=${detection.hasIssues}`,
    `issueCount=${detection.issueCount}`,
    `matchText=${detection.matchText || '(none)'}`,
    `errorBadge=${detection.errorBadge}`,
    `note=${detection.note}`,
    `badges=${JSON.stringify(detection.badgeInfos || [])}`,
    '',
  ];
  fs.writeFileSync(path.join(outDir, 'next-issue.txt'), lines.join('\n'));
  fs.writeFileSync(path.join(outDir, 'next-issue-raw.json'), JSON.stringify(detection, null, 2));
  try {
    await page.screenshot({ path: path.join(outDir, 'next-issue.png'), fullPage: true });
    const badge = page.locator('[data-next-badge]').first();
    if (await badge.count()) {
      await badge.screenshot({ path: path.join(outDir, 'next-issue-badge-corner.png') }).catch(() => {});
    }
  } catch {
    /* screenshots are best-effort */
  }
}

(async () => {
  const run = loadRun();
  const origin = process.env.FRONTEND_ORIGIN || run.FRONTEND_ORIGIN;
  refuseOrigin(origin);

  const cmd = process.argv[2] || 'snapshot';
  const feature = process.env.FEATURE || (cmd === 'analyze' ? 'analyze-results' : 'home-search');
  const outDir = path.join(artifactsDir, feature);
  fs.mkdirSync(outDir, { recursive: true });

  const pw = loadPlaywright();
  if (!pw || !pw.chromium) {
    const msg = 'playwright module not importable; HTTP proof remains valid but Next issues badge gate did not run';
    fs.writeFileSync(path.join(outDir, 'browser-skipped.txt'), msg + '\n');
    console.log(`browser skipped: ${msg}`);
    if (cmd === 'check-issues') {
      console.error('NEXT_ISSUES_CHECK=skipped (Playwright missing); prove that ignores this gate is invalid');
      process.exit(2);
    }
    process.exit(0);
  }

  let browser;
  try {
    browser = await pw.chromium.launch({ headless: true });
  } catch (err) {
    const msg = String(err && err.message ? err.message : err);
    fs.writeFileSync(path.join(outDir, 'browser-skipped.txt'), msg);
    console.log(`browser skipped (chromium not installed): ${msg}`);
    if (cmd === 'check-issues') {
      console.error('NEXT_ISSUES_CHECK=skipped (Chromium missing); prove that ignores this gate is invalid');
      process.exit(2);
    }
    process.exit(0);
  }

  const page = await browser.newPage();
  try {
    await page.goto(origin + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const h1 = await page.locator('h1').first().textContent();

    if (cmd === 'check-issues') {
      const detection = await detectNextIssues(page);
      await writeIssueArtifacts(outDir, 'check-issues', detection, page);
      if (detection.hasIssues) {
        console.error(
          `NEXT_ISSUES_FAIL: visible Next issues badge (${detection.matchText || 'data-error=true'}; count=${detection.issueCount})`
        );
        process.exit(1);
      }
      console.log('NEXT_ISSUES_CHECK=pass (no visible Issues badge)');
      process.exit(0);
    }

    const shot = path.join(outDir, `${cmd === 'analyze' ? 'analyze' : 'snapshot'}.png`);
    await page.screenshot({ path: shot, fullPage: true });
    fs.writeFileSync(path.join(outDir, `${cmd === 'analyze' ? 'analyze' : 'snapshot'}.h1.txt`), String(h1 || '').trim() + '\n');

    // Always gate on Next issues for snapshot / analyze — ignoring the badge is invalid.
    let detection = await detectNextIssues(page);
    await writeIssueArtifacts(outDir, cmd === 'analyze' ? 'before-analyze' : 'snapshot', detection, page);
    if (detection.hasIssues) {
      console.error(
        `NEXT_ISSUES_FAIL: visible Next issues badge (${detection.matchText || 'data-error=true'}; count=${detection.issueCount})`
      );
      process.exit(1);
    }

    if (cmd === 'analyze') {
      const ticker = (process.argv[3] || 'AAPL').toUpperCase();
      await page.locator('input[placeholder="AAPL or TSLA"]').fill(ticker);
      await page.locator('button', { hasText: 'Analyze' }).click();
      await page.waitForTimeout(2000);
      const html = await page.content();
      fs.writeFileSync(path.join(outDir, 'after-click.html'), html);
      await page.screenshot({ path: path.join(outDir, 'after-click.png'), fullPage: true });
      const hasTable = html.includes('5-Year Financial Metrics');
      fs.writeFileSync(
        path.join(outDir, 'after-click.meta.txt'),
        [
          `ticker=${ticker}`,
          `h1=${String(h1 || '').trim()}`,
          `has_table=${hasTable}`,
          `note=Table rows in page.tsx are hardcoded sample billions; KPI values come from /api/analyze JSON.`,
        ].join('\n') + '\n'
      );
      detection = await detectNextIssues(page);
      await writeIssueArtifacts(outDir, 'after-analyze', detection, page);
      if (detection.hasIssues) {
        console.error(
          `NEXT_ISSUES_FAIL after analyze: visible Next issues badge (${detection.matchText || 'data-error=true'}; count=${detection.issueCount})`
        );
        process.exit(1);
      }
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
