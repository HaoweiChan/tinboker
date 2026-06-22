/**
 * Admin tag registry page — view tags with episode counts, toggle visibility,
 * discover new tags from Firestore, add/delete.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, Search, Trash2, Check, X, Eye, EyeOff, Radar, Layers } from 'lucide-react';
import {
  listAdminTags,
  createAdminTag,
  updateAdminTag,
  deleteAdminTag,
  discoverTags,
  syncSectors,
  type AdminTagEntry,
} from '@/services/api/adminTags';
import { SectorIcon } from '@/components/topics/SectorIcon';

const KIND_SECTOR = 'sector';

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
  const [kindFilter, setKindFilter] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showAddRow, setShowAddRow] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newDisplay, setNewDisplay] = useState('');
  const [discovering, setDiscovering] = useState(false);
  const [syncing, setSyncing] = useState(false);
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
      if (kindFilter) params.kind = kindFilter;
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await listAdminTags(params);
      setTags(res.tags);
    } catch (err) {
      console.error('Failed to fetch tags:', err);
    } finally {
      setLoading(false);
    }
  }, [tierFilter, kindFilter, debouncedSearch]);

  useEffect(() => { fetchTags(); }, [fetchTags]);

  const handleToggleTier = async (tag: AdminTagEntry) => {
    try {
      if (tag.registered === false || tag.id == null) {
        // Virtual tag (no registry row yet) → materialize it at the FLIPPED tier:
        // a visible vocab tag becomes hidden; a hidden off-vocab tag becomes trending
        // (promoting it past the vocabulary gate). Refetch so it shows as registered.
        const newTier = tag.tier === 'trending' ? 'hidden' : 'trending';
        await createAdminTag({ slug: tag.slug, display_zh: tag.display_zh, tier: newTier });
        await fetchTags();
        return;
      }
      const newTier = tag.tier === 'trending' ? 'hidden' : 'trending';
      const updated = await updateAdminTag(tag.id, { tier: newTier });
      setTags((prev) => prev.map((t) => (t.id === tag.id ? { ...t, ...updated } : t)));
    } catch (err) {
      console.error('Failed to update tier:', err);
    }
  };

  const handleDelete = async (tag: AdminTagEntry) => {
    if (tag.id == null) return; // virtual rows have no registry row to delete
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

  const handleSyncSectors = async () => {
    setSyncing(true);
    setDiscoverMsg('');
    try {
      const res = await syncSectors();
      setDiscoverMsg(res.message);
      await fetchTags();
    } catch (err) {
      console.error('Failed to sync sectors:', err);
      setDiscoverMsg('Sector sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const trendingCount = tags.filter((t) => t.tier === 'trending').length;
  const hiddenCount = tags.filter((t) => t.tier !== 'trending').length;

  return (
    <div className="mx-auto max-w-5xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Topic Registry</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {tags.length} topics — {trendingCount} visible · {hiddenCount} hidden
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
            onClick={handleSyncSectors}
            disabled={syncing}
            className="flex items-center gap-2 rounded-md border border-purple-300 px-3 py-2 text-sm text-purple-700 hover:bg-purple-50 disabled:opacity-50 dark:border-purple-600 dark:text-purple-300 dark:hover:bg-purple-900/20"
            title="Sync sectors/themes from the pipeline universe (new ones added as visible)"
          >
            <Layers className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            同步產業
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
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
        >
          <option value="">All kinds</option>
          <option value="tag">標籤 Tags</option>
          <option value="sector">產業 Sectors</option>
        </select>
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
        >
          <option value="">All</option>
          <option value="trending">Visible</option>
          <option value="hidden">Hidden</option>
        </select>
      </div>

      <p className="mb-4 -mt-1 text-xs text-gray-400">
        Off-vocabulary tags (auto-extracted, hidden from /topics) appear only when you search — find one and toggle it to “show” to promote it.
      </p>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3">Slug</th>
              <th className="px-4 py-3">顯示名稱</th>
              <th className="px-4 py-3">Kind</th>
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
                <td className="px-4 py-2 text-gray-400 text-xs">標籤</td>
                <td className="px-4 py-2 text-right text-gray-400">—</td>
                <td className="px-4 py-2 text-gray-400 text-xs">will be visible</td>
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
                <td colSpan={6} className="px-4 py-10 text-center text-gray-400">Loading…</td>
              </tr>
            ) : tags.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-gray-400">No tags found.</td>
              </tr>
            ) : (
              tags.map((tag) => {
                const isSector = tag.kind === KIND_SECTOR;
                const isVirtual = tag.registered === false;
                return (
                <tr key={`${tag.kind}:${tag.slug}`} className={`hover:bg-gray-50 dark:hover:bg-gray-800/50 ${tag.tier !== 'trending' ? 'opacity-60' : ''}`}>
                  <td className="px-4 py-2.5 font-mono text-sm text-gray-900 dark:text-white">
                    <span className="inline-flex items-center gap-2">
                      {isSector && (
                        <SectorIcon
                          exposureId={tag.exposure_id || tag.slug}
                          iconId={tag.icon_id}
                          color={tag.color_hex}
                          variant="chip"
                          size={13}
                        />
                      )}
                      {tag.slug}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 dark:text-gray-300">
                    {tag.display_zh}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${isSector
                      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                    }`}>
                      {isSector ? '產業' : '標籤'}
                    </span>
                    {isVirtual && (
                      <span
                        className="ml-1.5 inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                        title="Auto-surfaced from episodes — not yet in the registry. Hide it to create a registry row."
                      >
                        auto
                      </span>
                    )}
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
                    {isSector ? (
                      <span className="text-xs text-gray-400" title="Synced from the pipeline universe — hide it instead of deleting">
                        synced
                      </span>
                    ) : isVirtual ? (
                      <span className="text-xs text-gray-400" title="Auto-surfaced — hide it to create a registry row, then it can be deleted">
                        —
                      </span>
                    ) : (
                      <button
                        onClick={() => handleDelete(tag)}
                        className="rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30"
                        title="Delete tag"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
