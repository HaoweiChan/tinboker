/**
 * Admin tag registry page — view tags with episode counts, toggle visibility,
 * discover new tags from Firestore, add/delete.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, RefreshCw, Search, Trash2, Check, X, Eye, EyeOff, Radar, Layers, Pencil, Lightbulb, ChevronUp, ChevronDown } from 'lucide-react';
import {
  listAdminTags,
  createAdminTag,
  updateAdminTag,
  deleteAdminTag,
  discoverTags,
  syncSectors,
  getThemeCandidates,
  type AdminTagEntry,
  type ThemeCandidate,
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
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  // Theme discovery queue (lazy: scans Firestore, so only load when opened)
  const [candidatesOpen, setCandidatesOpen] = useState(false);
  const [candidates, setCandidates] = useState<ThemeCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [expandedTerm, setExpandedTerm] = useState<string | null>(null);

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

  // Episodes column sort: off (registered-first default) -> desc -> asc -> off.
  const [episodeSort, setEpisodeSort] = useState<'desc' | 'asc' | null>(null);
  const toggleEpisodeSort = () =>
    setEpisodeSort((s) => (s === null ? 'desc' : s === 'desc' ? 'asc' : null));
  const displayTags = useMemo(() => {
    if (!episodeSort) return tags;
    const dir = episodeSort === 'asc' ? 1 : -1;
    return [...tags].sort((a, b) => {
      const av = a.episode_count, bv = b.episode_count;
      // Uncounted (virtual "—") rows always sort to the bottom.
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * dir;
    });
  }, [tags, episodeSort]);

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

  const handleSaveDisplay = async (tag: AdminTagEntry) => {
    const value = editValue.trim();
    if (!value || value === tag.display_zh) { setEditKey(null); return; }
    try {
      // Virtual rows (no registry id) get a real row created, mirroring the toggle.
      if (tag.registered === false || tag.id == null) {
        await createAdminTag({ slug: tag.slug, display_zh: value, tier: tag.tier });
        await fetchTags();
      } else {
        const updated = await updateAdminTag(tag.id, { display_zh: value });
        setTags((prev) => prev.map((t) => (t.id === tag.id ? { ...t, ...updated } : t)));
      }
    } catch (err) {
      console.error('Failed to update display name:', err);
    } finally {
      setEditKey(null);
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

  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    try {
      setCandidates(await getThemeCandidates(3, 40));
      setCandidatesLoaded(true);
    } catch (err) {
      console.error('Failed to fetch theme candidates:', err);
    } finally {
      setCandidatesLoading(false);
    }
  }, []);

  const toggleCandidates = () => {
    const next = !candidatesOpen;
    setCandidatesOpen(next);
    if (next && !candidatesLoaded) loadCandidates();
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

      {/* Theme discovery queue — emerging concepts not yet curated */}
      <div className="mb-4 rounded-lg border border-border bg-card">
        <button
          onClick={toggleCandidates}
          className="flex w-full items-center justify-between px-4 py-3 text-left"
        >
          <span className="flex flex-wrap items-center gap-2 text-base font-medium text-foreground">
            <Lightbulb className="h-4 w-4 text-accent-info" />
            題材探勘
            <span className="text-xs font-normal text-muted-foreground">
              播客中反覆出現、但尚未收錄為題材的新興概念
            </span>
          </span>
          {candidatesOpen
            ? <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
            : <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />}
        </button>
        {candidatesOpen && (
          <div className="border-t border-border px-4 py-3">
            {candidatesLoading ? (
              <p className="py-4 text-center text-sm text-muted-foreground">掃描集數中…</p>
            ) : candidates.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">目前沒有達到門檻的新題材候選。</p>
            ) : (
              <>
                <p className="mb-3 text-xs text-muted-foreground">
                  要收錄候選題材，請在 <code className="rounded bg-muted px-1">curated_themes.json</code> 新增條目後重新編譯 — 此處僅供探勘。
                </p>
                <ul className="divide-y divide-border">
                  {candidates.map((c) => {
                    const open = expandedTerm === c.normalized_text;
                    return (
                      <li key={c.normalized_text} className="py-2">
                        <button
                          onClick={() => setExpandedTerm(open ? null : c.normalized_text)}
                          className="flex w-full items-center justify-between text-left"
                        >
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-base text-foreground">{c.mention_text}</span>
                            <span className="rounded-full bg-accent-info-soft px-2 py-0.5 text-xs font-medium text-accent-info">
                              {c.count} 集
                            </span>
                          </span>
                          {c.examples.length > 0 && (
                            open
                              ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                              : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          )}
                        </button>
                        {open && c.examples.length > 0 && (
                          <ul className="mt-2 space-y-1.5 pl-1">
                            {c.examples.map((ex, i) => (
                              <li key={i} className="text-xs text-muted-foreground">
                                <span className="font-medium text-foreground/80">{ex.episode_title || '（無標題）'}</span>
                                {ex.context && <span className="ml-1.5 opacity-80">— {ex.context}</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </div>
        )}
      </div>

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
              <th className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={toggleEpisodeSort}
                  className="ml-auto inline-flex items-center gap-1 hover:text-foreground"
                  title="Sort by episode count"
                >
                  Episodes
                  {episodeSort === 'desc' && <ChevronDown className="h-3 w-3" />}
                  {episodeSort === 'asc' && <ChevronUp className="h-3 w-3" />}
                </button>
              </th>
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
              displayTags.map((tag) => {
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
                    {editKey === `${tag.kind}:${tag.slug}` ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveDisplay(tag);
                            if (e.key === 'Escape') setEditKey(null);
                          }}
                          className="w-full rounded border border-input bg-card px-2 py-1 text-base text-foreground"
                          autoFocus
                        />
                        <button onClick={() => handleSaveDisplay(tag)} className="rounded p-1 text-sentiment-bull hover:bg-sentiment-bull-soft" title="Save">
                          <Check className="h-4 w-4" />
                        </button>
                        <button onClick={() => setEditKey(null)} className="rounded p-1 text-muted-foreground hover:bg-muted" title="Cancel">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : isSector ? (
                      // Sector labels come from the pipeline universe — a re-sync overwrites them, so don't edit here.
                      tag.display_zh
                    ) : (
                      <button
                        onClick={() => { setEditKey(`${tag.kind}:${tag.slug}`); setEditValue(tag.display_zh); }}
                        className="group inline-flex items-center gap-1.5 text-left hover:text-foreground"
                        title="Click to edit display name"
                      >
                        {tag.display_zh}
                        <Pencil className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-60" />
                      </button>
                    )}
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
