/**
 * Admin tag registry page — view, filter, add, edit tier, and delete tags.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, Search, Trash2, Check, X } from 'lucide-react';
import {
  listAdminTags,
  createAdminTag,
  updateAdminTag,
  deleteAdminTag,
  type AdminTagEntry,
} from '@/services/api/adminTags';

const TIER_OPTIONS = ['trending', 'valid', 'suppressed'] as const;

const TIER_COLORS: Record<string, string> = {
  trending: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  valid: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  suppressed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
};

function TierBadge({ tier, onClick }: { tier: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-opacity ${TIER_COLORS[tier] ?? 'bg-gray-100 text-gray-600'} ${onClick ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
    >
      {tier}
    </button>
  );
}

function TierSelector({ value, onChange, onCancel }: {
  value: string;
  onChange: (tier: string) => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {TIER_OPTIONS.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-all ${t === value
            ? `${TIER_COLORS[t]} ring-2 ring-offset-1 ring-blue-400`
            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600'
          }`}
        >
          {t}
        </button>
      ))}
      <button onClick={onCancel} className="ml-1 rounded p-0.5 text-gray-400 hover:text-gray-600">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export const AdminTagsPage: React.FC = () => {
  const [tags, setTags] = useState<AdminTagEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [editingTierId, setEditingTierId] = useState<number | null>(null);
  const [showAddRow, setShowAddRow] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newDisplay, setNewDisplay] = useState('');
  const [newTier, setNewTier] = useState('trending');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchTags = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (tierFilter) params.tier = tierFilter;
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await listAdminTags(params);
      setTags(res.tags);
    } catch (err) {
      console.error('Failed to fetch tags:', err);
    } finally {
      setLoading(false);
    }
  }, [tierFilter, debouncedSearch]);

  useEffect(() => { fetchTags(); }, [fetchTags]);

  const handleTierChange = async (id: number, newTier: string) => {
    try {
      const updated = await updateAdminTag(id, { tier: newTier });
      setTags((prev) => prev.map((t) => (t.id === id ? updated : t)));
    } catch (err) {
      console.error('Failed to update tier:', err);
    }
    setEditingTierId(null);
  };

  const handleDelete = async (tag: AdminTagEntry) => {
    if (!confirm(`Delete tag "${tag.slug}" (${tag.display_zh})?`)) return;
    try {
      await deleteAdminTag(tag.id);
      setTags((prev) => prev.filter((t) => t.id !== tag.id));
    } catch (err) {
      console.error('Failed to delete tag:', err);
    }
  };

  const handleAdd = async () => {
    if (!newSlug.trim() || !newDisplay.trim()) return;
    try {
      const created = await createAdminTag({
        slug: newSlug.trim().toLowerCase().replace(/\s+/g, '_'),
        display_zh: newDisplay.trim(),
        tier: newTier,
      });
      setTags((prev) => [...prev, created].sort((a, b) => a.slug.localeCompare(b.slug)));
      setShowAddRow(false);
      setNewSlug('');
      setNewDisplay('');
      setNewTier('trending');
    } catch (err) {
      console.error('Failed to create tag:', err);
    }
  };

  const counts = {
    trending: tags.filter((t) => t.tier === 'trending').length,
    valid: tags.filter((t) => t.tier === 'valid').length,
    suppressed: tags.filter((t) => t.tier === 'suppressed').length,
  };

  return (
    <div className="mx-auto max-w-5xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Tag Registry</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {tags.length} tags — {counts.trending} trending · {counts.valid} valid · {counts.suppressed} suppressed
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchTags}
            className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={() => setShowAddRow(true)}
            className="flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Tag
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search slug or display name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          />
        </div>
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
        >
          <option value="">All tiers</option>
          {TIER_OPTIONS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3">Slug</th>
              <th className="px-4 py-3">顯示名稱</th>
              <th className="px-4 py-3">Tier</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {/* Add row */}
            {showAddRow && (
              <tr className="bg-blue-50/50 dark:bg-blue-900/10">
                <td className="px-4 py-2">
                  <input
                    type="text"
                    value={newSlug}
                    onChange={(e) => setNewSlug(e.target.value)}
                    placeholder="tag_slug"
                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    autoFocus
                  />
                </td>
                <td className="px-4 py-2">
                  <input
                    type="text"
                    value={newDisplay}
                    onChange={(e) => setNewDisplay(e.target.value)}
                    placeholder="顯示名稱"
                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                </td>
                <td className="px-4 py-2">
                  <select
                    value={newTier}
                    onChange={(e) => setNewTier(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  >
                    {TIER_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={handleAdd}
                      className="rounded p-1 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30"
                      title="Save"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => { setShowAddRow(false); setNewSlug(''); setNewDisplay(''); }}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                      title="Cancel"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            )}

            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-gray-400">Loading…</td>
              </tr>
            ) : tags.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-gray-400">No tags found.</td>
              </tr>
            ) : (
              tags.map((tag) => (
                <tr key={tag.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-4 py-2.5 font-mono text-sm text-gray-900 dark:text-white">
                    {tag.slug}
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 dark:text-gray-300">
                    {tag.display_zh}
                  </td>
                  <td className="px-4 py-2.5">
                    {editingTierId === tag.id ? (
                      <TierSelector
                        value={tag.tier}
                        onChange={(t) => handleTierChange(tag.id, t)}
                        onCancel={() => setEditingTierId(null)}
                      />
                    ) : (
                      <TierBadge tier={tag.tier} onClick={() => setEditingTierId(tag.id)} />
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => handleDelete(tag)}
                      className="rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30"
                      title="Delete tag"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
