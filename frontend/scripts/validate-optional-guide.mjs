// Run: node scripts/validate-optional-guide.mjs
// Exercise the actual controller and storage helpers without a browser or network.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { build } from 'esbuild';

const storage = new Map();
let slots = [], cursor = 0, effects = [];
let route = { pathname: '/', search: '', hash: '' };
let lastNavigation;
const runtime = {
  module: { exports: {} }, URLSearchParams,
  localStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
  hooks: {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value) => { slots[index] = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      slots[index] ??= { current: initial };
      return slots[index];
    },
    useEffect(effect, dependencies) {
      const index = cursor++;
      if (!slots[index] || dependencies.some((value, i) => value !== slots[index][i])) {
        slots[index] = dependencies;
        effects.push(effect);
      }
    },
  },
  router: {
    useLocation: () => route,
    useSearchParams: () => [new URLSearchParams(route.search)],
    useNavigate: () => (next, options) => { route = next; lastNavigation = options; },
  },
};
const bundled = await build({
  entryPoints: [fileURLToPath(new URL('../src/components/onboarding/OnboardingModals.tsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  define: { 'import.meta.env.VITE_RELEASE_VERSION': 'undefined' },
  plugins: [{
    name: 'controlled-ui-dependencies',
    setup(builder) {
      builder.onResolve({ filter: /^@\/lib\/onboarding$/ }, () => ({ path: fileURLToPath(new URL('../src/lib/onboarding.ts', import.meta.url)) }));
      builder.onResolve({ filter: /^(react|react-dom|react-router-dom|lucide-react|@\/)/ }, ({ path }) => ({ path, namespace: 'stub' }));
      builder.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path }) => ({ contents:
        path === 'react' ? 'export const {useState,useEffect,useRef} = globalThis.hooks;' :
        path === 'react/jsx-runtime' ? 'export const jsx=(type,props)=>({type,props}); export const jsxs=jsx;' :
        path === 'react-router-dom' ? 'export const {useLocation,useSearchParams,useNavigate}=globalThis.router;' :
        path.includes('useAppStore') ? 'export const useAppStore=(select)=>select({isAuthReady:true,user:null});' :
        'export const X=()=>null, ArrowRight=X, ArrowLeft=X, TrendingUp=X, Hash=X, Sparkles=X, BracketMark=X, GoogleLoginButton=X, DisplayPreferences=X, createPortal=X;',
      }));
    },
  }],
});
vm.runInNewContext(bundled.outputFiles[0].text, runtime);
const render = () => { cursor = 0; return runtime.module.exports.OnboardingModals(); };
const settle = () => {
  render();
  const pending = effects;
  effects = [];
  pending.forEach((effect) => effect());
  return render();
};
assert.equal(settle(), null, 'first visitor gets no automatic tutorial or release modal');
const latest = storage.get('tb_last_seen_changelog');
assert.ok(latest, 'first visit silently adopts latest changelog');
assert.equal(storage.has('tb_onboarding_seen'), false, 'optional invitation remains eligible');

route = { pathname: '/', search: '?keep=1&onboarding=tutorial', hash: '#market' };
const tutorial = settle();
assert.ok(tutorial?.props.onClose, 'manual tutorial opens');
tutorial.props.onClose();
assert.equal(storage.get('tb_onboarding_seen'), '1');
assert.equal(new URLSearchParams(route.search).get('keep'), '1');
assert.equal(new URLSearchParams(route.search).has('onboarding'), false);
assert.equal(route.hash, '#market');
assert.equal(lastNavigation.replace, true);
assert.equal(settle(), null, 'closing tutorial does not open another modal');

route = { pathname: '/about', search: '?onboarding=tutorial', hash: '' };
assert.ok(settle()?.props.onClose, 'seen tutorial reopens from public About while signed out');
settle().props.onClose();
assert.equal(settle(), null);

slots = []; effects = [];
storage.set('tb_last_seen_changelog', 'older-release');
route = { pathname: '/', search: '?keep=2&onboarding=whatsnew', hash: '#market' };
settle().props.onClose();
assert.equal(storage.get('tb_last_seen_changelog'), 'older-release', 'explicit release preview keeps its seen flag');
assert.equal(settle(), null, 'closing release preview cannot trigger automatic release notes');

slots = []; effects = [];
route = { pathname: '/', search: '', hash: '' };
const automatic = settle();
assert.ok(automatic?.props.onClose, 'returning visitor still gets unseen release notes');
automatic.props.onClose();
assert.equal(storage.get('tb_last_seen_changelog'), latest);
assert.equal(settle(), null);
console.log('PASS: optional first visit, query open/close/reopen, URL preservation, signed-out About, and changelog isolation');
