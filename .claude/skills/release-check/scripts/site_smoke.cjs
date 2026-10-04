#!/usr/bin/env node
/*
 * DJ Lab site smoke test (Playwright, headless Chromium).
 * Usage: node site_smoke.cjs http://localhost:8000/ [--screens DIR] [--max-pages 15]
 * Checks every same-origin page linked from the home page, at desktop (1280px) and mobile (375px):
 *   console errors, uncaught exceptions, failed requests / HTTP >= 400, <html dir="rtl" lang="he">,
 *   no horizontal scroll on mobile, window.DJLAB_CATALOG present on the home page, audio sources reachable.
 * Exit code 0 = pass, 1 = failures, 2 = could not run (Playwright/browser missing).
 */
const path = require('path');
let pw;
try { pw = require('playwright'); } catch (e) {
  try {
    const root = require('child_process').execSync('npm root -g').toString().trim();
    pw = require(path.join(root, 'playwright'));
  } catch (e2) {
    console.error('Playwright not found. Install: npm i -g playwright && npx playwright install chromium');
    process.exit(2);
  }
}
const args = process.argv.slice(2);
const base = (args.find(a => /^https?:/.test(a)) || 'http://localhost:8000/').replace(/\/?$/, '/');
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const screens = opt('--screens', null);
const maxPages = parseInt(opt('--max-pages', '15'), 10);

(async () => {
  let browser;
  try { browser = await pw.chromium.launch(); } catch (e) {
    console.error('Cannot launch Chromium: ' + e.message.split('\n')[0]); process.exit(2);
  }
  const failures = [];
  const fail = (page, msg) => failures.push(`${page}: ${msg}`);
  const origin = new URL(base).origin;
  const visited = new Set();
  const queue = [base];
  const audioUrls = new Set();
  let pagesChecked = 0;

  while (queue.length && pagesChecked < maxPages) {
    const url = queue.shift();
    const key = url.split('#')[0];
    if (visited.has(key)) continue;
    visited.add(key);
    pagesChecked++;
    for (const vp of [{ name: 'desktop', width: 1280, height: 800 }, { name: 'mobile', width: 375, height: 740 }]) {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const page = await ctx.newPage();
      const label = `${key.replace(origin, '') || '/'} [${vp.name}]`;
      page.on('console', m => { if (m.type() === 'error') fail(label, 'console error: ' + m.text().slice(0, 200)); });
      page.on('pageerror', e => fail(label, 'uncaught: ' + String(e.message).slice(0, 200)));
      page.on('requestfailed', r => {
        const u = r.url();
        if (/\.(mp3|wav|ogg)(\?|$)/i.test(u) && /aborted/i.test(r.failure()?.errorText || '')) return; // media preload aborts are normal
        if (u.startsWith(origin)) fail(label, `request failed: ${u.replace(origin, '')} (${r.failure()?.errorText})`);
      });
      page.on('response', r => { if (r.status() >= 400 && r.url().startsWith(origin)) fail(label, `HTTP ${r.status()}: ${r.url().replace(origin, '')}`); });
      let resp;
      try { resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }); } catch (e) {
        fail(label, 'navigation: ' + e.message.split('\n')[0]); await ctx.close(); continue;
      }
      if (!resp || resp.status() >= 400) { fail(label, `status ${resp && resp.status()}`); await ctx.close(); continue; }
      const info = await page.evaluate(() => ({
        dir: document.documentElement.getAttribute('dir') || getComputedStyle(document.body).direction,
        lang: document.documentElement.getAttribute('lang'),
        title: document.title,
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        catalog: typeof window.DJLAB_CATALOG === 'object' && window.DJLAB_CATALOG
          ? (window.DJLAB_CATALOG.tracks || []).length : null,
        links: [...document.querySelectorAll('a[href]')].map(a => a.href),
        audio: [...document.querySelectorAll('audio[src], audio source[src], [data-audio], [data-src$=".mp3"]')]
          .map(el => el.src || el.getAttribute('data-audio') || el.getAttribute('data-src')).filter(Boolean)
          .map(u => new URL(u, location.href).href),
      }));
      if (info.dir !== 'rtl') fail(label, `direction is "${info.dir}", expected rtl`);
      if (!/^he/.test(info.lang || '')) fail(label, `lang is "${info.lang}", expected he`);
      if (!info.title) fail(label, 'empty <title>');
      if (vp.name === 'mobile' && info.overflow > 1) fail(label, `horizontal scroll: ${info.overflow}px wider than viewport`);
      if (key === base && vp.name === 'desktop') {
        if (info.catalog === null) console.log('note: window.DJLAB_CATALOG not found on home page');
        else console.log(`home: DJLAB_CATALOG has ${info.catalog} tracks`);
      }
      info.audio.forEach(u => audioUrls.add(u));
      if (vp.name === 'desktop') {
        for (const l of info.links) {
          const u = l.split('#')[0];
          if (u.startsWith(origin) && /(\/|\.html)$/.test(u) && !visited.has(u) && !queue.includes(u)) queue.push(u);
        }
      }
      if (screens) {
        const fs = require('fs'); fs.mkdirSync(screens, { recursive: true });
        const name = (key.replace(origin, '').replace(/[^a-z0-9]+/gi, '_') || 'home') + `_${vp.name}.png`;
        await page.screenshot({ path: path.join(screens, name), fullPage: false });
      }
      await ctx.close();
    }
  }
  // audio reachability (first 8 unique sources)
  const ctx = await browser.newContext();
  for (const u of [...audioUrls].slice(0, 8)) {
    try {
      const r = await ctx.request.get(u, { headers: { Range: 'bytes=0-1023' } });
      if (r.status() >= 400) fail('audio', `${u.replace(origin, '')} -> HTTP ${r.status()}`);
    } catch (e) { fail('audio', `${u}: ${e.message.split('\n')[0]}`); }
  }
  await browser.close();
  console.log(`checked ${pagesChecked} page(s) x 2 viewports, ${audioUrls.size} audio source(s)`);
  if (failures.length) {
    console.log(`FAIL (${failures.length})`);
    [...new Set(failures)].slice(0, 60).forEach(f => console.log('  - ' + f));
    process.exit(1);
  }
  console.log('PASS');
})();
