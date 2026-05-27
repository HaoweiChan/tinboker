import React, { useState, useEffect, useRef } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { toast } from 'sonner';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

interface GoogleLoginButtonProps {
  className?: string;
  children?: React.ReactNode;
  type?: 'icon' | 'standard';
}

const POPUP_TIMEOUT_MS = 5000;

export const GoogleLoginButton: React.FC<GoogleLoginButtonProps> = ({ className, children }) => {
  const login = useAppStore((state) => state.login);
  const [isLoading, setIsLoading] = useState(false);
  const popupTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (popupTimer.current) clearTimeout(popupTimer.current);
    };
  }, []);

  const devLogin = () => {
    const dummyUser = {
      id: 'dev-user-123',
      name: 'Dev User',
      email: 'dev@tinboker.local',
      avatar: '',
      initials: 'DU',
    };
    const dummyToken = 'dev-token-' + Date.now();

    login(dummyUser, dummyToken);
    useAppStore.setState({
      isAuthReady: true,
      watchlist: [],
      subscriptions: [],
      alerts: [],
    });
    toast.success('開發模式登入成功');
  };

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      if (popupTimer.current) clearTimeout(popupTimer.current);
      try {
        const authResponse = await authApi.verifyGoogleToken({
          accessToken: tokenResponse.access_token,
        });
        const { user: backendUser, token: appToken } = authResponse;

        login(
          {
            id: backendUser.id,
            name: backendUser.name,
            email: backendUser.email,
            avatar: backendUser.avatar || '',
            initials: backendUser.name
              .split(' ')
              .map((n: string) => n[0])
              .join('')
              .toUpperCase()
              .slice(0, 2),
          },
          appToken,
        );

        useAppStore.setState({
          watchlist: backendUser.watchlist || [],
          subscriptions: backendUser.podcast_subscriptions || [],
          tagSubscriptions: backendUser.tag_subscriptions || [],
          alerts: backendUser.alerts || [],
        });
        toast.success(`歡迎回來，${backendUser.name}！`);
      } catch (error) {
        console.error('Login failed:', error);
        toast.error('登入失敗，請稍後再試');
      } finally {
        setIsLoading(false);
      }
    },
    onError: () => {
      if (popupTimer.current) clearTimeout(popupTimer.current);
      setIsLoading(false);
      console.error('Google login error');
      toast.error('Google 登入失敗');
    },
    flow: 'implicit',
  });

  const handleClick = () => {
    if (isLoading) return;

    if (import.meta.env.DEV) {
      devLogin();
      return;
    }

    setIsLoading(true);
    googleLogin();

    // If popup is blocked, the onSuccess/onError never fires.
    // Reset loading state and show a helpful toast after a timeout.
    popupTimer.current = setTimeout(() => {
      if (isLoading) {
        setIsLoading(false);
        toast.error('無法開啟登入視窗，請檢查瀏覽器是否封鎖了彈出式視窗', { duration: 6000 });
      }
    }, POPUP_TIMEOUT_MS);
  };

  return (
    <button
      onClick={handleClick}
      className={className}
      type="button"
      disabled={isLoading}
    >
      {isLoading ? (
        <span className="flex items-center gap-2">
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          登入中...
        </span>
      ) : (
        children || '登入'
      )}
    </button>
  );
};
