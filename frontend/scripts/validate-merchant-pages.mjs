import assert from 'node:assert/strict';
import { build } from 'esbuild';
import vm from 'node:vm';
import { existsSync } from 'node:fs';

function flatten(node) { return !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(flatten)]; }
function text(node) { return typeof node === 'string' || typeof node === 'number' ? String(node) : node && typeof node === 'object' ? [node.props?.children].flat(Infinity).map(text).join('') : ''; }
async function render(plans) {
  const runtime = { module: { exports: {} }, hooks: [], index: 0, plans };
  const mocks = {
    react: 'export const useState=v=>{const i=globalThis.index++;if(!(i in globalThis.hooks))globalThis.hooks[i]=v;return[globalThis.hooks[i],v=>globalThis.hooks[i]=v];};export const useEffect=fn=>{globalThis.effect=fn;};',
    'react/jsx-runtime': 'export const jsx=(type,props)=>({type,props});export const jsxs=jsx;export const Fragment="fragment";',
    'react-router-dom': 'export const Link="a";',
    '@/components/common/SEO': 'export const SEO="metadata";',
    '@/components/layout/PageContent': 'export const PageContent="main";',
    '@/services/api/billing': 'export const getMembershipPlans=async()=>{if(!globalThis.plans)throw new Error("unavailable");return globalThis.plans;};',
  };
  const output = await build({ entryPoints: ['src/pages/MembershipPage.tsx'], tsconfig: 'tsconfig.app.json', bundle: true, write: false, format: 'cjs', platform: 'node', plugins: [{ name: 'boundaries', setup(builder) {
    builder.onResolve({ filter: /.*/ }, args => mocks[args.path] ? { path: args.path, namespace: 'mock' } : undefined);
    builder.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: mocks[args.path] }));
  } }] });
  vm.runInNewContext(output.outputFiles[0].text, runtime);
  runtime.module.exports.default(); runtime.effect(); await new Promise(resolve => setImmediate(resolve));
  runtime.index = 0; return runtime.module.exports.default();
}
const page = await render({ list_price: 199, founding_price: 99, founding_open: true, checkout_open: true });
assert.match(text(page), /NT\$ 199/); assert.match(text(page), /NT\$ 99/);
assert.match(text(page), /目前不接受付款/);
const buttons = flatten(page).filter(node => node.type === 'button');
assert.equal(buttons.length, 1); assert.equal(buttons[0].props.disabled, true);
for (const image of flatten(page).filter(node => node.type === 'img')) assert.ok(existsSync(`public${image.props.src}`));
const unavailable = await render(null);
assert.match(text(unavailable), /價格資訊暫時無法載入/);
assert.doesNotMatch(text(unavailable), /NT\$/);
console.log('PASS: API prices, no invented fallback, no checkout even if upstream enabled, and real screenshot assets present');
