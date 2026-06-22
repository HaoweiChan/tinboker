/**
 * Filter controls for the content-source list: type tabs + search + locale/active filters.
 */

import React from 'react';
import { Search, Filter, Podcast, Newspaper } from 'lucide-react';
import type { SourceType } from '@/types/contentSource';

interface SourceFiltersProps {
  sourceType: SourceType;
  onSourceTypeChange: (value: SourceType) => void;
  search: string;
  onSearchChange: (value: string) => void;
  locale: string;
  onLocaleChange: (value: string) => void;
  active: string;
  onActiveChange: (value: string) => void;
}

// Podcasts filter by content language; news feeds filter by region.
const LOCALE_OPTIONS: Record<SourceType, { value: string; label: string }[]> = {
  podcast: [
    { value: '', label: 'All Languages' },
    { value: 'zh-TW', label: 'Chinese (zh-TW)' },
    { value: 'en', label: 'English' },
  ],
  news: [
    { value: '', label: 'All Regions' },
    { value: 'US', label: 'US' },
    { value: 'TW', label: 'TW' },
  ],
};

const ACTIVE_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Inactive' },
];

const TABS: { value: SourceType; label: string; icon: React.ReactNode }[] = [
  { value: 'podcast', label: 'Podcasts', icon: <Podcast className="h-4 w-4" /> },
  { value: 'news', label: 'News Feeds', icon: <Newspaper className="h-4 w-4" /> },
];

export const SourceFilters: React.FC<SourceFiltersProps> = ({
  sourceType,
  onSourceTypeChange,
  search,
  onSearchChange,
  locale,
  onLocaleChange,
  active,
  onActiveChange,
}) => {
  return (
    <div className="space-y-4">
      {/* Type tabs */}
      <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => onSourceTypeChange(tab.value)}
            className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-base font-medium transition-colors ${
              sourceType === tab.value
                ? 'bg-accent-info text-accent-info-foreground'
                : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search name, slug, or feed URL..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full rounded-md border border-input bg-card py-2 pl-10 pr-4 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            value={locale}
            onChange={(e) => onLocaleChange(e.target.value)}
            className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
          >
            {LOCALE_OPTIONS[sourceType].map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <select
          value={active}
          onChange={(e) => onActiveChange(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
        >
          {ACTIVE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};
