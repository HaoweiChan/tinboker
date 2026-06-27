import React, { useEffect } from 'react';
import { Modal } from '@/components/ui/Modal';
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';
import { BracketMark } from '@/components/logo/AppLogo';
import { useAppStore } from '@/store/useAppStore';

/**
 * Global login prompt opened by `useRequireAuth()` when a logged-out visitor
 * triggers a gated action (bookmark, watchlist, comment) on a public page.
 * Mounted once in AppLayout. Auto-closes once login succeeds.
 */
export const LoginPromptModal: React.FC = () => {
  const open = useAppStore((s) => s.loginPromptOpen);
  const close = useAppStore((s) => s.closeLoginPrompt);
  const user = useAppStore((s) => s.user);

  useEffect(() => {
    if (user && open) close();
  }, [user, open, close]);

  return (
    <Modal isOpen={open} onClose={close} title="登入後即可使用">
      <div className="flex flex-col items-center gap-5 px-6 py-9 text-center">
        <BracketMark size={36} />
        <div className="space-y-1" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
          <p className="text-md font-bold text-foreground">登入解鎖完整功能</p>
          <p className="text-sm text-muted-foreground">免費註冊，即可收藏集數、加入自選股與留言</p>
        </div>
        <GoogleLoginButton className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition">
          使用 Google 登入 / 註冊
        </GoogleLoginButton>
      </div>
    </Modal>
  );
};
