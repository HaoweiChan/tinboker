import React from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { toast } from 'sonner';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

interface GoogleLoginButtonProps {
  className?: string;
  children?: React.ReactNode;
  type?: 'icon' | 'standard';
}

export const GoogleLoginButton: React.FC<GoogleLoginButtonProps> = ({ className, children }) => {
  const login = useAppStore((state) => state.login);

  // Dev mode: Bypass Google OAuth with dummy user
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

    // Set some dummy preferences
    useAppStore.setState({
      watchlist: [],
      subscriptions: [],
      alerts: []
    });

    toast.success('開發模式登入成功');
  };

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        // Exchange access token for app session
        const authResponse = await authApi.verifyGoogleToken({
          accessToken: tokenResponse.access_token
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
          appToken
        );

        // Sync user preferences to store
        useAppStore.setState({
          watchlist: backendUser.watchlist || [],
          subscriptions: backendUser.podcast_subscriptions || [],
          tagSubscriptions: backendUser.tag_subscriptions || [],
          alerts: backendUser.alerts || []
        });

        toast.success(`歡迎回來，${backendUser.name}！`);
      } catch (error) {
        console.error('Login failed:', error);
        toast.error('登入失敗，請稍後再試');
      }
    },
    onError: () => {
      console.error('Google login error');
      toast.error('Google 登入失敗');
    },
    flow: 'implicit', // Get access token
  });

  const handleClick = () => {
    // In dev mode, use dummy login
    if (import.meta.env.DEV) {
      devLogin();
    } else {
      googleLogin();
    }
  };

  return (
    <button
      onClick={handleClick}
      className={className}
      type="button"
    >
      {children || '登入'}
    </button>
  );
};
