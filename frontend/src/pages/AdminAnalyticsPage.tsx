/**
 * Admin Analytics Page - Links to Cloudflare and Google Analytics dashboards,
 * plus tracking configuration status.
 */

import React from 'react';
import { ExternalLink, TrendingUp, Globe, Search, CheckCircle, AlertTriangle } from 'lucide-react';

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

interface TrackingItemProps {
  label: string;
  detail: string;
  status: 'active' | 'pending';
}

const TrackingItem: React.FC<TrackingItemProps> = ({ label, detail, status }) => (
  <li className="flex items-center gap-3 rounded-lg px-3 py-2.5">
    {status === 'active' ? (
      <CheckCircle className="h-4 w-4 flex-shrink-0 text-green-500" />
    ) : (
      <AlertTriangle className="h-4 w-4 flex-shrink-0 text-yellow-500" />
    )}
    <div className="min-w-0">
      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</span>
      <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">{detail}</span>
    </div>
  </li>
);

export const AdminAnalyticsPage: React.FC = () => {
  return (
    <div className="mx-auto max-w-7xl space-y-8">
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

      {/* Google Search Console */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-gray-100 p-2 dark:bg-gray-700">
            <Search className="h-5 w-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              SEO Performance
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Track search rankings, indexing status, and organic traffic
            </p>
          </div>
        </div>
        <a
          href="https://search.google.com/search-console?resource_id=https://tinboker.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
        >
          Open Google Search Console
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {/* Tracking Configuration */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Tracking Configuration
        </h3>
        <ul className="mt-3 space-y-1">
          <TrackingItem
            label="Cloudflare Web Analytics"
            detail="Enabled (auto-injected via Cloudflare Pages)"
            status="active"
          />
          <TrackingItem
            label="Google Analytics"
            detail="G-VYVPJ535WH"
            status="active"
          />
          <TrackingItem
            label="Google Search Console"
            detail="Verify domain ownership"
            status="pending"
          />
        </ul>
      </div>
    </div>
  );
};
