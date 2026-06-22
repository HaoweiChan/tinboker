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
        ? 'bg-sentiment-bull-soft text-sentiment-bull hover:bg-sentiment-bull-soft/70'
        : 'bg-muted text-muted-foreground hover:bg-muted/70'
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
    if (tag.id == null) return;
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
          <h1 className="text-2xl font-bold text-foreground">Topic Registry</h1>
          <p className="text-base text-muted-foreground">
            {tags.length} topics — {trendingCount} visible · {hiddenCount} hidden
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="flex items-center gap-2 rounded-md border border-accent-info px-3 py-2 text-base text-accent-info hover:bg-accent-info-soft disabled:opacity-50"
            title="Scan Firestore for new tags with >= 3 episodes"
          >
            <Radar className={`h-4 w-4 ${discovering ? 'animate-spin' : ''}`} />
            Discover
          </button>
          <button
            onClick={handleSyncSectors}
            disabled={syncing}
            className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted disabled:opacity-50"
            title="Sync sectors/themes from the pipeline universe (new ones added as visible)"
          >
            <Layers className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            同步產業
          </button>
          <button
            onClick={fetchTags}
            className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={() => setShowAddRow(true)}
            className="flex items-center gap-2 rounded-md bg-accent-info px-3 py-2 text-base text-accent-info-foreground hover:bg-accent-info/90"
          >
            <Plus className="h-4 w-4" />
            Add Tag
          </button>
        </div>
      </div>

      {/* Discover feedback */}
      {discoverMsg && (
        <div className="mb-4 rounded-md border border-accent-info bg-accent-info-soft px-4 py-2.5 text-base text-foreground">
          {discoverMsg}
          <button onClick={() => setDiscoverMsg('')} className="ml-2 text-accent-info hover:text-accent-info/70">
            <X className="inline h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search slug or display name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-input bg-card py-2 pl-9 pr-3 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
          />
        </div>
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground"
        >
          <option value="">All kinds</option>
          <option value="tag">標籤 Tags</option>
          <option value="sector">產業 Sectors</option>
        </select>
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-base text-foreground"
        >
          <option value="">All</option>
          <option value="trending">Visible</option>
          <option value="hidden">Hidden</option>
        </select>
      </div>

      <p className="mb-4 -mt-1 text-xs text-muted-foreground">
        Off-vocabulary tags (auto-extracted, hidden from /topics) appear only when you search — find one and toggle it to "show" to promote it.
      </p>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-base">
          <thead className="bg-muted text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Slug</th>
              <th className="px-4 py-3">顯示名稱</th>
              <th className="px-4 py-3">Kind</th>
              <th className="px-4 py-3 text-right">Episodes</th>
              <th className="px-4 py-3">Visibility</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {/* Add row */}
            {showAddRow && (
              <tr className="bg-accent-info-soft">
                <td className="px-4 py-2">
                  <input
                    type="text"
                    value={newSlug}
                    onChange={(e) => setNewSlug(e.target.value)}
                    placeholder="tag_slug"
                    className="w-full rounded border border-input bg-card px-2 py-1 text-base text-foreground"
                    autoFocus
                  />
                </td>
                <td className="px-4 py-2">
                  <input
                    type="text"
                    value={newDisplay}
                    onChange={(e) => setNewDisplay(e.target.value)}
                    placeholder="顯示名稱"
                    className="w-full rounded border border-input bg-card px-2 py-1 text-base text-foreground"
                  />
                </td>
                <td className="px-4 py-2 text-muted-foreground text-xs">標籤</td>
                <td className="px-4 py-2 text-right text-muted-foreground">—</td>
                <td className="px-4 py-2 text-muted-foreground text-xs">will be visible</td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={handleAdd}
                      className="rounded p-1 text-sentiment-bull hover:bg-sentiment-bull-soft"
                      title="Save"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => { setShowAddRow(false); setNewSlug(''); setNewDisplay(''); }}
                      className="rounded p-1 text-muted-foreground hover:bg-muted"
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
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : tags.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">No tags found.</td>
              </tr>
            ) : (
              tags.map((tag) => {
                const isSector = tag.kind === KIND_SECTOR;
                const isVirtual = tag.registered === false;
                return (
                <tr key={`${tag.kind}:${tag.slug}`} className={`hover:bg-muted/50 ${tag.tier !== 'trending' ? 'opacity-60' : ''}`}>
                  <td className="px-4 py-2.5 font-mono text-base text-foreground">
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
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {tag.display_zh}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${isSector
                      ? 'bg-accent-info-soft text-accent-info'
                      : 'bg-primary/15 text-primary'
                    }`}>
                      {isSector ? '產業' : '標籤'}
                    </span>
                    {isVirtual && (
                      <span
                        className="ml-1.5 inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground"
                        title="Auto-surfaced from episodes — not yet in the registry. Hide it to create a registry row."
                      >
                        auto
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-base tabular-nums text-muted-foreground">
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
                      <span className="text-xs text-muted-foreground" title="Synced from the pipeline universe — hide it instead of deleting">
                        synced
                      </span>
                    ) : isVirtual ? (
                      <span className="text-xs text-muted-foreground" title="Auto-surfaced — hide it to create a registry row, then it can be deleted">
                        —
                      </span>
                    ) : (
                      <button
                        onClick={() => handleDelete(tag)}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
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
