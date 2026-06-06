import React, { useEffect, useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';
import { BracketMark } from '@/components/logo/AppLogo';
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';

interface AdminLoginProps {
  onSuccess?: () => void;
}

export const AdminLogin: React.FC<AdminLoginProps> = ({ onSuccess }) => {
  const isAuthReady = useAppStore((state) => state.isAuthReady);
  const user = useAppStore((state) => state.user);
  const token = useAppStore((state) => state.token);
  const logout = useAppStore((state) => state.logout);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isAuthReady || !user || !token) {
      setIsAdmin(null);
      return;
    }
    authApi.isAdmin(token).then(setIsAdmin);
  }, [isAuthReady, user, token]);

  useEffect(() => {
    if (isAdmin === true) onSuccess?.();
  }, [isAdmin, onSuccess]);

  if (!isAuthReady || (user && isAdmin === null)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-8">
        <BracketMark size={40} />
        <div className="text-center">
          <p className="text-[15px] font-semibold mb-1">管理員登入</p>
          <p className="text-[13px] text-muted-foreground">請以授權的 Google 帳號登入</p>
        </div>
        <GoogleLoginButton className="flex items-center gap-2.5 px-5 py-2.5 rounded-lg bg-card border border-border text-[14px] font-medium hover:bg-muted transition-colors">
          使用 Google 帳號登入
        </GoogleLoginButton>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-6">
      <BracketMark size={40} />
      <div className="text-center">
        <p className="text-[15px] font-semibold mb-1">無存取權限</p>
        <p className="text-[13px] text-muted-foreground">
          <span className="font-mono">{user.email}</span> 未在管理員名單中
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
};
