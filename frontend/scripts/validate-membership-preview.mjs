import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const user = { id: 'admin', name: 'Admin', email: 'admin@example.com', is_member: true, membership_preview: null, membership_preview_available: true };
const flush = () => new Promise((resolve) => setImmediate(resolve));
async function harness(stage, local = false) {
  const runtime = { module: { exports: {} }, require, console, hooks: [], hookIndex: 0, calls: [], reloads: 0 };
  runtime.window = { location: { reload() { runtime.reloads++; } } };
  runtime.state = { user: { ...user }, isAuthReady: true, login(...args) { runtime.calls.push(args); } };
  runtime.api = { async setMembershipPreview() { return { token: 'new-access', refresh_token: 'new-refresh', user: { ...user, is_member: false, membership_preview: 'free' } }; } };
  const mocks = {
    react: 'export const useState = (initial) => { const i=globalThis.hookIndex++; if (!(i in globalThis.hooks)) globalThis.hooks[i]=initial; return [globalThis.hooks[i], value => {globalThis.hooks[i]=value;}]; };',
    'react/jsx-runtime': 'export const jsx=(type,props)=>({type,props}); export const jsxs=jsx;',
    '@/store/useAppStore': 'export const useAppStore = selector => selector(globalThis.state); useAppStore.getState = () => globalThis.state;',
    '@/services/api/auth': 'export const authApi = globalThis.api;',
  };
  const result = await build({
    tsconfig: 'tsconfig.app.json', entryPoints: ['src/components/auth/MembershipPreviewBanner.tsx'], bundle: true, write: false, format: 'cjs', platform: 'node',
    define: { 'import.meta.env.VITE_STAGE': JSON.stringify(stage) ?? 'undefined', 'import.meta.env.DEV': JSON.stringify(local) },
    plugins: [{ name: 'component-boundaries', setup(builder) {
      builder.onResolve({ filter: /^(react|react\/jsx-runtime|@\/store\/useAppStore|@\/services\/api\/auth)$/ }, args => ({ path: args.path, namespace: 'mock' }));
      builder.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: mocks[args.path] }));
    } }],
  });
  vm.runInNewContext(result.outputFiles[0].text, runtime);
  runtime.render = () => { runtime.hookIndex = 0; return runtime.module.exports.MembershipPreviewBanner(); };
  return runtime;
}
function find(node, type) {
  if (!node || typeof node !== 'object') return null;
  if (node.type === type) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, type); if (found) return found; }
  return null;
}
for (const stage of ['PRODUCTION', 'STAGING', undefined]) assert.equal((await harness(stage)).render(), null);
assert.equal((await harness(undefined, true)).render(), null);
assert.equal((await harness('STAGING', true)).render(), null);
assert.equal((await harness('PRODUCTION', true)).render(), null);
const dev = await harness('DEV');
dev.state.isAuthReady = false; assert.equal(dev.render(), null);
dev.state.isAuthReady = true; dev.state.user.membership_preview_available = false; assert.equal(dev.render(), null);
dev.state.user.membership_preview_available = true;
assert.equal(find(dev.render(), 'select').props.children.length, 2);
dev.state.user.is_member = false;
assert.equal(find(dev.render(), 'select').props.value, 'free');
dev.state.user.is_member = true;
let resolveRequest;
dev.api.setMembershipPreview = () => new Promise(resolve => { resolveRequest = resolve; });
find(dev.render(), 'select').props.onChange({ target: { value: 'free' } });
assert.equal(dev.calls.length, 0); assert.equal(dev.reloads, 0);
assert.equal(find(dev.render(), 'select').props.disabled, true);
assert.equal(find(dev.render(), 'select').props.value, 'paid');
resolveRequest({ token: 'access', refresh_token: 'refresh', user: { ...user, is_member: false, membership_preview: 'free' } });
await flush();
assert.equal(dev.calls[0][0].is_member, false);
assert.equal(dev.calls[0][0].membership_preview, 'free');
assert.equal(dev.calls[0][1], 'access'); assert.equal(dev.calls[0][2], 'refresh'); assert.equal(dev.reloads, 1);
for (const mode of ['free', 'paid']) {
  const session = await harness('DEV');
  session.api.setMembershipPreview = async () => ({ token: 'access', refresh_token: 'refresh', user: { ...user, is_member: mode === 'paid', membership_preview: mode } });
  find(session.render(), 'select').props.onChange({ target: { value: mode } }); await flush();
  assert.equal(session.calls[0][0].is_member, mode === 'paid');
  assert.equal(session.calls[0][0].membership_preview, mode);
  assert.equal(session.reloads, 1);
}
const failed = await harness('DEV');
failed.api.setMembershipPreview = async () => { throw new Error('expired'); };
find(failed.render(), 'select').props.onChange({ target: { value: 'paid' } }); await flush();
assert.equal(failed.calls.length, 0); assert.equal(failed.reloads, 0);
assert.equal(find(failed.render(), 'select').props.value, 'paid');
assert.equal(find(failed.render(), 'select').props.disabled, false);
assert.match(failed.hooks[1], /切換失敗/);
const schemaBuild = await build({ entryPoints: ['src/lib/authSession.ts'], bundle: true, write: false, format: 'cjs', platform: 'node' });
const schemaRuntime = { module: { exports: {} }, require };
vm.runInNewContext(schemaBuild.outputFiles[0].text, schemaRuntime);
const { SessionResponseSchema, sessionUser } = schemaRuntime.module.exports;
assert.throws(() => SessionResponseSchema.parse({ token: '', user }));
assert.throws(() => SessionResponseSchema.parse({ token: 'access', user: { ...user, membership_preview: 'admin' } }));
const restored = sessionUser({ ...user, is_member: false, membership_preview: null, membership_preview_available: false });
assert.equal(restored.is_member, false); assert.equal(restored.membership_preview, null); assert.equal(restored.membership_preview_available, false);
console.log('PASS: environment/admin gates, pending non-optimistic switch, persisted effective user and tokens before reload, failure recovery, and restored session fields');

// Exercise the real API wrapper and refresh function with transport/store boundaries only.
const { readFile } = await import('node:fs/promises');
async function authBoundary(entry, exposeRefresh = false) {
  const runtime = { module: { exports: {} }, require, console, calls: [], state: { token: 'old-access', refreshToken: 'old-refresh', user: { ...user, membership_preview: 'paid' } } };
  runtime.state.login = (nextUser, token, refreshToken) => { runtime.state.user = nextUser; runtime.state.token = token; runtime.state.refreshToken = refreshToken; };
  runtime.response = { token: 'fresh-access', refresh_token: 'fresh-refresh', user: { ...user, is_member: false, membership_preview: null } };
  runtime.transport = { post: async (...args) => { runtime.calls.push(args); return { data: runtime.response }; }, create: () => ({ interceptors: { request: { use() {} }, response: { use() {} } } }) };
  const source = await readFile(entry, 'utf8');
  const output = await build({
    stdin: { contents: source + (exposeRefresh ? '\nexport { performTokenRefresh };' : ''), resolveDir: process.cwd() + '/' + entry.slice(0, entry.lastIndexOf('/')), loader: 'ts' },
    tsconfig: 'tsconfig.app.json', bundle: true, write: false, format: 'cjs', platform: 'node',
    define: { 'import.meta.env.DEV': 'false', 'import.meta.env.PROD': 'false', 'import.meta.env.VITE_API_BASE_URL': 'undefined' },
    plugins: [{ name: 'auth-boundaries', setup(builder) {
      builder.onResolve({ filter: /^(axios|sonner|@\/store\/useAppStore|\.\/client)$/ }, args => ({ path: args.path, namespace: 'auth-mock' }));
      builder.onLoad({ filter: /.*/, namespace: 'auth-mock' }, args => ({ contents: args.path === 'axios' ? 'export default globalThis.transport; export const isAxiosError=()=>false; export const AxiosHeaders=globalThis.require("axios").AxiosHeaders;' : args.path === 'sonner' ? 'export const toast={};' : args.path === './client' ? 'export const apiClient=globalThis.transport;' : 'export const useAppStore={getState:()=>globalThis.state};' }));
    } }],
  });
  vm.runInNewContext(output.outputFiles[0].text, runtime);
  return runtime;
}
const auth = await authBoundary('src/services/api/auth.ts');
await auth.module.exports.authApi.setMembershipPreview('free');
assert.equal(auth.calls[0][0], '/api/auth/membership-preview');
assert.equal(auth.calls[0][1].mode, 'free');
assert.equal(auth.calls[0][2].headers.Authorization, 'Bearer old-access');
auth.response.refresh_token = undefined;
await assert.rejects(() => auth.module.exports.authApi.setMembershipPreview('paid'), /Missing preview refresh token/);
const refresh = await authBoundary('src/services/api/client.ts', true);
assert.equal(await refresh.module.exports.performTokenRefresh(), 'fresh-access');
assert.equal(refresh.state.user.is_member, false);
assert.equal(refresh.state.user.membership_preview, null);
assert.equal(refresh.state.token, 'fresh-access'); assert.equal(refresh.state.refreshToken, 'fresh-refresh');
refresh.transport.post = async () => { throw new Error('expired preview'); };
assert.equal(await refresh.module.exports.performTokenRefresh(), null);
assert.equal(refresh.state.token, 'fresh-access');
console.log('PASS: authenticated preview request, missing refresh rejection, actual silent refresh updates effective user, expired refresh returns failure');
