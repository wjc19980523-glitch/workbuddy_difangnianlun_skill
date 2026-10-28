// Render driver (frozen template).
//   node src/render.mjs <cityDir> shot <t> <out.png> [<t> <out.png> ...]   stills at given seconds
//   node src/render.mjs <cityDir> frames <outDir> <startFrame> <endFrame>  JPEG frames (resumable)
//   node src/render.mjs <cityDir> info                                     timeline as JSON
// The template is served at /, the city folder (city.json, nodes.json, assets/) at /city/.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.jpg': 'image/jpeg', '.png': 'image/png', '.bin': 'application/octet-stream' };

const [cityArg, mode, ...args] = process.argv.slice(2);
const CITY_DIR = path.resolve(cityArg || '');
if (!fs.existsSync(path.join(CITY_DIR, 'city.json'))) { console.error('usage: node src/render.mjs <cityDir> shot|frames|info ...'); process.exit(2); }

function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const u = decodeURIComponent(req.url.split('?')[0]);
      const [base, rel] = u.startsWith('/city/') ? [CITY_DIR, u.slice(6)] : [ROOT, u];
      const p = path.join(base, rel);
      if (!p.startsWith(base) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { rsp.writeHead(404); rsp.end(); return; }
      rsp.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream' });
      fs.createReadStream(p).pipe(rsp);
    }).listen(0, '127.0.0.1', () => res(srv));
  });
}

async function open() {
  const srv = await serve();
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new',
    args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
      '--window-size=1080,1920', '--hide-scrollbars', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
      '--no-proxy-server'],
  });
  const page = await browser.newPage();
  // quality knobs: NL_SCALE (1 = 1080x1920 output, 0.5 = 540x960), NL_SAMPLES (MSAA, 4), NL_FPS (30)
  const SCALE = parseFloat(process.env.NL_SCALE || '1');
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: SCALE });
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.error('[page]', m.text()); });
  page.on('pageerror', e => console.error('[pageerror]', e.message));
  await page.goto(`http://127.0.0.1:${srv.address().port}/src/index.html?scale=${SCALE}&samples=${process.env.NL_SAMPLES || 4}&fps=${process.env.NL_FPS || 30}`, { waitUntil: 'load', timeout: 0 });
  await page.waitForFunction('window.ready || window.bootError', { timeout: 0, polling: 200 });
  const err = await page.evaluate('window.bootError');
  if (err) throw new Error(err);
  return { srv, browser, page };
}

async function frame(page, t) {
  await page.evaluate(t => window.renderAt(t), t);
  // two rAFs so the DOM overlay and the WebGL canvas are composited
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}

const { srv, browser, page } = await open();
const stage = await page.$('#stage');
try {
  if (mode === 'shot') {
    for (let k = 0; k < args.length; k += 2) {
      const t = parseFloat(args[k]);
      const t0 = Date.now();
      await frame(page, t);
      await stage.screenshot({ path: args[k + 1], type: args[k + 1].endsWith('.png') ? 'png' : 'jpeg', ...(args[k + 1].endsWith('.png') ? {} : { quality: 92 }) });
      console.log('shot', t, args[k + 1], Date.now() - t0, 'ms');
    }
  } else if (mode === 'frames') {
    const [dir, s, e] = [args[0], parseInt(args[1]), parseInt(args[2])];
    fs.mkdirSync(dir, { recursive: true });
    const fps = await page.evaluate('window.FPS');
    const t0 = Date.now();
    for (let f = s; f < e; f++) {
      const out = path.join(dir, `f${String(f).padStart(5, '0')}.jpg`);
      if (fs.existsSync(out) && fs.statSync(out).size > 10000) continue;
      await frame(page, f / fps);
      await stage.screenshot({ path: out + '.tmp', type: 'jpeg', quality: 94 });
      fs.renameSync(out + '.tmp', out);
      if ((f - s) % 50 === 0) console.log(`frame ${f} (${((Date.now() - t0) / (f - s + 1) / 1000).toFixed(2)} s/f)`);
    }
  } else if (mode === 'layout') {
    // measure every node's typography in the real page: wrapped lines / overlaps are layout errors
    const segs = await page.evaluate('window.segments');
    const rep = [];
    for (const s of segs.filter(s => s.kind === 'node')) {
      await frame(page, s.t0 + 5.2);
      rep.push(await page.evaluate(i => {
        const r = e => e.getBoundingClientRect();
        const lines = (e, lh) => Math.round(r(e).height / lh);
        const q = id => document.getElementById(id);
        const out = { i, year: lines(q('year'), 112 * 1.05), title: lines(q('title'), 62 * 1.25),
          body: [...q('body').children].map(d => lines(d, 35 * 1.72)), src: lines(q('src'), 22 * 1.5),
          footTop: Math.round(r(q('foot')).top), eraW: Math.round(q('era').scrollWidth), eraBox: Math.round(q('era').clientWidth) };
        const big = document.querySelector('.tcard .big');
        if (big) { out.cardBig = lines(big, 150 * 1.1); out.cardLines = [...document.querySelectorAll('.tcard .ln')].map(d => lines(d, 36 * 1.8)); }
        const cap = document.querySelector('.cardimg .cap');
        if (cap) out.cap = lines(cap, 25 * 1.5);
        const cards = [...document.querySelectorAll('.cardimg')].map(b => { const k = b.firstElementChild; return k ? Math.round(r(k).bottom) : 0; });
        out.cardBottom = Math.max(0, ...cards);
        return out;
      }, s.i));
    }
    console.log(JSON.stringify(rep));
  } else if (mode === 'info') {
    console.log(JSON.stringify(await page.evaluate('({total: window.TOTAL, fps: window.FPS, segments: window.segments})')));
  }
} finally {
  await browser.close();
  srv.close();
}
