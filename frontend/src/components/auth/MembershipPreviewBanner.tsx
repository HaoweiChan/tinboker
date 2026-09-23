import { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';
import { sessionUser } from '@/lib/authSession';

const PREVIEW_ENV = import.meta.env.VITE_STAGE === 'DEV'
  || (import.meta.env.DEV && !import.meta.env.VITE_STAGE);

export function MembershipPreviewBanner() {
  const user = useAppStore((state) => state.user);
  const ready = useAppStore((state) => state.isAuthReady);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  if (!PREVIEW_ENV || !ready || !user?.membership_preview_available) return null;

  const changeMode = async (mode: 'original' | 'free' | 'paid') => {
    setPending(true);
    setError('');
    try {
      const session = await authApi.setMembershipPreview(mode);
      useAppStore.getState().login(sessionUser(session.user), session.token, session.refresh_token);
      // A full reload clears member-only data held by mounted pages and query caches.
      window.location.reload();
    } catch {
      setError('切換失敗，請重試；預覽逾時請重新登入。');
      setPending(false);
    }
  };

  return (
    <aside aria-label="會員預覽" className="border-b border-primary/20 bg-primary/5 px-4 py-2 sm:px-6 lg:px-7">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <label className="flex items-center gap-2 font-medium">
          會員預覽
          <select value={user.membership_preview ?? 'original'} disabled={pending}
            onChange={(event) => { const mode = event.target.value; if (mode === 'original' || mode === 'free' || mode === 'paid') void changeMode(mode); }}
            className="min-h-8 rounded border border-border bg-card px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50">
            <option value="original">實際身分</option>
            <option value="free">免費會員</option>
            <option value="paid">付費會員</option>
          </select>
        </label>
        <span className="text-muted-foreground">不影響正式訂閱</span>
        <span className="text-[11px] text-muted-foreground">啟用預覽後，登入階段最長 1 小時。</span>
        {pending && <span role="status">切換中…</span>}
        {error && <span role="alert" className="w-full text-destructive">{error}</span>}
      </div>
    </aside>
  );
}
