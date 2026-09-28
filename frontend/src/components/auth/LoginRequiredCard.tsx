import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';
import { BracketMark } from '@/components/logo/AppLogo';

/** The "please log in" terminal card — shared by RequireLogin (route guard) and
 *  MemberGate (content gate), so the two never drift apart. */
export const LoginRequiredCard: React.FC = () => (
  <div className="flex items-center justify-center px-4 py-20">
    <div className="w-full max-w-sm bg-card border border-border rounded-md overflow-hidden font-mono">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-background">
        <span className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-primary" />
          <span className="w-2.5 h-2.5 rounded-full bg-accent-info" />
          <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/40" />
        </span>
        <span className="text-2xs text-muted-foreground tracking-wide ml-1">tinboker — 需要登入</span>
      </div>
      <div className="flex flex-col items-center gap-5 px-6 py-9 text-center">
        <BracketMark size={36} />
        <div className="space-y-1" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
          <p className="text-md font-bold text-foreground">登入後即可檢視</p>
          <p className="text-sm text-muted-foreground">免費註冊，解鎖個股情緒、話題與集數摘要</p>
        </div>
        <GoogleLoginButton className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition">
          使用 Google 登入 / 註冊
        </GoogleLoginButton>
      </div>
    </div>
  </div>
);
