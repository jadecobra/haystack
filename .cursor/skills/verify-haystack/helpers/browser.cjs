#!/usr/bin/env node
/**
 * Skill-local optional Playwright driver for the isolated frontend origin.
 * Does NOT start Next, does NOT use ports 3000 or 8000.
 *
 * Usage (after helpers/launch):
 *   FEATURE=home-search node helpers/browser.cjs snapshot
 *   FEATURE=analyze-results node helpers/browser.cjs analyze AAPL
 *   FEATURE=home-search node helpers/browser.cjs check-issues
 *   CLICK_ORIGIN=https://… node helpers/browser.cjs click-through
 *
 * check-issues [path...] (default "/") FAILS (exit 1) when the Next.js overlay / badge
 * shows a visible "1 Issue" / "N Issues" (data-error=true), or when console error /
 * pageerror fires (except "Failed to load resource"). Ignoring that gate is invalid.
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

function existingChromiumExecutables() {
  const fromEnv = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const found = [];
  if (fromEnv && fs.existsSync(fromEnv)) found.push(fromEnv);
  const cache = path.join(
    process.env.HOME || '',
    'Library',
    'Caches',
    'ms-playwright',
  );
  if (!fs.existsSync(cache)) return found;
  const names = fs.readdirSync(cache).filter((n) => n.startsWith('chromium'));
  names.sort().reverse();
  for (const name of names) {
    const root = path.join(cache, name);
    const walk = [root];
    for (let i = 0; i < walk.length; i++) {
      let entries;
      try {
        entries = fs.readdirSync(walk[i], { withFileTypes: true });
      } catch {
        continue;
      }
      for (const ent of entries) {
        const p = path.join(walk[i], ent.name);
        if (ent.isDirectory()) {
          if (walk.length < 80) walk.push(p);
          continue;
        }
        if (
          ent.name === 'chrome-headless-shell' ||
          ent.name === 'headless_shell' ||
          ent.name === 'chrome' ||
          ent.name === 'Chromium'
        ) {
          found.push(p);
        }
      }
    }
  }
  return [...new Set(found)];
}

async function launchChromium(pw) {
  try {
    return await pw.chromium.launch({ headless: true });
  } catch (first) {
    const tried = [];
    for (const executablePath of existingChromiumExecutables()) {
      tried.push(executablePath);
      try {
        return await pw.chromium.launch({ headless: true, executablePath });
      } catch {
        /* try next binary */
      }
    }
    const extra = tried.length
      ? `; also failed executablePath fallbacks: ${tried.join(', ')}`
      : '';
    const err = new Error(
      `${first && first.message ? first.message : first}${extra}`,
    );
    throw err;
  }
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

function issueArtifactNames(routePath) {
  // "/" keeps the historical filenames. Other routes get a sanitized suffix.
  if (!routePath || routePath === '/') {
    return {
      txt: 'next-issue.txt',
      json: 'next-issue-raw.json',
      png: 'next-issue.png',
      badge: 'next-issue-badge-corner.png',
    };
  }
  const safe = String(routePath).replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'path';
  return {
    txt: `next-issue-${safe}.txt`,
    json: `next-issue-${safe}-raw.json`,
    png: `next-issue-${safe}.png`,
    badge: `next-issue-${safe}-badge-corner.png`,
  };
}

function isIgnoredConsoleError(text) {
  return /Failed to load resource/i.test(text);
}

function redactSecrets(text) {
  let out = String(text);
  for (const key of ['VERCEL_OIDC_TOKEN', 'VERCEL_AUTOMATION_BYPASS_SECRET']) {
    const value = process.env[key];
    if (value && value.length > 0) out = out.split(value).join('[redacted]');
  }
  return out;
}

function previewHeaders() {
  const headers = {};
  const oidc = process.env.VERCEL_OIDC_TOKEN;
  if (oidc) headers['x-vercel-trusted-oidc-idp-token'] = oidc;
  const bypass = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
  if (bypass) {
    headers['x-vercel-protection-bypass'] = bypass;
    headers['x-vercel-set-bypass-cookie'] = 'true';
  }
  return headers;
}

function isEdgarTimeoutError(err) {
  return Boolean(err && err.edgarTimeout);
}

function edgarTimeout(message) {
  const err = new Error(message);
  err.edgarTimeout = true;
  return err;
}

const CLICK_WIDTHS = [390, 1440];
const CLICK_METRICS_TIMEOUT_MS = 180000;

function clickShotName(width, id) {
  const safe = String(id).replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'path';
  return `${width}-${safe}.png`;
}

async function shoot(page, outDir, width, id) {
  const file = path.join(outDir, clickShotName(width, id));
  await page.screenshot({ path: file, fullPage: true }).catch(() => {});
  return file;
}

function attachClickWatch(page, bag) {
  const onConsole = (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (isIgnoredConsoleError(text)) return;
    bag.consoleErrors.push(redactSecrets(text));
  };
  const onPageError = (err) => {
    bag.consoleErrors.push(redactSecrets(String(err && err.message ? err.message : err)));
  };
  const started = new WeakSet();
  const onRequest = (req) => {
    started.add(req);
  };
  const onResponse = (res) => {
    if (!started.has(res.request())) return;
    let url = '';
    try {
      url = res.url();
    } catch {
      return;
    }
    const status = res.status();
    let pathname = '';
    try {
      pathname = new URL(url).pathname;
    } catch {
      pathname = url;
    }
    const interesting = pathname.startsWith('/api/') || pathname.startsWith('/analyze');
    if (interesting || status >= 400) {
      bag.responses.push({ url: pathname || url, status, interesting });
    }
  };
  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('request', onRequest);
  page.on('response', onResponse);
  return () => {
    page.off('console', onConsole);
    page.off('pageerror', onPageError);
    page.off('request', onRequest);
    page.off('response', onResponse);
  };
}

async function layoutProblem(page, width) {
  if (width !== 390) return null;
  return page.evaluate(() => {
    const overflowing = [];
    const nodes = [document.documentElement, document.body, ...document.querySelectorAll('body *')];
    for (const el of nodes) {
      if (!el) continue;
      const style = getComputedStyle(el);
      const hides = style.overflowX === 'hidden' || style.overflowX === 'clip';
      if (!hides && el !== document.documentElement && el !== document.body) continue;
      if (el.clientWidth < 8) continue;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (cls.split(/\s+/).includes('sr-only')) continue;
      if (el.scrollWidth <= el.clientWidth + 8) continue;
      let ancestor = el.parentElement;
      let insideScroller = false;
      while (ancestor) {
        const parentStyle = getComputedStyle(ancestor);
        const scrolls = parentStyle.overflowX === 'auto' || parentStyle.overflowX === 'scroll';
        if (scrolls && ancestor.clientWidth > 0 && ancestor.scrollWidth > ancestor.clientWidth + 8) {
          insideScroller = true;
          break;
        }
        ancestor = ancestor.parentElement;
      }
      if (insideScroller) continue;
      overflowing.push(el.tagName);
    }
    if (overflowing.length === 0) return null;
    return 'content overflows or is clipped at mobile width';
  });
}

async function imageProblem(page) {
  return page.evaluate(() => {
    const images = Array.from(document.querySelectorAll('img'));
    for (const img of images) {
      if (!img.complete || img.naturalWidth === 0) {
        return `image did not load (${img.alt || img.getAttribute('src') || 'img'})`;
      }
    }
    return null;
  });
}

async function assertHealthy(page, bag, width, opts) {
  const detection = await detectNextIssues(page);
  if (detection.hasIssues) {
    throw new Error(`Next.js issues badge or error overlay (${detection.matchText || 'data-error=true'})`);
  }
  if (bag.consoleErrors.length > 0) {
    throw new Error(`console error: ${bag.consoleErrors[0]}`);
  }
  for (const res of bag.responses) {
    if (res.status < 400) continue;
    if (opts && opts.allowApi404 && res.url.includes('/api/analyze/')) continue;
    if (!res.interesting && !res.url.startsWith('/api/')) continue;
    const err = new Error(`request ${res.url} status ${res.status}`);
    if (res.status === 408 || res.status === 504) err.edgarTimeout = true;
    throw err;
  }
  if (!opts || !opts.allowAlert) {
    const alertText = ((await page.locator('p[role="alert"]').first().textContent({ timeout: 500 }).catch(() => '')) || '').trim();
    if (alertText) {
      if (/taking too long|timed out|timeout/i.test(alertText)) throw edgarTimeout('EDGAR timeout');
      throw new Error(`valid path shows an error message: ${alertText}`);
    }
  }
  const brokenImage = await imageProblem(page);
  if (brokenImage) throw new Error(brokenImage);
  const clipped = await layoutProblem(page, width);
  if (clipped) throw new Error(clipped);
}

async function waitForMetrics(page, timeoutMs, bag) {
  const started = Date.now();
  let heading = '';
  while (Date.now() - started <= timeoutMs) {
    const analyze = (bag && bag.responses ? bag.responses : []).filter((res) => res.url.includes('/api/analyze/'));
    const hard = analyze.find((res) => res.status >= 400 && res.status !== 408 && res.status !== 504);
    if (hard) throw new Error(`request ${hard.url} status ${hard.status}`);
    const slow = analyze.find((res) => res.status === 408 || res.status === 504);
    if (slow) throw edgarTimeout(`EDGAR timeout status ${slow.status}`);
    const alertText = ((await page.locator('p[role="alert"]').first().textContent({ timeout: 500 }).catch(() => '')) || '').trim();
    if (alertText && /taking too long|timed out|timeout/i.test(alertText)) throw edgarTimeout('EDGAR timeout');
    if (alertText) {
      const live = (bag && bag.responses ? bag.responses : []).filter((res) => res.url.includes('/api/analyze/'));
      const hard = live.find((res) => res.status >= 400 && res.status !== 408 && res.status !== 504);
      if (hard) throw new Error(`request ${hard.url} status ${hard.status}`);
      const slow = live.find((res) => res.status === 408 || res.status === 504);
      if (slow) throw edgarTimeout(`EDGAR timeout status ${slow.status}`);
      throw new Error(`valid path shows an error message: ${alertText}`);
    }
    heading = ((await page.locator('[data-testid="company-heading"]').first().textContent({ timeout: 500 }).catch(() => '')) || '').trim();
    if (heading && /source\s*:/i.test(heading)) break;
    heading = '';
    await page.waitForTimeout(200);
  }
  if (!heading) throw edgarTimeout('EDGAR timeout waiting for metrics table');
  if (/taking too long/i.test(heading)) throw edgarTimeout('EDGAR timeout');
  const alertText = ((await page.locator('p[role="alert"]').first().textContent({ timeout: 500 }).catch(() => '')) || '').trim();
  if (alertText && /taking too long|timed out|timeout/i.test(alertText)) {
    throw edgarTimeout('EDGAR timeout');
  }
  if (alertText) throw new Error(`valid path shows an error message: ${alertText}`);
  if (!/·|Apple/.test(heading)) throw new Error('company name is missing');
  const tableCount = await page.locator('table').count();
  if (tableCount < 1) throw new Error('metrics table is missing');
  const cells = await page.locator('table td').allTextContents();
  const values = cells.map((cell) => cell.trim()).filter(Boolean);
  if (values.length === 0) throw new Error('metrics table has no rows');
  const blank = values.every((cell) => cell === '—' || cell === '-' || /^nan$/i.test(cell));
  if (blank) throw new Error('metrics table values are empty');
}

async function runClickThrough(options) {
  const origin = String(options.origin || '').replace(/\/$/, '');
  refuseOrigin(origin);
  const outDir = options.outDir;
  fs.mkdirSync(outDir, { recursive: true });
  const widths = options.widths || CLICK_WIDTHS;
  const metricsTimeoutMs = options.metricsTimeoutMs || CLICK_METRICS_TIMEOUT_MS;
  const pw = options.playwright || loadPlaywright();
  if (!pw || !pw.chromium) {
    console.error('click-through FAIL path=setup width=0 problem=Playwright is missing');
    return 2;
  }
  let browser;
  try {
    browser = await launchChromium(pw);
  } catch (err) {
    console.error(`click-through FAIL path=setup width=0 problem=${redactSecrets(err && err.message ? err.message : err)}`);
    return 2;
  }
  const results = [];
  try {
    const context = await browser.newContext({
      extraHTTPHeaders: options.headers || {},
      viewport: { width: widths[0], height: 900 },
    });
    const page = await context.newPage();
    if (options.installRoutes) await options.installRoutes(page);
    page.setDefaultTimeout(15000);

    const record = async (width, id, fn, edgar) => {
      const runOnce = async () => {
        const bag = { consoleErrors: [], responses: [] };
        const detach = attachClickWatch(page, bag);
        try {
          await fn(bag);
          await assertHealthy(page, bag, width, {
            allowApi404: id === 'invalid-ticker',
            allowAlert: id === 'invalid-ticker',
          });
        } finally {
          detach();
          await shoot(page, outDir, width, id);
        }
      };
      try {
        if (!edgar) {
          await runOnce();
        } else {
          try {
            await runOnce();
          } catch (err) {
            if (!isEdgarTimeoutError(err)) throw err;
            await runOnce();
            console.log(`click-through path=${id} width=${width} result=pass note=passed after retry`);
            results.push({ id, width, ok: true, retry: true });
            return;
          }
        }
        console.log(`click-through path=${id} width=${width} result=pass`);
        results.push({ id, width, ok: true });
      } catch (err) {
        const problem = isEdgarTimeoutError(err)
          ? 'two EDGAR timeouts'
          : redactSecrets(err && err.message ? err.message : err);
        console.log(`click-through path=${id} width=${width} result=fail problem=${problem}`);
        results.push({ id, width, ok: false, problem });
      }
    };

    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });

      await record(width, 'home', async () => {
        const response = await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (response && response.status() >= 400) throw new Error(`page status ${response.status()}`);
        await page.locator('img[alt="LongMuch"]').first().waitFor({ timeout: 15000 });
        const tickerInput = page.locator('input[placeholder="enter stock ticker e.g. AAPL"]');
        if ((await tickerInput.count()) < 1) throw new Error('ticker form is missing');
        const analyze = page.locator('button', { hasText: 'Analyze' });
        if ((await analyze.count()) < 1) throw new Error('ticker form is missing');
      }, false);

      await record(width, 'logo', async () => {
        const logoLink = page.locator('a[href="/"]', { has: page.locator('img[alt="LongMuch"]') }).first();
        if ((await logoLink.count()) < 1) throw new Error('logo link is missing');
        await logoLink.click();
        await page.waitForURL((url) => url.pathname === '/', { timeout: 15000 });
        if (new URL(page.url()).pathname !== '/') throw new Error('logo link opened the wrong page');
      }, false);

      await record(width, 'analyze', async (bag) => {
        await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.locator('input[placeholder="enter stock ticker e.g. AAPL"]').fill('AAPL');
        await page.locator('button', { hasText: 'Analyze' }).click();
        await waitForMetrics(page, metricsTimeoutMs, bag);
        const bad = bag.responses.find((res) => res.url.includes('/api/analyze/') && (res.status === 408 || res.status === 504));
        if (bad) throw edgarTimeout(`EDGAR timeout status ${bad.status}`);
      }, true);

      await record(width, 'deep-link', async (bag) => {
        const response = await page.goto(`${origin}/AAPL`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (response && response.status() >= 400) throw new Error(`page status ${response.status()}`);
        await waitForMetrics(page, metricsTimeoutMs, bag);
        const bad = bag.responses.find((res) => res.url.includes('/api/analyze/') && (res.status === 408 || res.status === 504));
        if (bad) throw edgarTimeout(`EDGAR timeout status ${bad.status}`);
      }, true);

      await record(width, 'invalid-ticker', async () => {
        const response = await page.goto(`${origin}/ZZZZQ`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (response && response.status() >= 400) throw new Error(`page status ${response.status()}`);
        let alertText = '';
        try {
          await page.waitForFunction(
            () => /find that ticker|check the symbol/i.test(document.body ? document.body.innerText : ''),
            null,
            { timeout: metricsTimeoutMs },
          );
          alertText = ((await page.locator('p[role="alert"]').allTextContents()).join(' ') || '').trim();
          if (!alertText) {
            alertText = ((await page.locator('body').innerText()) || '').trim();
          }
        } catch (err) {
          if (isEdgarTimeoutError(err)) throw err;
          throw edgarTimeout('EDGAR timeout waiting for invalid-ticker error');
        }
        if (/taking too long|timed out|timeout/i.test(alertText)) throw edgarTimeout('EDGAR timeout');
        if (!/find that ticker|couldn.t analyze|check the symbol/i.test(alertText)) {
          throw new Error(`invalid ticker does not show its error message (${alertText || 'empty'})`);
        }
      }, true);

      await record(width, 'sector', async (bag) => {
        await page.goto(`${origin}/AAPL`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await waitForMetrics(page, metricsTimeoutMs, bag);
        const sectorLink = page.locator('a[href^="/sector/"]').first();
        if ((await sectorLink.count()) < 1) throw new Error('sector link is missing on the AAPL result');
        const href = await sectorLink.getAttribute('href');
        await sectorLink.click();
        await page.waitForURL((url) => url.pathname.startsWith('/sector/'), { timeout: 20000 });
        if (!new URL(page.url()).pathname.startsWith('/sector/')) {
          throw new Error(`sector link opened the wrong page (${href})`);
        }
        await page.locator('[data-testid="sector-row-link"]').first().waitFor({ timeout: 20000 });
        const peers = await page.locator('[data-testid="sector-row-link"]').count();
        if (peers < 1) throw new Error('sector page peer list is empty');
      }, true);

      await record(width, 'screen', async () => {
        const response = await page.goto(`${origin}/screen`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (response && response.status() >= 400) throw new Error(`page status ${response.status()}`);
        await page.locator('[data-testid="screen-oe-yield"]').first().waitFor({ timeout: 30000 });
        const rows = await page.locator('[data-testid="screen-oe-yield"]').count();
        if (rows < 1) throw new Error('screen table has no rows');
        const alertText = ((await page.locator('p[role="alert"]').first().textContent({ timeout: 1000 }).catch(() => '')) || '').trim();
        if (alertText) throw new Error(`valid path shows an error message: ${alertText}`);
      }, false);

      await record(width, 'docs', async () => {
        const response = await page.goto(`${origin}/docs`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (response && response.status() >= 400) throw new Error(`page status ${response.status()}`);
        const h1 = ((await page.locator('h1').first().textContent()) || '').trim();
        if (!/How metrics are calculated/.test(h1)) throw new Error('docs text is missing');
      }, false);

      await record(width, 'header-footer-links', async () => {
        await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        const hrefs = await page.locator('nav[data-testid="site-nav"] a, a[href="/"]:has(img[alt="LongMuch"])').evaluateAll((els) => {
          const out = [];
          for (const el of els) {
            const href = el.getAttribute('href');
            if (href && href.startsWith('/') && !out.includes(href)) out.push(href);
          }
          return out;
        });
        if (hrefs.length < 2) throw new Error('header or footer links are missing');
        for (const href of hrefs) {
          const response = await page.goto(`${origin}${href}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
          const status = response ? response.status() : 0;
          if (status >= 400) throw new Error(`link ${href} status ${status}`);
          const pathname = new URL(page.url()).pathname;
          const expected = href.split('?')[0];
          if (pathname !== expected && !(expected === '/' && pathname === '/')) {
            throw new Error(`link ${href} opened the wrong page ${pathname}`);
          }
          const title = await page.title();
          const bodyText = ((await page.locator('body').innerText()) || '').slice(0, 400);
          if (/404|page could not be found|this page does not exist/i.test(`${title}\n${bodyText}`) && expected !== '/') {
            throw new Error(`link ${href} opened a 404`);
          }
        }
      }, false);
    }
  } finally {
    await browser.close();
  }
  const failed = results.filter((row) => !row.ok);
  return failed.length === 0 ? 0 : 1;
}

module.exports = {
  runClickThrough,
  detectNextIssues,
  loadPlaywright,
  launchChromium,
  redactSecrets,
  previewHeaders,
};

async function writeIssueArtifacts(outDir, label, detection, page, routePath) {
  const names = issueArtifactNames(routePath);
  const lines = [
    `NEXT ISSUE CHECK (${label})`,
    `path=${routePath || '/'}`,
    `hasIssues=${detection.hasIssues}`,
    `issueCount=${detection.issueCount}`,
    `matchText=${detection.matchText || '(none)'}`,
    `errorBadge=${detection.errorBadge}`,
    `consoleErrors=${(detection.consoleErrors || []).length}`,
    `note=${detection.note}`,
    `badges=${JSON.stringify(detection.badgeInfos || [])}`,
    `console=${JSON.stringify(detection.consoleErrors || [])}`,
    '',
  ];
  fs.writeFileSync(path.join(outDir, names.txt), lines.join('\n'));
  fs.writeFileSync(path.join(outDir, names.json), JSON.stringify(detection, null, 2));
  try {
    await page.screenshot({ path: path.join(outDir, names.png), fullPage: true });
    const badge = page.locator('[data-next-badge]').first();
    if (await badge.count()) {
      await badge.screenshot({ path: path.join(outDir, names.badge) }).catch(() => {});
    }
  } catch {
    /* screenshots are best-effort */
  }
}

/**
 * Navigate one path, collect console errors + pageerrors from navigation start,
 * wait for ticker auto-analyze, then run the badge detector.
 */
async function checkIssuesOnPath(page, origin, routePath) {
  const consoleErrors = [];
  const onConsole = (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (isIgnoredConsoleError(text)) return;
    consoleErrors.push(text);
  };
  const onPageError = (err) => {
    consoleErrors.push(String(err && err.message ? err.message : err));
  };
  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  try {
    const target = routePath.startsWith('/') ? routePath : `/${routePath}`;
    await page.goto(origin + target, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);
    const detection = await detectNextIssues(page);
    detection.consoleErrors = consoleErrors.slice();
    detection.path = target;
    return detection;
  } finally {
    page.off('console', onConsole);
    page.off('pageerror', onPageError);
  }
}

if (require.main === module) (async () => {
  const cmd = process.argv[2] || 'snapshot';
  if (cmd === 'click-through') {
    const origin = process.env.CLICK_ORIGIN || process.env.FRONTEND_ORIGIN || (() => {
      const run = loadRun();
      return run.FRONTEND_ORIGIN;
    })();
    const outDir = process.env.CLICK_OUT_DIR || path.join(artifactsDir, 'click-through');
    const code = await runClickThrough({
      origin,
      outDir,
      headers: previewHeaders(),
      playwright: loadPlaywright(),
    });
    process.exit(code);
  }

  const run = loadRun();
  const origin = process.env.FRONTEND_ORIGIN || run.FRONTEND_ORIGIN;
  refuseOrigin(origin);

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
    browser = await launchChromium(pw);
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
      const paths = process.argv.slice(3).filter(Boolean);
      const routePaths = paths.length > 0 ? paths : ['/'];
      let failed = false;
      for (const routePath of routePaths) {
        const detection = await checkIssuesOnPath(page, origin, routePath);
        await writeIssueArtifacts(outDir, 'check-issues', detection, page, detection.path);
        const consoleCount = (detection.consoleErrors || []).length;
        console.log(
          `NEXT_ISSUES_CHECK path=${detection.path} badge=${detection.issueCount || 0} console_errors=${consoleCount}`
        );
        if (detection.hasIssues || consoleCount > 0) failed = true;
      }
      if (failed) {
        console.error('NEXT_ISSUES_FAIL: visible Next issues badge or console error');
        process.exit(1);
      }
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
      await page.route('**/api/analyze/**', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        await route.continue();
      });
      await page.locator('input[placeholder="enter stock ticker e.g. AAPL"]').fill(ticker);
      await page.locator('button', { hasText: 'Analyze' }).click();
      await page.waitForSelector('[data-testid="analyze-wait-status"]', { timeout: 5000 });
      const waitHtml = await page.content();
      fs.writeFileSync(path.join(outDir, 'wait.html'), waitHtml);
      await page.screenshot({ path: path.join(outDir, 'wait.png'), fullPage: true });
      const waitStatus = (await page.locator('[data-testid="analyze-wait-status"]').textContent()) || '';
      const waitElapsed = (await page.locator('[data-testid="analyze-wait-elapsed"]').textContent()) || '';
      const groupCount = await page.locator('th[scope="colgroup"]').count();
      const hasSkeleton = waitHtml.includes('Financial Metrics') && waitHtml.includes('—');
      const forbiddenWait = /cold start|waking|Render|API/i.test(waitStatus);
      fs.writeFileSync(
        path.join(outDir, 'wait.meta.txt'),
        [
          `ticker=${ticker}`,
          `status=${waitStatus.trim()}`,
          `elapsed=${waitElapsed.trim()}`,
          `group_headers=${groupCount}`,
          `has_skeleton=${hasSkeleton}`,
          `forbidden_copy=${forbiddenWait}`,
        ].join('\n') + '\n'
      );
      if (forbiddenWait) {
        console.error('WAIT_UX_FAIL: forbidden copy in status line');
        process.exit(1);
      }
      await page.waitForFunction(
        () => document.body && document.body.innerText.includes('source : EDGAR'),
        null,
        { timeout: 180000 },
      );
      const html = await page.content();
      fs.writeFileSync(path.join(outDir, 'after-click.html'), html);
      await page.screenshot({ path: path.join(outDir, 'after-click.png'), fullPage: true });
      const hasTable = html.includes('Financial Metrics');
      const readyGroups = await page.locator('th[scope="colgroup"]').count();
      fs.writeFileSync(
        path.join(outDir, 'after-click.meta.txt'),
        [
          `ticker=${ticker}`,
          `h1=${String(h1 || '').trim()}`,
          `has_table=${hasTable}`,
          `ready_group_headers=${readyGroups}`,
          `wait_status=${waitStatus.trim()}`,
          `wait_elapsed=${waitElapsed.trim()}`,
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
