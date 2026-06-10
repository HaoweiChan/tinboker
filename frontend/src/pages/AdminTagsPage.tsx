/**
 * Admin tag registry page — view tags with episode counts, toggle visibility,
 * discover new tags from Firestore, add/delete.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, Search, Trash2, Check, X, Eye, EyeOff, Radar } from 'lucide-react';
import {
  listAdminTags,
  createAdminTag,
  updateAdminTag,
  deleteAdminTag,
  discoverTags,
  type AdminTagEntry,
} from '@/services/api/adminTags';

function VisibilityToggle({ visible, onToggle }: { visible: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-all ${visible
        ? 'bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900/40 dark:text-green-300'
        : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400'
      }`}
      title={visible ? 'Showing in trending — click to hide' : 'Hidden — click to show in trending'}
    >
      {visible ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
      {visible ? 'Trending' : 'Hidden'}
    </button>
  );
}

export const AdminTagsPage: React.FC = () => {
  const [tags, setTags] = useState<AdminTagEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showAddRow, setShowAddRow] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newDisplay, setNewDisplay] = useState('');
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState('');

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

  const handleToggleTier = async (tag: AdminTagEntry) => {
    const newTier = tag.tier === 'trending' ? 'hidden' : 'trending';
    try {
      const updated = await updateAdminTag(tag.id, { tier: newTier });
      setTags((prev) => prev.map((t) => (t.id === tag.id ? { ...t, ...updated } : t)));
    } catch (err) {
      console.error('Failed to update tier:', err);
    }
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
        tier: 'trending',
      });
      setTags((prev) => [...prev, created].sort((a, b) => a.slug.localeCompare(b.slug)));
      setShowAddRow(false);
      setNewSlug('');
      setNewDisplay('');
    } catch (err) {
      console.error('Failed to create tag:', err);
    }
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoverMsg('');
    try {
      const res = await discoverTags(3);
      setDiscoverMsg(res.message);
      if (res.discovered > 0) await fetchTags();
    } catch (err) {
      console.error('Failed to discover tags:', err);
      setDiscoverMsg('Discovery failed');
    } finally {
      setDiscovering(false);
    }
  };

  const trendingCount = tags.filter((t) => t.tier === 'trending').length;
  const hiddenCount = tags.filter((t) => t.tier !== 'trending').length;

  return (
    <div className="mx-auto max-w-5xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Tag Registry</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {tags.length} tags — {trendingCount} trending · {hiddenCount} hidden
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="flex items-center gap-2 rounded-md border border-blue-300 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-600 dark:text-blue-300 dark:hover:bg-blue-900/20"
            title="Scan Firestore for new tags with >= 3 episodes"
          >
            <Radar className={`h-4 w-4 ${discovering ? 'animate-spin' : ''}`} />
            Discover
          </button>
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

      {/* Discover feedback */}
      {discoverMsg && (
        <div className="mb-4 rounded-md border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
          {discoverMsg}
          <button onClick={() => setDiscoverMsg('')} className="ml-2 text-blue-500 hover:text-blue-700">
            <X className="inline h-3.5 w-3.5" />
          </button>
        </div>
      )}

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
          <option value="">All</option>
          <option value="trending">Trending</option>
          <option value="hidden">Hidden</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3">Slug</th>
              <th className="px-4 py-3">顯示名稱</th>
              <th className="px-4 py-3 text-right">Episodes</th>
              <th className="px-4 py-3">Visibility</th>
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
                <td className="px-4 py-2 text-right text-gray-400">—</td>
                <td className="px-4 py-2 text-gray-400 text-xs">will be trending</td>
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
                <td colSpan={5} className="px-4 py-10 text-center text-gray-400">Loading…</td>
              </tr>
            ) : tags.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-gray-400">No tags found.</td>
              </tr>
            ) : (
              tags.map((tag) => (
                <tr key={tag.id} className={`hover:bg-gray-50 dark:hover:bg-gray-800/50 ${tag.tier !== 'trending' ? 'opacity-60' : ''}`}>
                  <td className="px-4 py-2.5 font-mono text-sm text-gray-900 dark:text-white">
                    {tag.slug}
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 dark:text-gray-300">
                    {tag.display_zh}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-sm tabular-nums text-gray-600 dark:text-gray-400">
                    {tag.episode_count != null ? tag.episode_count.toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <VisibilityToggle
                      visible={tag.tier === 'trending'}
                      onToggle={() => handleToggleTier(tag)}
                    />
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
