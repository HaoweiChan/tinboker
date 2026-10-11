"""Screenshot an article at the passage a draft quotes, with the quotes highlighted.

Drives a system Chromium over the DevTools protocol with the ``websockets`` client the
workspace already installs — no browser-automation dependency. Every failure raises:
the caller's rule is "no image, no draft", and a screenshot of a cookie wall or an ad
is worse than none.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

VIEWPORT = (600, 750)  # CSS px at 2x -> a 1200x1500 (4:5) image
DEADLINE = 90
USER_AGENT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

# Consent walls first: they dim the page and block scrolling.
_CONSENT = r"""
(() => { for (const b of document.querySelectorAll('button'))
  if (/^(continue|accept|agree|i agree|got it)/i.test(b.textContent.trim())) { b.click(); return true; }
  return false; })()
"""

_HELPERS = r"""
// Extracted text and the live DOM disagree on typography: curly vs straight quotes,
// non-breaking spaces. Each character maps to one character, so offsets stay aligned.
const canon = (c) => "\u2018\u2019".includes(c) ? "'" : "\u201c\u201d".includes(c) ? '"' : /\s/.test(c) ? ' ' : c;
const flat = (s) => [...s].map(canon).join('').replace(/ +/g, ' ');
const holder = (text) => [...document.querySelectorAll('p, li, blockquote')]
  .find(e => flat(e.textContent).includes(text));
const pinned = (e) => ['fixed', 'sticky'].includes(getComputedStyle(e).position);
"""

# Scrolling to the passage is what triggers the promo modals, so scroll first, clean after.
_LOCATE = _HELPERS + r"""
(() => { const p = PHRASES.map(holder).find(Boolean);
  if (p) p.scrollIntoView({ block: 'center' });
  return !!p; })()
"""

_FRAME = _HELPERS + r"""
(() => {
  for (const e of document.querySelectorAll('body *')) {
    if (!e.isConnected) continue;
    const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    const modal = (cs.position === 'fixed' || cs.position === 'absolute') && +cs.zIndex > 10
      && r.width > innerWidth * 0.6 && r.height > innerHeight * 0.4;
    if (modal || (pinned(e) && e.querySelector('input'))) e.remove();
  }
  document.documentElement.style.overflow = document.body.style.overflow = 'auto';
  const p = PHRASES.map(holder).find(Boolean);
  // Frame the passage with the nearest photo above it when both fit.
  const img = [...document.querySelectorAll('img')].filter(i => i.getBoundingClientRect().width > 300
    && (i.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING)).pop();
  const top = (e) => e.getBoundingClientRect().top + scrollY;
  const fits = img && top(p) + p.offsetHeight - top(img) < innerHeight - 140;
  scrollTo(0, fits ? top(img) - 16 : top(p) - innerHeight / 3);
  return true;
})()
"""

# One wobbly, slightly tilted swipe per text line, so it reads as drawn by hand.
_HIGHLIGHT = _HELPERS + r"""
(() => {
  for (const e of document.querySelectorAll('body *'))
    if (e.isConnected && pinned(e) && e.querySelector('input')) e.remove();
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const jit = (a) => (rnd() * 2 - 1) * a;
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('style', 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;'
    + 'z-index:2147483647;mix-blend-mode:multiply');
  let drawn = 0, covered = 0;
  for (const text of PHRASES) {
    const p = holder(text);
    if (!p) continue;
    // Map the phrase onto the element's text nodes; it may run across inline links.
    const nodes = [], w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) nodes.push(n);
    const raw = nodes.map(n => n.textContent).join('');
    const map = []; let norm = '';
    for (let i = 0; i < raw.length; i++) {
      const c = canon(raw[i]);
      if (c === ' ' && norm.endsWith(' ')) continue;
      norm += c; map.push(i);
    }
    const s = norm.indexOf(text);
    if (s < 0) continue;
    const at = (offset) => { for (const n of nodes) { if (offset <= n.length) return [n, offset]; offset -= n.length; } };
    const range = document.createRange();
    range.setStart(...at(map[s])); range.setEnd(...at(map[s + text.length - 1] + 1));
    const lines = [];
    for (const r of range.getClientRects()) {
      const l = lines.find(l => Math.abs(l.top - r.top) < r.height / 2);
      if (l) { l.left = Math.min(l.left, r.left); l.right = Math.max(l.right, r.right); }
      else if (r.width > 1) lines.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right });
    }
    for (const l of lines) {
      if (l.top < 0 || l.bottom > innerHeight) continue;
      // Something still sits on top of the text: say so instead of shipping it.
      const hit = document.elementFromPoint((l.left + l.right) / 2, (l.top + l.bottom) / 2);
      if (!hit || !(p.contains(hit) || hit.contains(p))) { covered++; continue; }
      const h = l.bottom - l.top, x0 = l.left - 3 + jit(3), x1 = l.right + 3 + jit(4);
      const slope = jit(h * 0.07), yT = l.top + h * 0.16 + jit(1.5), yB = l.bottom - h * 0.06 + jit(1.5);
      const edge = (y, from, to) => {
        const pts = [], n = Math.max(4, Math.round(Math.abs(to - from) / 34));
        for (let i = 0; i <= n; i++) {
          const t = i / n;
          pts.push(`${(from + (to - from) * t).toFixed(1)},${(y + slope * (from < to ? t : 1 - t) + jit(h * 0.055)).toFixed(1)}`);
        }
        return pts;
      };
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', 'M' + [...edge(yT, x0, x1), ...edge(yB, x1 + jit(2), x0 + jit(2))].join(' L') + 'Z');
      path.setAttribute('fill', '#ffe94a'); path.setAttribute('fill-opacity', '0.78');
      path.setAttribute('stroke', '#ffe94a'); path.setAttribute('stroke-width', '2.5');
      path.setAttribute('stroke-linejoin', 'round');
      svg.appendChild(path); drawn++;
    }
  }
  document.body.appendChild(svg);
  return JSON.stringify({ drawn, covered });
})()
"""


_TYPOGRAPHY = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _script(template: str, phrases: list[str]) -> str:
    flat = [re.sub(r"\s+", " ", p.translate(_TYPOGRAPHY)).strip() for p in phrases]
    return f"const PHRASES = {json.dumps(flat)};\n" + template


def _browser_path() -> str:
    path = os.environ.get("NEWS_SCREENSHOT_BROWSER") or next(
        (found for name in ("chromium", "chromium-browser", "google-chrome")
         if (found := shutil.which(name))), None)
    if not path:
        raise RuntimeError("screenshot failed (no_browser)")
    return path


def capture(url: str, phrases: list[str]) -> bytes:
    """PNG of the article at the first quoted passage, quotes highlighted."""
    from websockets.sync.client import connect

    if not url.startswith("https://") or not phrases:
        raise RuntimeError("screenshot failed (bad_request)")
    started = time.monotonic()
    profile = tempfile.mkdtemp(prefix="news-shot-")
    drop = {}
    if os.geteuid() == 0:
        # Root cannot use Chromium's sandbox, and an unsandboxed browser on arbitrary
        # news pages is not acceptable: run it as nobody with the sandbox on.
        shutil.chown(profile, "nobody")
        drop = {"user": "nobody", "group": "nogroup", "env": {**os.environ, "HOME": profile}}
    proc = subprocess.Popen(
        [_browser_path(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
         "--no-first-run", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **drop)
    try:
        port_file = os.path.join(profile, "DevToolsActivePort")
        while not os.path.exists(port_file) or not open(port_file).read().strip():
            if proc.poll() is not None or time.monotonic() - started > 20:
                raise RuntimeError("screenshot failed (browser_start)")
            time.sleep(0.2)
        port = int(open(port_file).read().split()[0])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request(
                f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"), timeout=10) as response:
            target = json.load(response)
        with connect(target["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024, open_timeout=10) as ws:
            counter = 0

            def call(method: str, **params):
                nonlocal counter
                counter += 1
                ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                while True:
                    left = DEADLINE - (time.monotonic() - started)
                    if left <= 0:
                        raise RuntimeError("screenshot failed (timeout)")
                    reply = json.loads(ws.recv(timeout=left))
                    if reply.get("id") == counter:
                        if "error" in reply:
                            raise RuntimeError("screenshot failed (protocol)")
                        return reply["result"]

            def evaluate(source: str):
                # replMode lets each script redeclare the shared const helpers.
                result = call("Runtime.evaluate", expression=source, returnByValue=True, replMode=True)
                if "exceptionDetails" in result:
                    raise RuntimeError("screenshot failed (page_script)")
                return result["result"].get("value")

            width, height = VIEWPORT
            call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                 deviceScaleFactor=2, mobile=True)
            call("Emulation.setUserAgentOverride", userAgent=USER_AGENT)
            call("Page.navigate", url=url)
            # ponytail: fixed waits, not load events — news pages never go network-idle.
            time.sleep(7)
            evaluate(_CONSENT)
            time.sleep(2)
            if not evaluate(_script(_LOCATE, phrases)):
                raise RuntimeError("screenshot failed (passage_not_found)")
            time.sleep(4)
            evaluate(_script(_FRAME, phrases))
            time.sleep(2.5)
            marks = json.loads(evaluate(_script(_HIGHLIGHT, phrases)))
            if marks["covered"] or not marks["drawn"]:
                raise RuntimeError("screenshot failed (passage_covered)" if marks["covered"]
                                   else "screenshot failed (nothing_highlighted)")
            time.sleep(0.3)
            return base64.b64decode(call("Page.captureScreenshot", format="png")["data"])
    finally:
        proc.kill()
        proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)
