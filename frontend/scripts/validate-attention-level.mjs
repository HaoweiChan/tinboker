// Run: node scripts/validate-attention-level.mjs
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { build } from 'esbuild';

const bundled = await build({
  entryPoints: [fileURLToPath(new URL('../src/validation/schemas.ts', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs',
});
const runtime = { module: { exports: {} } };
vm.runInNewContext(bundled.outputFiles[0].text, runtime);
const { AttentionLevelFieldsSchema: schema } = runtime.module.exports;
for (const level of [0, 50, 100]) {
  assert.equal(schema.parse({ attention_level: level }).attention_level, level);
}
for (const level of [-1, 101, 1.5, '87', NaN, Infinity, null]) {
  assert.equal(schema.parse({ attention_level: level }).attention_level, null);
}
assert.equal(schema.parse({}).attention_level, undefined);
assert.equal(schema.parse({ attention_as_of: '2026-09-23' }).attention_as_of, '2026-09-23');
assert.equal(schema.parse({ attention_as_of: 'invalid' }).attention_as_of, null);
console.log('PASS: valid levels including zero, missing/invalid levels, and date shape');
