import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { Sun, Moon } from 'lucide-react';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useAppStore();
  const isDark = theme === 'dark';
  
  return (
    <button
      onClick={toggleTheme}
      className="w-10 h-10 rounded-full text-accent-info dark:text-accent-info hover:text-accent-info dark:hover:text-accent-info flex items-center justify-center transition focus:outline-none"
      aria-label="Toggle theme"
    >
      {isDark ? <Moon size={18} /> : <Sun size={18} />}
    </button>
  );
};
