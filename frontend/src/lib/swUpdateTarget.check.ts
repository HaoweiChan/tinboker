// Runnable check: node src/lib/swUpdateTarget.check.ts
import { pickUpdateTarget } from './swUpdateTarget.ts'

const eq = (got: unknown, want: unknown, label: string) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    throw new Error(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
  }
}

eq(pickUpdateTarget({ waiting: 'n+1' }), { worker: 'n+1', ready: true }, 'one deploy')
eq(pickUpdateTarget({ installing: 'n+1' }), { worker: 'n+1', ready: false }, 'still downloading')
// The bug: a second deploy installing while the first waits must win.
eq(pickUpdateTarget({ waiting: 'n+1', installing: 'n+2' }), { worker: 'n+2', ready: false }, 'two deploys')
eq(pickUpdateTarget({ waiting: null, installing: null }), null, 'stale prompt')
eq(pickUpdateTarget(undefined), null, 'no registration')
console.log('swUpdateTarget: ok')
