// Headless Chrome over raw CDP (Node 22 WebSocket) — no deps.
// usage: node capture.mjs <outDir> <url> [<url>...]   → <slug>.png (full page) + <slug>.json (element rects)
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const [outDir, ...urls] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const PORT = 9333;
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${outDir}/.profile`,
  "--hide-scrollbars", "--lang=zh-TW", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let targets;
for (let i = 0; i < 50 && !targets; i++) {
  await sleep(200);
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); } catch {}
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m.result ?? m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.value;

const W = 393, H = 852, DPR = 3;
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DPR, mobile: true });
await send("Emulation.setUserAgentOverride", { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1" });
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });

// seed flags so onboarding modal / changelog toast / install banner stay away
await send("Page.navigate", { url: "https://tinboker.com/about" }); await sleep(3000);
await evalJs(`localStorage.setItem('tb_onboarding_seen','1'); localStorage.setItem('tb_last_seen_changelog','9999'); sessionStorage.setItem('pwa-banner-dismissed','1'); 1`);

for (const url of urls) {
  const slug = new URL(url).pathname.replace(/\W+/g, "_").replace(/^_|_$/g, "") || "home";
  await send("Page.navigate", { url }); await sleep(9000);
  await evalJs(`[...document.querySelectorAll('button')].filter(b=>/略過|跳過|關閉|稍後|close|skip|^\\s*[×✕✖x]\\s*$/i.test(b.textContent+' '+(b.getAttribute('aria-label')||''))).forEach(b=>b.click()); 1`);
  await sleep(800);
  // lazy content: scroll down and back
  await evalJs(`(async()=>{for(let y=0;y<document.body.scrollHeight;y+=600){scrollTo(0,y);await new Promise(r=>setTimeout(r,250))}scrollTo(0,0);await new Promise(r=>setTimeout(r,1200))})()`);
  const h = Math.min(await evalJs(`document.documentElement.scrollHeight`), 6000);
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: h, deviceScaleFactor: DPR, mobile: true });
  await sleep(1500);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${outDir}/${slug}.png`, Buffer.from(shot.data, "base64"));
  const rects = await evalJs(`[...document.querySelectorAll('main *, header, nav, section, article, [class*=card], [class*=Card], svg, canvas')]
    .map(el=>{const r=el.getBoundingClientRect();return {tag:el.tagName.toLowerCase(),cls:String(el.className?.baseVal??el.className).slice(0,80),text:(el.innerText||'').slice(0,40).replace(/\\n/g,' '),x:r.x,y:r.y+scrollY,w:r.width,h:r.height}})
    .filter(r=>r.w>=250&&r.h>=60&&r.h<700)`);
  writeFileSync(`${outDir}/${slug}.json`, JSON.stringify(rects, null, 1));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DPR, mobile: true });
  console.log(slug, h, rects.length, JSON.stringify(await evalJs(`[...new Set([...document.querySelectorAll('a[href*="/episode/"]')].map(a=>a.getAttribute('href')))].slice(0,5)`)));
}
chrome.kill();
process.exit(0);
