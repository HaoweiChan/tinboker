// Runnable check: node src/lib/savedCount.check.ts
import { savedCount } from './savedCount.ts'

const eq = (got: number, want: number, label: string) => {
  if (got !== want) throw new Error(`${label}: got ${got}, want ${want}`)
}

eq(savedCount(0, 0, 3), 3, 'still loading — show the id count')
eq(savedCount(3, 3, 3), 3, 'loaded, nothing swiped')
eq(savedCount(3, 2, 3), 2, 'one swiped away')
// The regression: the last card swiped away must read 0, not the stale id count.
eq(savedCount(1, 0, 1), 0, 'last one swiped away')
eq(savedCount(3, 0, 3), 0, 'all swiped away')
eq(savedCount(2, 2, 3), 2, 'one id never resolved')
console.log('savedCount: ok')
