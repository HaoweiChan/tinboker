/**
 * Filter controls for translation list.
 */

import React from 'react';
import { Search, Filter } from 'lucide-react';

interface TranslationFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  market: string;
  onMarketChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
}

const MARKETS = [
  { value: '', label: 'All Markets' },
  { value: 'US', label: 'US Stocks' },
  { value: 'TW', label: 'TW Stocks' },
  { value: 'JP', label: 'JP Stocks' },
];

const STATUSES = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'auto', label: 'Auto Import' },
];

export const TranslationFilters: React.FC<TranslationFiltersProps> = ({
  search,
  onSearchChange,
  market,
  onMarketChange,
  status,
  onStatusChange,
}) => {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search ticker or name..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full rounded-md border border-input bg-card py-2 pl-10 pr-4 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
        />
      </div>
      {/* Market Filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <select
          value={market}
          onChange={(e) => onMarketChange(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
        >
          {MARKETS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      {/* Status Filter */}
      <div>
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};
