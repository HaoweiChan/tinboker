// Run: node scripts/validate-pwa-install-fallback.mjs [alternate-component-path]
// Exercise the actual banner and inline guide with controlled hooks and browser events.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { build } from 'esbuild';

const bundled = await build({
  entryPoints: [process.argv[2] ? resolve(process.argv[2]) : fileURLToPath(new URL('../src/components/common/PWAInstallPrompt.tsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  plugins: [{ name: 'browser-mocks', setup(builder) {
    builder.onResolve({ filter: /^(react|lucide-react|@\/)/ }, ({ path }) => ({ path, namespace: 'stub' }));
    builder.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path }) => ({ contents:
      path === 'react' ? 'export const {useState,useEffect,useCallback}=globalThis.hooks; export default {};' :
      path === 'react/jsx-runtime' ? 'export const jsx=(type,props)=>({type,props}); export const jsxs=jsx;' :
      path.includes('utils') ? 'export const cn=(...args)=>args.filter(Boolean).join(" ");' :
      'export const Download=()=>null, Share=Download, Plus=Download, MoreVertical=Download, X=Download, Check=Download, BracketMark=Download;',
    }));
  } }],
});

function browser(userAgent) {
  const frames = new Map(), listeners = new Map(), storage = new Map();
  let frame, cursor, effects = [], timers = [];
  const runtime = {
    module: { exports: {} },
    navigator: { userAgent, platform: '', maxTouchPoints: 1 },
    sessionStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    setTimeout: (callback) => { timers.push(callback); return timers.length; }, clearTimeout: () => {},
    window: {
      location: { pathname: '/' }, matchMedia: () => ({ matches: false }),
      addEventListener: (name, callback) => { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(callback); },
      removeEventListener: (name, callback) => listeners.get(name)?.delete(callback),
    },
    hooks: {
      useState(initial) {
        const slots = frame, index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
        return [slots[index], (value) => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
      },
      useEffect(effect, deps) {
        const index = cursor++;
        if (!frame[index] || deps.some((value, i) => value !== frame[index][i])) { frame[index] = deps; effects.push(effect); }
      },
      useCallback: (callback) => callback,
    },
  };
  vm.runInNewContext(bundled.outputFiles[0].text, runtime);
  function expand(node, path = 'root') {
    if (!node || typeof node !== 'object') return node;
    if (Array.isArray(node)) return node.map((child, i) => expand(child, `${path}.${i}`));
    if (typeof node.type === 'function') {
      if (!frames.has(path)) frames.set(path, []);
      frame = frames.get(path); cursor = 0;
      return expand(node.type(node.props), `${path}.child`);
    }
    return { ...node, props: { ...node.props, children: expand(node.props.children, `${path}.children`) } };
  }
  const render = () => expand({ type: runtime.module.exports.PWAInstallBanner, props: {} });
  const settle = () => {
    let tree;
    for (let i = 0; i < 3; i++) { tree = render(); const pending = effects; effects = []; pending.forEach((effect) => effect()); }
    return tree;
  };
  settle(); const pendingTimers = timers; timers = []; pendingTimers.forEach((callback) => callback());
  return { settle, storage, emit: (name, event) => listeners.get(name)?.forEach((callback) => callback(event)) };
}
const text = (node) => Array.isArray(node) ? node.map(text).join('') : node && typeof node === 'object' ? text(node.props.children) : String(node ?? '');
function button(node, label) {
  if (Array.isArray(node)) return node.map((child) => button(child, label)).find(Boolean);
  if (!node || typeof node !== 'object') return undefined;
  if (node.type === 'button' && (text(node) === label || node.props['aria-label'] === label)) return node;
  return button(node.props.children, label);
}

const android = browser('Mozilla/5.0 Android Chrome/140');
await button(android.settle(), '查看安裝步驟').props.onClick();
assert.match(text(android.settle()), /Chrome 右上角/, 'Android fallback must open Android instructions');
assert.doesNotMatch(text(android.settle()), /Safari/, 'Android fallback must not show iOS instructions');
button(android.settle(), '知道了').props.onClick();
assert.equal(android.settle(), null);
assert.equal(android.storage.get('pwa-banner-dismissed'), '1');

const ios = browser('Mozilla/5.0 iPhone Safari/605');
await button(ios.settle(), '查看安裝步驟').props.onClick();
assert.match(text(ios.settle()), /Safari.*分享/, 'iOS keeps Safari instructions');
button(ios.settle(), '關閉').props.onClick();
assert.equal(ios.settle(), null);

const native = browser('Mozilla/5.0 Android Chrome/140');
let prompts = 0, prevented = false;
native.emit('beforeinstallprompt', { preventDefault: () => { prevented = true; }, prompt: async () => { prompts++; }, userChoice: Promise.resolve({ outcome: 'accepted' }) });
await button(native.settle(), '立即安裝').props.onClick();
assert.equal(prompts, 1);
assert.equal(prevented, true);
assert.equal(native.settle(), null, 'accepted native install hides banner');
console.log('PASS: Android fallback, iOS instructions, dismiss persistence, and native install');
