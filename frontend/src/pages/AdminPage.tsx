/**
 * Admin layout wrapper with sidebar navigation.
 * All admin pages are nested under this layout.
 */

import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { AdminLogin } from '@/components/auth/AdminLogin';
import { AdminSidebar } from '@/components/admin/AdminSidebar';
import { useAppStore } from '@/store/useAppStore';
import { Menu, X } from 'lucide-react';

export const AdminPage: React.FC = () => {
    const logout = useAppStore((state) => state.logout);
    const [authenticated, setAuthenticated] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();

    // Close mobile menu on route change
    useEffect(() => {
        setMobileMenuOpen(false);
    }, [location.pathname]);

    const handleLogout = () => {
        logout();
        setAuthenticated(false);
        navigate('/admin');
    };

    const handleLoginSuccess = () => {
        setAuthenticated(true);
    };

    if (!authenticated) {
        return (
            <div className="min-h-screen bg-background">
                <AdminLogin onSuccess={handleLoginSuccess} />
            </div>
        );
    }

    return (
        <div className="flex min-h-screen bg-muted">
            {/* Mobile menu button */}
            <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="fixed left-4 top-4 z-50 rounded-md bg-card p-2 shadow-md lg:hidden"
                aria-label="Toggle menu"
            >
                {mobileMenuOpen ? (
                    <X className="h-6 w-6 text-muted-foreground" />
                ) : (
                    <Menu className="h-6 w-6 text-muted-foreground" />
                )}
            </button>

            {/* Mobile sidebar overlay */}
            {mobileMenuOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/50 lg:hidden"
                    onClick={() => setMobileMenuOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div
                className={`
          fixed inset-y-0 left-0 z-40 w-64 transform transition-transform duration-200 ease-in-out
          lg:relative lg:translate-x-0
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          ${sidebarOpen ? 'lg:w-64' : 'lg:w-16'}
        `}
            >
                <AdminSidebar
                    collapsed={!sidebarOpen}
                    onToggle={() => setSidebarOpen(!sidebarOpen)}
                    onLogout={handleLogout}
                />
            </div>

            {/* Main content */}
            <main className="flex-1 overflow-auto">
                <div className="min-h-screen p-4 pt-16 lg:p-6 lg:pt-6">
                    <Outlet context={{ authenticated, onLogout: handleLogout }} />
                </div>
            </main>
        </div>
    );
};
