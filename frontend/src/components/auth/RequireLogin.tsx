import { Outlet } from 'react-router-dom';
import { useAppStore } from '@/store/useAppStore';
import { LoginRequiredCard } from '@/components/auth/LoginRequiredCard';

/** Route guard: renders the page only when logged in, else a login prompt.
 *  Wrap routes that should force registration. */
export const RequireLogin: React.FC = () => {
  const isAuthReady = useAppStore((s) => s.isAuthReady);
  const user = useAppStore((s) => s.user);

  if (!isAuthReady) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (user) return <Outlet />;

  return <LoginRequiredCard />;
};
