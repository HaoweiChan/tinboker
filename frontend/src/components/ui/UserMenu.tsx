import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Settings, LogOut, MessageSquareText, Info } from 'lucide-react';
import { useAppStore, useUser, useLogout } from '@/store/useAppStore';
import { LoginButton } from '@/components/auth/LoginButton';
import { authApi } from '@/services/api/auth';

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
      <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-slate-700 animate-pulse" />
    );
  }

  if (!user) {
    return (
      <LoginButton className="text-sm font-bold text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white px-4 py-2 rounded-lg dark:hover:bg-slate-800 transition">
        登入
      </LoginButton>
    );
  }

  return (
    <div className="relative" ref={menuRef}>
      {/* Avatar Button */}
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-tr from-accent-info to-purple-600 border-2 border-slate-200 dark:border-slate-700 hover:opacity-90 transition shadow-lg overflow-hidden"
        aria-label="User Menu"
      >
        {user.avatar ? (
          <img src={user.avatar} alt={`Avatar of ${user.name}`} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <span className="text-slate-50 font-financial font-bold text-sm">{user.initials || user.name.charAt(0)}</span>
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-xl overflow-hidden z-50">
          {/* User Info */}
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <div className="font-bold text-slate-900 dark:text-slate-50 text-lg">{user.name}</div>
            <div className="text-slate-500 dark:text-slate-400 text-sm">{user.email}</div>
          </div>

          {/* Menu Items */}
          <div className="py-2">
            <button
              onClick={() => handleNavigation('/profile')}
              className="w-full flex items-center gap-3 px-4 py-3 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <User size={18} />
              <span>個人檔案</span>
            </button>
            <button
              onClick={() => handleNavigation('/settings')}
              className="w-full flex items-center gap-3 px-4 py-3 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <Settings size={18} />
              <span>帳號設定</span>
            </button>
          </div>

          {/* Support — surfaces sidebar's 支援 group for mobile (where the
              desktop sidebar isn't visible). Same items show on desktop too;
              the small redundancy with the sidebar makes them more findable. */}
          <div className="border-t border-slate-200 dark:border-slate-700 py-2">
            <button
              onClick={() => handleNavigation('/report')}
              className="w-full flex items-center gap-3 px-4 py-3 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <MessageSquareText size={18} />
              <span>意見回饋</span>
            </button>
            <button
              onClick={() => handleNavigation('/about')}
              className="w-full flex items-center gap-3 px-4 py-3 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <Info size={18} />
              <span>關於</span>
            </button>
          </div>

          {/* Logout */}
          <div className="border-t border-slate-200 dark:border-slate-700 py-2">
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-3 text-red-500 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-red-600 dark:hover:text-red-300 transition-colors"
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
