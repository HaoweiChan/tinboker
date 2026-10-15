// Exercise the real hook with minimal React/API doubles, including its module cache.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const requests = [];
let state;
let effect;
const code = ts.transpileModule(readFileSync(new URL('../src/hooks/useStockPriceSinceMap.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = {
  exports: {},
  require: (name) => {
    if (name === 'react') return {
      useState: () => [state, (next) => { state = next; }],
      useEffect: (fn) => { effect = fn; },
    };
    if (name === '@/services/api/client') return { apiClient: {
      post: (url, payload) => new Promise((resolve) => { requests.push({ url, payload, resolve }); }),
    } };
    throw new Error(`Unexpected import: ${name}`);
  },
};
vm.runInNewContext(code, context);
const hook = context.exports.useStockPriceSinceMap;
const day = 86_400_000;
const dateA = Date.now() - 10 * day;
const dateB = dateA + day;
const episode = (date) => ({ id: String(date), released_at_ms: date, created_time: date, related_tickers: ['2330'] });
const render = (episodes) => { hook(episodes); effect(); };
const settle = async () => { await Promise.resolve(); await Promise.resolve(); };

render([episode(dateA)]);
assert.equal(requests.length, 1);
assert.equal(requests[0].payload.items[0].reference_ms, dateA);
requests[0].resolve({ data: { '2330': 10 } });
await settle();
assert.equal(state.get('2330'), 10);
render([episode(dateB)]);
assert.equal(requests.length, 2, 'same ticker on a different release date must fetch again');
assert.equal(requests[1].payload.items[0].reference_ms, dateB);
assert.equal(state.get('2330'), undefined, 'previous episode return is cleared while loading');
requests[1].resolve({ data: { '2330': 20 } });
await settle();
assert.equal(state.get('2330'), 20);
render([episode(dateA)]);
assert.equal(requests.length, 2, 'returning to the original date reuses its cache');
assert.equal(state.get('2330'), 10);
render([]);
assert.equal(state.size, 0, 'empty subjects clear prior returns');
render([episode(Date.now())]);
assert.equal(requests.length, 2, 'recent episodes do not show a misleading since-return');
console.log('validate-price-since: ok');
