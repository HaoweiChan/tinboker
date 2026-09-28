import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Settings, LogOut, Info, LayoutDashboard, Star } from 'lucide-react';
import { useAppStore, useUser, useLogout } from '@/store/useAppStore';
import { LoginButton } from '@/components/auth/LoginButton';
import { authApi } from '@/services/api/auth';

// Mirrors App.tsx: /admin routes exist on every non-production build. The installed
// dev/staging app has no URL bar, so this is the way into the back office.
const ADMIN_ENABLED = (import.meta.env.VITE_STAGE as string) !== 'PRODUCTION';

export const UserMenu: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const user = useUser();
  const logout = useLogout();
  const isAuthReady = useAppStore((state) => state.isAuthReady);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNavigation = (path: string) => {
    setIsOpen(false);
    navigate(path);
  };

  const handleLogout = async () => {
    setIsOpen(false);
    try {
      await authApi.logout();
    } catch (error) {
      console.warn('Logout request failed:', error);
    } finally {
      logout(); // Clear local state
      navigate('/');
    }
  };

  // Show a placeholder while auth is being validated to prevent flicker
  if (!isAuthReady) {
    return (
      <div className="w-10 h-10 rounded-full bg-muted animate-pulse" />
    );
  }

  if (!user) {
    return (
      <LoginButton className="text-base font-bold text-muted-foreground hover:text-foreground hover:bg-muted px-4 py-2 rounded-lg transition">
        登入
      </LoginButton>
    );
  }

  return (
    <div className="relative" ref={menuRef}>
      {/* Avatar Button */}
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-10 h-10 rounded-full bg-accent-info border-2 border-border hover:opacity-90 transition shadow-lg overflow-hidden"
        aria-label="User Menu"
      >
        {user.avatar ? (
          <img src={user.avatar} alt={`Avatar of ${user.name}`} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <span className="text-accent-info-foreground font-financial font-bold text-base">{user.initials || user.name.charAt(0)}</span>
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl bg-card border border-border shadow-xl overflow-hidden z-50">
          {/* User Info */}
          <div className="p-4 border-b border-border">
            <div className="font-bold text-foreground text-xl">{user.name}</div>
            <div className="text-muted-foreground text-xs">{user.email}</div>
          </div>

          {/* Menu Items */}
          <div className="py-2">
            {/* No 會員專區 row: /member is a permanent tab (mobile) and sidebar entry
                (desktop), so listing it here was a third door to the same page. */}
            <button
              onClick={() => handleNavigation('/watchlist')}
              className="w-full flex items-center gap-3 px-4 py-3 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <Star size={18} />
              <span>收藏</span>
            </button>
            <button
              onClick={() => handleNavigation('/settings')}
              className="w-full flex items-center gap-3 px-4 py-3 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <Settings size={18} />
              <span>帳號設定</span>
            </button>
            {ADMIN_ENABLED && (
              <button
                onClick={() => handleNavigation('/admin')}
                className="w-full flex items-center gap-3 px-4 py-3 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <LayoutDashboard size={18} />
                <span>後台</span>
              </button>
            )}
          </div>

          {/* Support — surfaces sidebar's 支援 group for mobile (where the
              desktop sidebar isn't visible). Same items show on desktop too;
              the small redundancy with the sidebar makes them more findable. */}
          <div className="border-t border-border py-2">
            <button
              onClick={() => handleNavigation('/about')}
              className="w-full flex items-center gap-3 px-4 py-3 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <Info size={18} />
              <span>關於</span>
            </button>
          </div>

          {/* Logout */}
          <div className="border-t border-border py-2">
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-3 text-destructive hover:bg-muted hover:text-destructive transition-colors"
            >
              <LogOut size={18} />
              <span>登出</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserMenu;
