import React from 'react';
import { NavLink } from 'react-router-dom';
import { BarChart2, Mic2, Languages, ChevronLeft, ChevronRight, Code2 } from 'lucide-react';

interface DevSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
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
      `flex items-center gap-3 rounded-lg px-3 py-2.5 text-base font-medium transition-colors ${
        isActive
          ? 'bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300'
          : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
      } ${collapsed ? 'justify-center' : ''}`
    }
    title={collapsed ? label : undefined}
  >
    {icon}
    {!collapsed && <span>{label}</span>}
  </NavLink>
);

export const DevSidebar: React.FC<DevSidebarProps> = ({ collapsed, onToggle }) => (
  <aside className="flex h-full flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
    <div
      className={`flex items-center border-b border-gray-200 px-4 py-4 dark:border-gray-700 ${
        collapsed ? 'justify-center' : 'justify-between'
      }`}
    >
      {!collapsed && (
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Dev Tools</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">dev.tinboker.com only</p>
        </div>
      )}
      <button
        onClick={onToggle}
        className="hidden rounded-md p-1.5 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 lg:block"
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronLeft className="h-5 w-5" />}
      </button>
    </div>

    <nav className="flex-1 space-y-1 p-3">
      <NavItem
        to="/dev"
        icon={<BarChart2 className="h-5 w-5" />}
        label="Grafana"
        collapsed={collapsed}
        end
      />
      <NavItem
        to="/dev/podcasters"
        icon={<Mic2 className="h-5 w-5" />}
        label="Podcasters"
        collapsed={collapsed}
      />
      <NavItem
        to="/dev/translations"
        icon={<Languages className="h-5 w-5" />}
        label="Translations"
        collapsed={collapsed}
      />
    </nav>

    <div className="border-t border-gray-200 p-3 dark:border-gray-700">
      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-400 dark:text-gray-500 ${
          collapsed ? 'justify-center' : ''
        }`}
      >
        <Code2 className="h-4 w-4 shrink-0" />
        {!collapsed && <span>DEV ENV</span>}
      </div>
    </div>
  </aside>
);
