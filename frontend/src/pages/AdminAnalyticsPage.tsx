/**
 * Admin Analytics Page - Links to Cloudflare and Google Analytics dashboards.
 */

import React, { useEffect, useState } from 'react';
import { ExternalLink, TrendingUp, Users, Eye, Globe, Loader2 } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';

interface AnalyticsCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  href: string;
  bgGradient: string;
}

const AnalyticsCard: React.FC<AnalyticsCardProps> = ({
  title,
  description,
  icon,
  href,
  bgGradient,
}) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className={`group relative overflow-hidden rounded-2xl p-6 ${bgGradient} text-white shadow-lg transition-all hover:scale-[1.02] hover:shadow-xl`}
  >
    <div className="absolute right-4 top-4 opacity-70 group-hover:opacity-100 transition-opacity">
      <ExternalLink className="h-5 w-5" />
    </div>
    <div className="flex items-start gap-4">
      <div className="rounded-xl bg-white/20 p-3">
        {icon}
      </div>
      <div>
        <h3 className="text-xl font-semibold">{title}</h3>
        <p className="mt-1 text-sm opacity-90">{description}</p>
      </div>
    </div>
    <div className="mt-4 text-sm font-medium opacity-80 group-hover:opacity-100">
      Open Dashboard →
    </div>
  </a>
);

interface QuickStatProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  trend?: string;
  trendUp?: boolean;
}

const QuickStat: React.FC<QuickStatProps> = ({ label, value, icon, trend, trendUp }) => (
  <div className="rounded-xl bg-white p-5 shadow-sm dark:bg-gray-800">
    <div className="flex items-center justify-between">
      <div className="rounded-lg bg-gray-100 p-2 dark:bg-gray-700">
        {icon}
      </div>
      {trend && (
        <span className={`text-sm font-medium ${trendUp ? 'text-green-500' : 'text-red-500'}`}>
          {trendUp ? '↑' : '↓'} {trend}
        </span>
      )}
    </div>
    <div className="mt-4">
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{label}</p>
    </div>
  </div>
);

interface AnalyticsData {
  pageViews: number | string;
  uniqueVisitors: number | string;
  requests: number | string;
  visits: number | string;
  period: string;
}

interface AnalyticsResponse {
  configured: boolean;
  message: string;
  data: AnalyticsData | null;
  dashboards?: {
    cloudflare: string;
    googleAnalytics: string;
  };
}

const formatNumber = (num: number | string): string => {
  if (typeof num === 'string') return num;
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

export const AdminAnalyticsPage: React.FC = () => {
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      setLoading(true);
      setError(null);
      try {
        const token = useAppStore.getState().token;
        const apiBase = import.meta.env.DEV
          ? 'http://localhost:8000'
          : 'https://api.tinboker.com';
        const response = await fetch(`${apiBase}/api/admin/analytics/overview?days=7`, {
          headers: {
            Authorization: `Bearer ${token || ''}`,
          },
        });
        if (!response.ok) {
          if (response.status === 503) {
            setAnalytics({ configured: false, message: 'Not configured', data: null });
          } else {
            throw new Error(`HTTP ${response.status}`);
          }
        } else {
          const data = await response.json();
          setAnalytics(data);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Analytics
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Monitor traffic and user engagement across platforms
        </p>
      </div>

      {/* Analytics Dashboards */}
      <div className="grid gap-6 md:grid-cols-2">
        <AnalyticsCard
          title="Cloudflare Web Analytics"
          description="Real-time traffic, page views, visitors, and performance metrics"
          icon={<Globe className="h-6 w-6" />}
          href="https://dash.cloudflare.com/?to=/:account/:zone/analytics/web-analytics"
          bgGradient="bg-gradient-to-br from-orange-500 to-orange-600"
        />
        <AnalyticsCard
          title="Google Analytics"
          description="Detailed user behavior, acquisition, and conversion tracking"
          icon={<TrendingUp className="h-6 w-6" />}
          href="https://analytics.google.com/analytics/web/#/p464726391/reports/intelligenthome"
          bgGradient="bg-gradient-to-br from-blue-500 to-blue-600"
        />
      </div>

      {/* Quick Stats */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Quick Overview (Last 7 Days)
          </h2>
          {loading && <Loader2 className="h-5 w-5 animate-spin text-gray-400" />}
        </div>
        {error ? (
          <div className="rounded-lg bg-red-50 p-4 text-red-600 dark:bg-red-900/20 dark:text-red-400">
            Failed to load analytics: {error}
          </div>
        ) : !analytics?.configured ? (
          <div className="rounded-lg bg-yellow-50 p-4 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400">
            Analytics API not configured. Add CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_TAG to secrets.
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <QuickStat
                label="Page Views"
                value={analytics.data ? formatNumber(analytics.data.pageViews) : '—'}
                icon={<Eye className="h-5 w-5 text-blue-500" />}
              />
              <QuickStat
                label="Unique Visitors"
                value={analytics.data ? formatNumber(analytics.data.uniqueVisitors) : '—'}
                icon={<Users className="h-5 w-5 text-green-500" />}
              />
              <QuickStat
                label="Total Visits"
                value={analytics.data ? formatNumber(analytics.data.visits) : '—'}
                icon={<TrendingUp className="h-5 w-5 text-purple-500" />}
              />
              <QuickStat
                label="Requests"
                value={analytics.data ? formatNumber(analytics.data.requests) : '—'}
                icon={<Globe className="h-5 w-5 text-orange-500" />}
              />
            </div>
            <div className="mt-4 rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
              <p className="text-sm text-blue-800 dark:text-blue-200">
                <strong>Note:</strong> {analytics.message} For detailed real-time analytics, please use the dashboard links above.
              </p>
              {analytics.data && (
                <p className="mt-2 text-xs text-blue-600 dark:text-blue-300">
                  Period: {analytics.data.period}
                </p>
              )}
            </div>
          </>
        )}
      </div>

      {/* Google Search Console */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          SEO Performance
        </h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Track search rankings, indexing status, and organic traffic
        </p>
        <a
          href="https://search.google.com/search-console?resource_id=https://www.tinboker.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
        >
          Open Google Search Console
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {/* Tracking Info */}
      <div className="rounded-xl bg-blue-50 p-6 dark:bg-blue-900/20">
        <h3 className="font-semibold text-blue-900 dark:text-blue-300">
          Tracking Configuration
        </h3>
        <ul className="mt-3 space-y-2 text-sm text-blue-800 dark:text-blue-200">
          <li className="flex items-center gap-2">
            <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
            Cloudflare Web Analytics: Enabled (auto-injected)
          </li>
          <li className="flex items-center gap-2">
            <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
            Google Analytics: G-VYVPJ535WH
          </li>
          <li className="flex items-center gap-2">
            <span className="inline-flex h-2 w-2 rounded-full bg-yellow-500" />
            Google Search Console: Verify domain ownership
          </li>
        </ul>
      </div>
    </div>
  );
};
