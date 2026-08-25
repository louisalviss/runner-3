#!/usr/bin/env node

import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target = (process.env.SITE2_URL || 'https://runner3-wp-a94b8fd2.wasmer.app/').replace(/\/$/, '/') ;
const out = process.env.SITE2_DIAG_OUT || '/tmp/site2-performance-diagnose.json';
const expectedHost = new URL(target).host;

function round(value) {
  return Number.isFinite(value) ? Math.round(value * 10) / 10 : null;
}

function extractCssUrls(value) {
  const urls = [];
  for (const match of String(value || '').matchAll(/url\(["']?([^"')]+)["']?\)/g)) urls.push(match[1]);
  return urls;
}

let browser;
try {
  const executablePath = [
    process.env.CHROME_PATH,
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  ].filter(Boolean).find((p) => fs.existsSync(p));
  if (!executablePath) throw new Error('Chrome executable not found');

  browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.__runner3Lcp = [];
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const el = entry.element;
          let style = null;
          let rect = null;
          if (el) {
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            style = {
              backgroundImage: cs.backgroundImage,
              backgroundSize: cs.backgroundSize,
              backgroundPosition: cs.backgroundPosition,
            };
            rect = { x: r.x, y: r.y, width: r.width, height: r.height };
          }
          window.__runner3Lcp.push({
            startTime: entry.startTime,
            renderTime: entry.renderTime,
            loadTime: entry.loadTime,
            size: entry.size,
            id: entry.id || '',
            url: entry.url || '',
            tag: el?.tagName || '',
            className: typeof el?.className === 'string' ? el.className : '',
            text: (el?.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 240),
            style,
            rect,
          });
        }
      }).observe({ type: 'largest-contentful-paint', buffered: true });
    } catch {}
  });

  const started = Date.now();
  const response = await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 120_000 });
  if (!response || response.status() >= 400) throw new Error(`Site2 homepage returned ${response?.status()}`);
  if (new URL(page.url()).host !== expectedHost) throw new Error(`Site2 host changed to ${page.url()}`);
  await page.waitForLoadState('networkidle', { timeout: 60_000 }).catch(() => {});
  await page.waitForTimeout(3500);

  const raw = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0];
    const resources = performance.getEntriesByType('resource').map((r) => ({
      name: r.name,
      initiatorType: r.initiatorType,
      startTime: r.startTime,
      duration: r.duration,
      transferSize: r.transferSize,
      encodedBodySize: r.encodedBodySize,
      decodedBodySize: r.decodedBodySize,
      responseStart: r.responseStart,
      responseEnd: r.responseEnd,
    }));
    const aboveFoldBackgrounds = [];
    for (const el of document.querySelectorAll('body *')) {
      const rect = el.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= innerHeight || rect.width < 80 || rect.height < 80) continue;
      const cs = getComputedStyle(el);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && cs.backgroundImage.includes('url(')) {
        aboveFoldBackgrounds.push({
          tag: el.tagName,
          className: typeof el.className === 'string' ? el.className : '',
          backgroundImage: cs.backgroundImage,
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 180),
        });
      }
    }
    const images = [...document.images].map((img) => {
      const r = img.getBoundingClientRect();
      return {
        src: img.currentSrc || img.src,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
        width: r.width,
        height: r.height,
        top: r.top,
        loading: img.loading,
        fetchPriority: img.fetchPriority,
      };
    });
    return {
      title: document.title,
      url: location.href,
      lcpEntries: window.__runner3Lcp || [],
      nav: nav ? {
        startTime: nav.startTime,
        responseStart: nav.responseStart,
        responseEnd: nav.responseEnd,
        domContentLoadedEventEnd: nav.domContentLoadedEventEnd,
        loadEventEnd: nav.loadEventEnd,
        transferSize: nav.transferSize,
        encodedBodySize: nav.encodedBodySize,
        decodedBodySize: nav.decodedBodySize,
      } : null,
      resources,
      aboveFoldBackgrounds,
      images,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
    };
  });

  const lcp = raw.lcpEntries.at(-1) || null;
  const bgUrls = raw.aboveFoldBackgrounds.flatMap((x) => extractCssUrls(x.backgroundImage));
  const lcpStyleUrls = extractCssUrls(lcp?.style?.backgroundImage);
  const heroUrl = lcp?.url || lcpStyleUrls[0] || bgUrls[0] || null;

  let hero = null;
  if (heroUrl) {
    const resolved = new URL(heroUrl, target).href;
    if (new URL(resolved).host === expectedHost) {
      const heroResponse = await fetch(resolved, { redirect: 'follow', headers: { 'cache-control': 'no-cache' } });
      const bytes = Buffer.from(await heroResponse.arrayBuffer()).byteLength;
      const dimensions = await page.evaluate(async (url) => {
        const image = new Image();
        const result = await new Promise((resolve) => {
          image.onload = () => resolve({ naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight });
          image.onerror = () => resolve({ naturalWidth: null, naturalHeight: null });
          image.src = url;
        });
        return result;
      }, resolved);
      const resource = raw.resources.find((x) => x.name === resolved) || null;
      hero = {
        url: resolved,
        status: heroResponse.status,
        contentType: heroResponse.headers.get('content-type'),
        bytes,
        ...dimensions,
        resource,
      };
    }
  }

  const byType = {};
  for (const r of raw.resources) {
    const key = r.initiatorType || 'other';
    const item = byType[key] ||= { count: 0, transferSize: 0, encodedBodySize: 0, decodedBodySize: 0 };
    item.count += 1;
    item.transferSize += Number(r.transferSize || 0);
    item.encodedBodySize += Number(r.encodedBodySize || 0);
    item.decodedBodySize += Number(r.decodedBodySize || 0);
  }

  const largest = [...raw.resources]
    .sort((a, b) => Number(b.encodedBodySize || 0) - Number(a.encodedBodySize || 0))
    .slice(0, 15)
    .map((x) => ({ ...x, startTime: round(x.startTime), duration: round(x.duration) }));

  const result = {
    status: 'ready',
    target,
    checkedAt: new Date().toISOString(),
    wallMs: Date.now() - started,
    viewport: raw.viewport,
    title: raw.title,
    navigation: raw.nav ? {
      ttfbMs: round(raw.nav.responseStart),
      responseEndMs: round(raw.nav.responseEnd),
      domContentLoadedMs: round(raw.nav.domContentLoadedEventEnd),
      loadMs: round(raw.nav.loadEventEnd),
      transferSize: raw.nav.transferSize,
      encodedBodySize: raw.nav.encodedBodySize,
      decodedBodySize: raw.nav.decodedBodySize,
    } : null,
    lcp,
    hero,
    aboveFoldBackgrounds: raw.aboveFoldBackgrounds,
    resourceSummary: byType,
    largestResources: largest,
    imageCount: raw.images.length,
    imagesAboveFold: raw.images.filter((x) => x.top < raw.viewport.height).slice(0, 20),
  };

  if (!lcp) throw new Error('No LCP entry observed');
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const result = {
    status: 'failed',
    target,
    checkedAt: new Date().toISOString(),
    error: String(error?.stack || error),
  };
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
}
