import { useCallback, useState } from 'react';
import { toast } from 'sonner';

/**
 * Optimistic removal with a 復原 toast, for the saved-items lists (/watchlist and
 * the 會員專區 tabs).
 *
 * The removed key is hidden immediately and restored if the toggle reports failure,
 * so a rejected server call doesn't silently drop a row. Callers filter their own
 * list with `removed` — it holds namespaced keys ('ticker:2330', 'topic:sp500', …)
 * so one hook can serve several lists on a page.
 */
export function useRemoveWithUndo() {
  const [removed, setRemoved] = useState<Set<string>>(new Set());

  const setHidden = useCallback((key: string, hidden: boolean) => {
    setRemoved((prev) => {
      const next = new Set(prev);
      if (hidden) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  /** Remove now, offer 復原. `toggle` flips the saved state server-side (or locally). */
  const removeWithUndo = useCallback((key: string, label: string, toggle: () => Promise<boolean>) => {
    setHidden(key, true);
    const removal = toggle();
    const toastId = toast(`已移除 ${label}`, {
      action: {
        label: '復原',
        onClick: async () => {
          setHidden(key, false);
          // Undo toggles back — only once the removal itself went through, or it would remove instead.
          if (!(await removal)) return;
          if (!(await toggle())) setHidden(key, true);
        },
      },
    });
    void removal.then((ok) => {
      if (ok) return;
      toast.dismiss(toastId); // the store already showed why
      setHidden(key, false);
    });
  }, [setHidden]);

  return { removed, removeWithUndo };
}
