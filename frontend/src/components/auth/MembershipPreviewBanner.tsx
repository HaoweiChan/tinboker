import { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';
import { sessionUser } from '@/lib/authSession';

const PREVIEW_ENV = import.meta.env.VITE_STAGE === 'DEV';

export function MembershipPreviewBanner() {
  const user = useAppStore((state) => state.user);
  const ready = useAppStore((state) => state.isAuthReady);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  if (!PREVIEW_ENV || !ready || !user?.membership_preview_available) return null;

  const changeMode = async (mode: 'free' | 'paid') => {
    setPending(true);
    setError('');
    try {
      const session = await authApi.setMembershipPreview(mode);
      useAppStore.getState().login(sessionUser(session.user), session.token, session.refresh_token);
      // A full reload clears member-only data held by mounted pages and query caches.
      window.location.reload();
    } catch {
      setError('切換失敗，請重試。');
      setPending(false);
    }
  };

  return (
    <aside aria-label="會員預覽" className="border-b border-primary/20 bg-primary/5 px-4 py-2 sm:px-6 lg:px-7">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <label className="flex items-center gap-2 font-medium">
          會員預覽
          <select value={user.membership_preview ?? (user.is_member ? 'paid' : 'free')} disabled={pending}
            onChange={(event) => { const mode = event.target.value; if (mode === 'free' || mode === 'paid') void changeMode(mode); }}
            className="min-h-8 rounded border border-border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50">
            <option value="free">免費會員</option>
            <option value="paid">付費會員</option>
          </select>
        </label>
        <span className="text-muted-foreground">不影響正式訂閱</span>
        {pending && <span role="status">切換中…</span>}
        {error && <span role="alert" className="w-full text-destructive">{error}</span>}
      </div>
    </aside>
  );
}
