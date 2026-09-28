import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const require = createRequire(import.meta.url);
const flush = () => new Promise(resolve => setImmediate(resolve));
const subscription = { id: 'sub', mer_order_no: 'order', status: 'active', amount: 299, is_founding: false, gateway_env: 'sandbox', paid_until: '2026-10-23T00:00:00Z', next_auth_date: '2026-10-23' };
const realUser = { id: 'user', name: 'User', email: 'user@example.com', is_member: false };
async function run(entry, mocks, runtime) {
  const result = await build({ entryPoints: [entry], tsconfig: 'tsconfig.app.json', bundle: true, write: false, format: 'cjs', platform: 'node',
    plugins: [{ name: 'boundaries', setup(builder) {
      builder.onResolve({ filter: /.*/ }, args => Object.hasOwn(mocks, args.path) ? ({ path: args.path, namespace: 'mock' }) : undefined);
      builder.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: mocks[args.path] }));
    } }],
  });
  runtime.module = { exports: {} }; runtime.require = require; runtime.console = console; runtime.URL = URL;
  vm.runInNewContext(result.outputFiles[0].text, runtime);
  return runtime.module.exports;
}
function all(node) {
  if (!node || typeof node !== 'object') return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(all)];
}
function text(node) { return typeof node === 'string' ? node : node && typeof node === 'object' ? [node.props?.children].flat(Infinity).map(text).join('') : ''; }
function button(tree, label) { return all(tree).find(node => node.type === 'button' && text(node).includes(label)); }
async function statusHarness(value = subscription, isMember = false) {
  const r = { hooks: [], hookIndex: 0, effect: null, timers: [], calls: [], fetches: 0, cancelled: 0, AbortController };
  r.setTimeout = fn => { r.timers.push(fn); return r.timers.length; }; r.clearTimeout = () => {};
  r.state = { token: 'access', user: realUser, login: (...args) => r.calls.push(args) };
  r.api = { getSubscription: async () => { r.fetches++; return value; }, cancelSubscription: async () => { r.cancelled++; return { ...subscription, status: 'cancelled' }; } };
  r.auth = { getCurrentUser: async () => ({ ...realUser, is_member: isMember }) };
  const exports = await run('src/components/membership/SubscriptionStatus.tsx', {
    react: 'export const useState=(initial)=>{const i=globalThis.hookIndex++;if(!(i in globalThis.hooks))globalThis.hooks[i]=initial;return[globalThis.hooks[i],v=>{globalThis.hooks[i]=typeof v==="function"?v(globalThis.hooks[i]):v;}];}; export const useRef=(value)=>{const i=globalThis.hookIndex++;return globalThis.hooks[i]??={current:value};}; export const useEffect=(fn)=>{globalThis.effect=fn;};',
    'react/jsx-runtime': 'export const jsx=(type,props)=>({type,props});export const jsxs=jsx;export const Fragment="fragment";',
    'react-router-dom': 'export const Link="a";',
    '@/store/useAppStore': 'export const useAppStore=selector=>selector(globalThis.state);useAppStore.getState=()=>globalThis.state;',
    '@/services/api/billing': 'export const getSubscription=(...args)=>globalThis.api.getSubscription(...args);export const cancelSubscription=(...args)=>globalThis.api.cancelSubscription(...args);',
    '@/services/api/auth': 'export const authApi=globalThis.auth;',
  }, r);
  r.render = () => { r.hookIndex = 0; return exports.SubscriptionStatus({ paymentReturn: true }); };
  r.render(); r.cleanup = r.effect(); await flush(); return r;
}
const pending = await statusHarness({ ...subscription, status: 'pending' });
for (let i = 0; i < 25 && pending.timers.length; i++) { pending.timers.shift()(); await flush(); }
assert.equal(pending.fetches, 20); assert.equal(pending.calls.length, 0); assert.match(text(pending.render()), /請勿重複付款/);
const cancelling = await statusHarness({ ...subscription, status: 'cancelling' });
assert.match(text(cancelling.render()), /取消續訂確認中/);
assert.equal(cancelling.calls.length, 0);
assert.equal(button(cancelling.render(), '確認取消續訂'), undefined);
const notification = await statusHarness({ ...subscription, status: 'pending' }, true);
notification.api.getSubscription = async () => subscription;
notification.timers.shift()(); await flush();
assert.equal(notification.calls[0][0].is_member, true);
assert.match(text(notification.render()), /訂閱中/);
const lookupFailure = await statusHarness();
lookupFailure.api.getSubscription = async () => { throw new Error('network'); };
lookupFailure.effect(); await flush();
assert.match(text(lookupFailure.render()), /無法更新訂閱狀態/);
const declined = await statusHarness({ ...subscription, status: 'failed' });
assert.match(text(declined.render()), /付款未完成/);
const missing = await statusHarness(null); assert.equal(missing.calls.length, 0); assert.match(text(missing.render()), /尚未收到付款確認/);
const ended = await statusHarness({ ...subscription, status: 'ended' }, true);
assert.equal(ended.calls.length, 1);
assert.equal(ended.calls[0][0].is_member, true);
const confirmed = await statusHarness(); assert.equal(confirmed.calls[0][0].is_member, false);
assert.match(text(confirmed.render()), /測試付款/);
let rejectCancel;
confirmed.api.cancelSubscription = () => { confirmed.cancelled++; return new Promise((_, reject) => { rejectCancel = reject; }); };
button(confirmed.render(), '取消自動續訂').props.onClick();
const cancel = button(confirmed.render(), '確認取消續訂');
assert.match(text(confirmed.render()), /會員權益仍保留至/);
cancel.props.onClick(); cancel.props.onClick(); assert.equal(confirmed.cancelled, 1);
rejectCancel(new Error('unconfirmed')); await flush();
assert.match(text(confirmed.render()), /取消續訂尚未確認/); assert.match(text(confirmed.render()), /訂閱中/);
confirmed.api.cancelSubscription = async () => ({ ...subscription, status: 'cancelled' });
button(confirmed.render(), '確認取消續訂').props.onClick(); await flush();
assert.match(text(confirmed.render()), /已取消自動續訂/); assert.match(text(confirmed.render()), /已付款期間的會員權益不受影響/);
console.log('PASS: bounded polling, no return-query grant, server /me entitlement, cancel confirmation/deduplication/failure/retained term');
const r = { forms: [], calls: [], state: { token: 'access' } };
r.response = { action: 'https://ccore.newebpay.com/MPG/period', fields: { MerchantID_: 'merchant', PostData_: 'encrypted' }, gateway_env: 'sandbox', mer_order_no: 'order' };
r.transport = { post: async (...args) => { r.calls.push(args); return { data: r.response }; }, get: async (...args) => { r.calls.push(args); return { data: r.response }; } };
r.document = { createElement: tag => tag === 'form' ? { inputs: [], append(input) { this.inputs.push(input); }, submit() { this.submitted = true; }, remove() {} } : {}, body: { append: form => r.forms.push(form) } };
const api = await run('src/services/api/billing.ts', { './client': 'export const apiClient=globalThis.transport;', '@/store/useAppStore': 'export const useAppStore={getState:()=>globalThis.state};' }, r);
await api.startCheckout(); assert.equal(r.calls[0][2].headers.Authorization, 'Bearer access');
assert.equal(r.forms[0].method, 'POST'); assert.equal(r.forms[0].submitted, true);
assert.deepEqual(r.forms[0].inputs.map(i=>i.name), ['MerchantID_', 'PostData_']);
r.response.action = 'https://attacker.example/'; await assert.rejects(api.startCheckout); assert.equal(r.forms.length, 1);
r.response = { subscription }; assert.equal((await api.getSubscription()).status, 'active');
r.response = { subscription: { ...subscription, status: 'unknown' } }; await assert.rejects(api.getSubscription);
r.response = { subscription: null }; assert.equal(await api.getSubscription(), null);
r.response = { subscription: { ...subscription, status: 'cancelled' } }; await api.cancelSubscription();
assert.equal(r.calls.at(-1)[0], '/api/billing/cancel'); assert.equal(r.calls.at(-1)[2].headers.Authorization, 'Bearer access');
r.state.token = null; const count = r.calls.length; await assert.rejects(api.startCheckout, /Not authenticated/); assert.equal(r.calls.length, count);
console.log('PASS: auth headers, fixed gateway allowlist, encrypted fields only, response validation and missing authentication');

async function planHarness(open = true) {
  const r = { hooks: [], hookIndex: 0, effect: null, starts: 0, state: { isAuthReady: true, user: realUser } };
  r.plans = { list_price: 299, founding_price: 199, founding_limit: 100, founding_remaining: 10, founding_open: true, checkout_open: open, gateway_env: 'sandbox' };
  r.start = () => { r.starts++; return new Promise((_, reject) => { r.rejectCheckout = reject; }); };
  const exports = await run('src/components/membership/PlanCard.tsx', {
    react: 'export const useState=(initial)=>{const i=globalThis.hookIndex++;if(!(i in globalThis.hooks))globalThis.hooks[i]=initial;return[globalThis.hooks[i],v=>globalThis.hooks[i]=v];};export const useRef=value=>{const i=globalThis.hookIndex++;return globalThis.hooks[i]??={current:value};};export const useEffect=fn=>globalThis.effect=fn;',
    'react/jsx-runtime': 'export const jsx=(type,props)=>({type,props});export const jsxs=jsx;export const Fragment="fragment";',
    'react-router-dom': 'export const Link="a";',
    axios: 'export const isAxiosError=()=>false;',
    'lucide-react': 'export const CheckCircle2="icon";',
    '@/store/useAppStore': 'export const useAppStore=selector=>selector(globalThis.state);',
    '@/hooks/useRequireAuth': 'export const useRequireAuth=()=>({guard:fn=>fn()});',
    '@/services/api/billing': 'export const getPlans=async()=>globalThis.plans;export const startCheckout=()=>globalThis.start();',
  }, r);
  r.render = () => { r.hookIndex = 0; return exports.PlanCard(); };
  r.render(); r.effect(); await flush(); return r;
}
const plan = await planHarness();
assert.match(text(plan.render()), /測試付款/);
const buy = button(plan.render(), '立即加入會員'); buy.props.onClick(); buy.props.onClick();
assert.equal(plan.starts, 1); assert.equal(button(plan.render(), '正在前往付款').props.disabled, true);
plan.rejectCheckout(new Error('unavailable')); await flush();
assert.match(text(plan.render()), /無法開始付款/); assert.equal(button(plan.render(), '立即加入會員').props.disabled, false);
const closed = await planHarness(false); assert.equal(button(closed.render(), '即將開放').props.disabled, true); assert.equal(closed.starts, 0);
console.log('PASS: actual checkout component prevents double submission, reports errors, labels sandbox and keeps missing-config checkout disabled');
