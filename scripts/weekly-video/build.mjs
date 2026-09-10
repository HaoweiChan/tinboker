// Build a TinBoker weekly-rollup animation video from /api/weekly/{week}.
// Deterministic: the page exposes setT(seconds); we step it and screenshot.
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const WEEK = process.argv[2] || '2026-W36';
const API  = process.env.API || 'https://dev-api.tinboker.com';  // `flips` lands on dev first
const FPS  = +(process.env.FPS || 20);
const HERE = path.dirname(new URL(import.meta.url).pathname);
const OUT  = process.env.OUT_DIR || path.join(HERE, 'out');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const j = async (u) => { const r = await fetch(u); if (!r.ok) throw new Error(u + ' -> ' + r.status); return r.json(); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ── data ───────────────────────────────────────────────────────────────────
const wk = await j(`${API}/api/weekly/${WEEK}`);
const ALIAS = { SPCX: 'SpaceX' };   // vendor name is a 60-char legal title
const nameCache = new Map();

// Order is decided by MARKET, never by which source happened to carry the name:
// a TW code always reads 名稱 + 代號, a US ticker always reads TICKER + english name.
// (The weekly payload only names tickers that appear in a sector exposure, so 8046
// arrived nameless and used to flip to ticker-first while 3037 stayed name-first.)
async function label(t) {
  let name = t.name || ALIAS[t.ticker] || '';
  if (!name) {
    if (!nameCache.has(t.ticker)) {
      try { const b = await j(`${API}/api/stocks/${t.ticker}/basic`); nameCache.set(t.ticker, b.name || ''); }
      catch { nameCache.set(t.ticker, ''); }
    }
    name = nameCache.get(t.ticker) || '';
  }
  if (/^\d+$/.test(t.ticker)) return { label: name || t.ticker, sub: name ? t.ticker : '' };
  let n = name
    .replace(/\b(Corp|Inc|Corporation|Common Stock|Class A|Technologies|Exploration|Platforms|Holdings?|Ltd|plc)\b/gi, '')
    .replace(/[.,]/g, ' ').replace(/\s+/g, ' ').trim();
  if (n.length > 13) n = n.slice(0, 13).replace(/\s+\S*$/, '');   // cut on a word boundary, never mid-word
  return { label: t.ticker, sub: n };
}

const tickers = [];
for (const t of wk.tickers.slice(0, 8)) tickers.push({ ...t, ...(await label(t)) });

// `flips` — which tickers the same shows changed their mind about — is computed by the
// backend (routers/weekly.py:flip_rows), NOT here. The weekly Threads copy reads the
// same field, and a video naming different tickers than the post would be the exact
// drift this repo has already had three times.
const flips = [];
for (const t of wk.flips || []) {
  const L = await label(t);
  const seg = (b, n, r) => [['b', b], ['n', n], ['r', r]].filter(s => s[1] > 0);
  const note = t.direction === 'bear'
    ? `上週 <b class="up">${t.prev_bull} 看多</b> · <b class="dn">${t.prev_bear} 看空</b> → 本週 <b class="up">${t.bull} 看多</b> · <b class="dn">${t.bear} 看空</b>`
    : `上週 <b class="up">${t.prev_bull} 看多</b> → 本週 <b class="up">${t.bull} 看多</b>，${t.episodes} 集提到`;
  flips.push({ ...L, prev: seg(t.prev_bull, t.prev_neu, t.prev_bear), now: seg(t.bull, t.neu, t.bear), note });
}
if (!flips.length) throw new Error(`${API} returned no \`flips\` — that backend predates flip_rows (PR: weekly video)`);

const D = {
  week: WEEK,
  range: `${wk.start.replaceAll('-', '.')} – ${wk.end.replaceAll('-', '.')}`,
  episode_count: wk.episode_count,
  podcast_count: wk.podcasts.length,
  ticker_count: wk.tickers.length,
  tickers, flips,
  sectors: wk.sectors.slice(0, 10).map(s => ({ name: s.display_name, episodes: s.episodes })),
  cta: '每天更新的節目摘要 · 個股情緒 · 題材熱度',
};

await fs.mkdir(OUT, { recursive: true });
const html = (await fs.readFile(path.join(HERE, 'weekly.html'), 'utf8')).replace('__DATA__', JSON.stringify(D));
const page = path.join(OUT, `page-${WEEK}.html`);
await fs.writeFile(page, html);
await fs.writeFile(path.join(OUT, `data-${WEEK}.json`), JSON.stringify(D, null, 2));

// ── chrome over CDP ────────────────────────────────────────────────────────
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'wkchrome-'));
const port = 9333;
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--hide-scrollbars', '--disable-gpu', '--no-first-run', '--force-device-scale-factor=1', 'about:blank'],
  { stdio: 'ignore' });
let targets;
for (let i = 0; i < 40; i++) { try { targets = await j(`http://127.0.0.1:${port}/json`); break; } catch { await sleep(250); } }
const target = targets.find(t => t.type === 'page');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
const cmd = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

await cmd('Page.enable');
await cmd('Emulation.setDeviceMetricsOverride', { width: 1080, height: 1350, deviceScaleFactor: 1, mobile: false });
await cmd('Page.navigate', { url: 'file://' + page });
await sleep(2500);
await cmd('Runtime.evaluate', { expression: 'document.fonts.ready', awaitPromise: true });
await sleep(600);
const dur = (await cmd('Runtime.evaluate', { expression: 'window.DURATION' })).result.value;
const frames = Math.round(dur * FPS);
const t0 = Date.now();
for (let f = 0; f < frames; f++) {
  await cmd('Runtime.evaluate', { expression: `setT(${(f / FPS).toFixed(4)})` });
  const shot = await cmd('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  await fs.writeFile(path.join(OUT, `f${String(f).padStart(4, '0')}.png`), Buffer.from(shot.data, 'base64'));
  if (f % 40 === 0) process.stdout.write(`  frame ${f}/${frames} (${((Date.now() - t0) / 1000).toFixed(1)}s)\n`);
}
ws.close(); chrome.kill();

// ── encode ─────────────────────────────────────────────────────────────────
const mp4 = path.join(OUT, `tinboker-weekly-${WEEK}.mp4`);
await new Promise((res, rej) => {
  const ff = spawn('ffmpeg', ['-y', '-framerate', String(FPS), '-i', path.join(OUT, 'f%04d.png'),
    '-c:v', 'libx264', '-profile:v', 'high', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    '-r', '30', mp4], { stdio: 'inherit' });
  ff.on('exit', c => c === 0 ? res() : rej(new Error('ffmpeg ' + c)));
});
for (const f of await fs.readdir(OUT)) if (f.endsWith('.png')) await fs.unlink(path.join(OUT, f));
console.log('\n✓ ' + mp4);
