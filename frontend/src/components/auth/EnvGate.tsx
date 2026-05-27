import { useEffect, useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';
import { BracketMark } from '@/components/logo/AppLogo';
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';

const STAGE = import.meta.env.VITE_STAGE as string | undefined;
// Only gate on deployed dev/staging — local Vite dev server is never gated
const IS_GATED = !import.meta.env.DEV && STAGE !== 'PRODUCTION';
const ENV_LABEL = STAGE === 'STAGING' ? '測試環境' : '開發環境';

export const EnvGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!IS_GATED) return <>{children}</>;
  return <GateImpl>{children}</GateImpl>;
};

function GateImpl({ children }: { children: React.ReactNode }) {
  const isAuthReady = useAppStore((state) => state.isAuthReady);
  const user = useAppStore((state) => state.user);
  const token = useAppStore((state) => state.token);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isAuthReady || !user || !token) {
      setIsAdmin(null);
      return;
    }
    authApi.isAdmin(token).then(setIsAdmin);
  }, [isAuthReady, user, token]);

  // Waiting for auth init, or waiting for admin check after login
  if (!isAuthReady || (user && isAdmin === null)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <LoginScreen />;
  if (!isAdmin) return <DeniedScreen email={user.email} />;
  return <>{children}</>;
}

function LoginScreen() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-8">
      <div className="flex flex-col items-center gap-3">
        <BracketMark size={40} />
        <span className="text-[11px] font-semibold tracking-[0.1em] uppercase text-muted-foreground bg-muted px-2.5 py-1 rounded-full">
          {ENV_LABEL}
        </span>
      </div>
      <div className="text-center">
        <p className="text-[15px] font-semibold mb-1">僅限授權人員存取</p>
        <p className="text-[13px] text-muted-foreground">請以授權的 Google 帳號登入</p>
      </div>
      <GoogleLoginButton className="flex items-center gap-2.5 px-5 py-2.5 rounded-lg bg-card border border-border text-[14px] font-medium hover:bg-muted transition-colors">
        <GoogleIcon />
        使用 Google 帳號登入
      </GoogleLoginButton>
    </div>
  );
}

function DeniedScreen({ email }: { email: string }) {
  const logout = useAppStore((state) => state.logout);
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-6">
      <div className="flex flex-col items-center gap-3">
        <BracketMark size={40} />
        <span className="text-[11px] font-semibold tracking-[0.1em] uppercase text-muted-foreground bg-muted px-2.5 py-1 rounded-full">
          {ENV_LABEL}
        </span>
      </div>
      <div className="text-center">
        <p className="text-[15px] font-semibold mb-1">無存取權限</p>
        <p className="text-[13px] text-muted-foreground">
          <span className="font-mono">{email}</span> 未在授權名單中
        </p>
      </div>
      <button
        onClick={logout}
        className="text-[13px] text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
      >
        切換帳號
      </button>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" className="shrink-0">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}
