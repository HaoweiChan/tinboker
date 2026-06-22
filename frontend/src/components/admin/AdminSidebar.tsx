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
            `flex items-center gap-3 rounded-lg px-3 py-2.5 text-base font-medium transition-colors ${isActive
                ? 'bg-accent-info-soft text-accent-info'
                : 'text-foreground hover:bg-muted'
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
        <aside className="flex h-full flex-col border-r border-border bg-card">
            {/* Header */}
            <div
                className={`flex items-center border-b border-border px-4 py-4 ${collapsed ? 'justify-center' : 'justify-between'
                    }`}
            >
                {!collapsed && (
                    <div>
                        <h1 className="text-xl font-bold text-foreground">
                            Admin
                        </h1>
                        <p className="text-xs text-muted-foreground">
                            TinBoker Dashboard
                        </p>
                    </div>
                )}
                <button
                    onClick={onToggle}
                    className="hidden rounded-md p-1.5 text-muted-foreground hover:bg-muted lg:block"
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
            <div className="border-t border-border p-3">
                <button
                    onClick={onLogout}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-base font-medium text-foreground transition-colors hover:bg-muted ${collapsed ? 'justify-center' : ''
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
