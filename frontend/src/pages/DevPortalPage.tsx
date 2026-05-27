import React, { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { DevSidebar } from '@/components/dev/DevSidebar';
import { Menu, X } from 'lucide-react';

export const DevPortalPage: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen bg-gray-100 dark:bg-gray-900">
      <button
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        className="fixed left-4 top-4 z-50 rounded-md bg-white p-2 shadow-md dark:bg-gray-800 lg:hidden"
        aria-label="Toggle menu"
      >
        {mobileMenuOpen ? (
          <X className="h-6 w-6 text-gray-600 dark:text-gray-300" />
        ) : (
          <Menu className="h-6 w-6 text-gray-600 dark:text-gray-300" />
        )}
      </button>

      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <div
        className={`
          fixed inset-y-0 left-0 z-40 w-64 transform transition-transform duration-200 ease-in-out
          lg:relative lg:translate-x-0
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          ${sidebarOpen ? 'lg:w-64' : 'lg:w-16'}
        `}
      >
        <DevSidebar collapsed={!sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      </div>

      <main className="flex-1 overflow-auto">
        <div className="min-h-screen p-4 pt-16 lg:p-6 lg:pt-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
