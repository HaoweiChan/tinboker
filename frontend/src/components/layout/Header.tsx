import React from 'react';
import { Link } from 'react-router-dom';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { AppLogo } from '@/components/logo/AppLogo';
import { UserMenu } from '@/components/ui/UserMenu';
import { NotificationDropdown } from '@/components/ui/NotificationDropdown';
import { SearchDropdown } from '@/components/ui/SearchDropdown';
import { useUser } from '@/store/useAppStore';
import { LoginButton } from '@/components/auth/LoginButton';
import { useWithinAppLayout } from './LayoutContext';

export const Header: React.FC = () => {
  const user = useUser();
  // Transitional: <AppLayout> renders its own header. Unmigrated pages still call
  // <Header/> but it no-ops inside the new shell. Deleted with the old Header in Phase 5.
  const insideAppLayout = useWithinAppLayout();
  if (insideAppLayout) return null;

  return (
    <header className="sticky top-0 z-50 w-full backdrop-blur-xl bg-white/85 dark:bg-slate-950/70 border-b border-slate-200/60 dark:border-white/[0.06] transition-all duration-300 flex flex-col shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.3)]">
      <div className="w-full py-2.5 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between gap-3 sm:gap-4">
          <Link to="/" className="flex items-center group flex-shrink-0 transition-transform duration-200 hover:scale-[1.02] active:scale-95">
            <AppLogo size={28} textClassName="text-slate-900 dark:text-slate-50" mobileCompact={true} />
          </Link>

          <div className="flex-1 max-w-2xl lg:mx-auto">
            <SearchDropdown mode="desktop" />
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0 ml-auto">
            <ThemeToggle />
            <NotificationDropdown />
            <div className="hidden sm:block">
              <UserMenu />
            </div>
            <div className="sm:hidden flex items-center">
              {user ? (
                <UserMenu />
              ) : (
                <LoginButton
                  className="p-2 text-sm font-bold text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-50 flex items-center"
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
