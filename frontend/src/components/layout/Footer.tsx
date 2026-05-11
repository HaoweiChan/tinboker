import React from 'react';
import { Link } from 'react-router-dom';
import { AppLogo } from '@/components/logo/AppLogo';
import { Mail, MessageCircle, AtSign } from 'lucide-react';
import { useWithinAppLayout } from './LayoutContext';

export const Footer: React.FC = () => {
  // Transitional: the new shell (<AppLayout>) has no footer. Deleted in Phase 5.
  if (useWithinAppLayout()) return null;
  return (
    <footer className="bg-slate-50/80 dark:bg-slate-950/80 border-t border-slate-200/60 dark:border-slate-800/40 mt-auto py-10 md:py-14">
      <div className="container mx-auto px-4 flex flex-col items-center text-center">

        <div className="flex flex-col items-center gap-3 mb-8">
          <AppLogo size={32} />
          <span className="text-sm text-slate-400 dark:text-slate-500 font-medium tracking-wide">
            聽見市場聲音，看見財富趨勢
          </span>
        </div>

        <div className="flex items-center gap-3 mb-8">
          {[
            { href: 'mailto:contact@tinboker.com', icon: <Mail size={17} />, label: 'Email' },
            { href: 'https://www.threads.net/@tinboker', icon: <AtSign size={17} />, label: 'Threads', external: true },
            { href: '#', icon: <MessageCircle size={17} />, label: 'Line' },
          ].map(({ href, icon, label, external }) => (
            <a
              key={label}
              href={href}
              {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
              className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800/60 flex items-center justify-center text-slate-500 dark:text-slate-500 hover:bg-amber-50 dark:hover:bg-amber-500/10 hover:text-amber-500 dark:hover:text-amber-400 transition-all duration-200 hover:scale-110 active:scale-95"
              aria-label={label}
            >
              {icon}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-8 mb-8">
          {[
            { to: '/about', text: '關於我們' },
            { to: '/disclaimer', text: '免責聲明' },
          ].map(({ to, text }) => (
            <Link
              key={to}
              to={to}
              className="text-slate-500 dark:text-slate-500 hover:text-amber-500 dark:hover:text-amber-400 transition-colors duration-200 text-sm font-medium"
            >
              {text}
            </Link>
          ))}
        </div>

        <div className="w-full max-w-xs h-px bg-gradient-to-r from-transparent via-slate-200 dark:via-slate-800 to-transparent mb-6" />

        <div className="text-slate-400 dark:text-slate-600 text-xs tracking-wide">
          © {new Date().getFullYear()} TinBoker. All rights reserved.
        </div>
      </div>
    </footer>
  );
};
