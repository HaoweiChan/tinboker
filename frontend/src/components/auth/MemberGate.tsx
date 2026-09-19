import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAppStore } from '@/store/useAppStore';
import { LoginRequiredCard } from '@/components/auth/LoginRequiredCard';
import { BracketMark } from '@/components/logo/AppLogo';

interface MemberGateProps {
  children: ReactNode;
  /** Rendered blurred and non-interactive behind the upgrade card, so the gated
   *  page can sell itself instead of showing a blank wall. It is rendered into the
   *  real DOM (blur is cosmetic) — pass placeholder/teaser content only, never the
   *  gated data. */
  preview?: ReactNode;
}

/** Content gate, modelled on RequireLogin: not logged in -> the same login card
 *  (reused, not duplicated); logged in but not a paying member -> an upgrade card,
 *  optionally over a blurred `preview`; member -> children.
 *
 *  No /membership page or route wiring yet — this PR only adds the gate. */
export const MemberGate: React.FC<MemberGateProps> = ({ children, preview }) => {
  const isAuthReady = useAppStore((s) => s.isAuthReady);
  const user = useAppStore((s) => s.user);

  if (!isAuthReady) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <LoginRequiredCard />;

  if (!user.is_member) {
    const card = (
      <div className="w-full max-w-sm bg-card border border-border rounded-md overflow-hidden font-mono shadow-lg">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-background">
          <span className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary" />
            <span className="w-2.5 h-2.5 rounded-full bg-accent-info" />
            <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/40" />
          </span>
          <span className="text-2xs text-muted-foreground tracking-wide ml-1">tinboker — 會員專屬</span>
        </div>
        <div className="flex flex-col items-center gap-5 px-6 py-9 text-center">
          <BracketMark size={36} />
          <div className="space-y-1" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
            <p className="text-md font-bold text-foreground">會員專屬內容</p>
            <p className="text-sm text-muted-foreground">升級會員即可解鎖完整分析與獨家資料</p>
          </div>
          <Link
            to="/membership"
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition"
          >
            立即升級會員
          </Link>
        </div>
      </div>
    );

    if (!preview) {
      return <div className="flex items-center justify-center px-4 py-20">{card}</div>;
    }

    return (
      <div className="relative">
        <div aria-hidden inert className="pointer-events-none select-none blur-sm">
          {preview}
        </div>
        <div className="absolute inset-0 flex items-center justify-center px-4">{card}</div>
      </div>
    );
  }

  return <>{children}</>;
};
