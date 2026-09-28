type WorkerSlots<W> = { installing?: W | null; waiting?: W | null }

/**
 * Which service worker should 立即更新 activate?
 *
 * The NEWEST one. When a second deploy lands while a worker is already waiting,
 * the registration briefly holds both `waiting` (deploy N+1) and `installing`
 * (deploy N+2). Activating `waiting` there reloads into N+1 — already stale —
 * and the prompt comes straight back once N+2 finishes installing.
 */
export function pickUpdateTarget<W>(
  reg: WorkerSlots<W> | undefined,
): { worker: W; ready: boolean } | null {
  if (reg?.installing) return { worker: reg.installing, ready: false }
  if (reg?.waiting) return { worker: reg.waiting, ready: true }
  return null
}
