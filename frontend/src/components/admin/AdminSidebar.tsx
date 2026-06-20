/**
 * Admin sidebar navigation component.
 */

import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard,
    Languages,
    Rss,
    SlidersHorizontal,
    BarChart3,
    FileText,
    Hash,
    Share2,
    ChevronLeft,
    ChevronRight,
    LogOut,
} from 'lucide-react';

interface AdminSidebarProps {
    collapsed: boolean;
    onToggle: () => void;
    onLogout: () => void;
}

interface NavItemProps {
    to: string;
    icon: React.ReactNode;
    label: string;
    collapsed: boolean;
    end?: boolean;
}

const NavItem: React.FC<NavItemProps> = ({ to, icon, label, collapsed, end }) => (
    <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${isActive
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
            } ${collapsed ? 'justify-center' : ''}`
        }
        title={collapsed ? label : undefined}
    >
        {icon}
        {!collapsed && <span>{label}</span>}
    </NavLink>
);

export const AdminSidebar: React.FC<AdminSidebarProps> = ({
    collapsed,
    onToggle,
    onLogout,
}) => {
    return (
        <aside className="flex h-full flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
            {/* Header */}
            <div
                className={`flex items-center border-b border-gray-200 px-4 py-4 dark:border-gray-700 ${collapsed ? 'justify-center' : 'justify-between'
                    }`}
            >
                {!collapsed && (
                    <div>
                        <h1 className="text-lg font-bold text-gray-900 dark:text-white">
                            Admin
                        </h1>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                            TinBoker Dashboard
                        </p>
                    </div>
                )}
                <button
                    onClick={onToggle}
                    className="hidden rounded-md p-1.5 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 lg:block"
                    title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                >
                    {collapsed ? (
                        <ChevronRight className="h-5 w-5" />
                    ) : (
                        <ChevronLeft className="h-5 w-5" />
                    )}
                </button>
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-1 p-3">
                <NavItem
                    to="/admin"
                    icon={<LayoutDashboard className="h-5 w-5" />}
                    label="Dashboard"
                    collapsed={collapsed}
                    end
                />
                <NavItem
                    to="/admin/translations"
                    icon={<Languages className="h-5 w-5" />}
                    label="Translations"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/sources"
                    icon={<Rss className="h-5 w-5" />}
                    label="Sources"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/pipeline"
                    icon={<SlidersHorizontal className="h-5 w-5" />}
                    label="Pipeline"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/articles"
                    icon={<FileText className="h-5 w-5" />}
                    label="Articles"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/tags"
                    icon={<Hash className="h-5 w-5" />}
                    label="Tags"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/social"
                    icon={<Share2 className="h-5 w-5" />}
                    label="Social"
                    collapsed={collapsed}
                />
                <NavItem
                    to="/admin/analytics"
                    icon={<BarChart3 className="h-5 w-5" />}
                    label="Analytics"
                    collapsed={collapsed}
                />
                {/* Future sections */}
                {/* <NavItem
          to="/admin/settings"
          icon={<Settings className="h-5 w-5" />}
          label="Settings"
          collapsed={collapsed}
        /> */}
            </nav>

            {/* Footer */}
            <div className="border-t border-gray-200 p-3 dark:border-gray-700">
                <button
                    onClick={onLogout}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 ${collapsed ? 'justify-center' : ''
                        }`}
                    title={collapsed ? 'Logout' : undefined}
                >
                    <LogOut className="h-5 w-5" />
                    {!collapsed && <span>Logout</span>}
                </button>
            </div>
        </aside>
    );
};
