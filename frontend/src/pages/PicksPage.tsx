import { useEffect, useMemo, useRef, useState } from 'react';
import { Filter, ChevronDown, Search, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign';
import { PickCard } from '@/components/financial/PickCard';
import {
  getRecentInsights,
  getInsightsByPodcaster,
  getSortedPodcasts,
  getEpisodeByIdOnly,
  getEpisodeAudioUrl,
  type Podcast,
} from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useTickerWindowReturns, windowReturnsKey } from '@/hooks/useTickerWindowReturns';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { usePlayerStore } from '@/store/usePlayerStore';
import { cn } from '@/lib/utils';
import { groupPicks } from '@/lib/pickGroups';
import type { TickerInsight } from '@/services/types';

interface ChannelOption {
  name: string;
  image_url?: string | null;
}

// Keep non-tradeable LLM artifacts out of the feed: indices, private companies,
// and multi-word labels (VIX, SPX, OPENAI, "台積電 (TSMC)", "US HY BOND ETF", …)
// have no price and only render as permanent "—". A pipeline-validator fix is the
// real cleanup at the source; this is the interim feed-side guard.
const NON_TRADEABLE = new Set([
  'VIX', 'SPX', 'DJI', 'IXIC', 'RUT', 'NBI', 'MSCI', 'SOX', 'NDX', 'INX', 'GSPC',
  'OPENAI', 'SPACE', 'ANTHROPIC',
]);
function isLikelyTradeable(ticker: string): boolean {
  const s = (ticker || '').trim();
  if (!s) return false;
  if (/[\s()]/.test(s)) return false; // "name (TICKER)" / multi-word labels
  return !NON_TRADEABLE.has(s.toUpperCase());
}

const PAGE_SIZE = 40; // infinite-scroll page size
const DAY_MS = 86_400_000;
// When a settled tier is active we sort the whole filtered set by that window's
// return, so we must fetch windows beyond the visible slice — capped to keep the
// chunked batch bounded.
const WINDOW_FETCH_CAP = 120;

/** Settled maturity tiers (days). 已揭曉 defaults to 7D for immediate density. */
type SettledTier = 7 | 30 | 90;
const TIER_WINDOW: Record<SettledTier, 'd7' | 'd30' | 'd90'> = { 7: 'd7', 30: 'd30', 90: 'd90' };

/** Whole days elapsed since a mention date (ISO string). */
function ageDays(launch?: string): number {
  const ms = Date.parse(launch || '');
  return Number.isFinite(ms) ? Math.floor((Date.now() - ms) / DAY_MS) : 0;
}

export const PicksPage: React.FC = () => {
  const [podcasters, setPodcasters] = useState<Podcast[]>([]);
  const [picks, setPicks] = useState<TickerInsight[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  // When channels are filtered, fetch each channel's FULL history (not just the
  // recent-100 blended feed) so older, settled picks surface. Keyed off `selected`.
  const [channelHistory, setChannelHistory] = useState<TickerInsight[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  // Feed controls: 最新 (all, newest) vs 已揭曉 (picks old enough for a window to
  // have settled). 已揭曉 has a 7/30/90-day sub-tier — default 7D for density,
  // and sorting flips to "highest return over that window".
  const [view, setView] = useState<'recent' | 'settled'>('recent');
  const [settledTier, setSettledTier] = useState<SettledTier>(7);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const playEpisode = usePlayerStore((s) => s.playEpisode);

  // Blended, reverse-chronological feed across all podcasters (backend-limited),
  // plus the podcaster list for avatars + the filter.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      getRecentInsights(100).catch(() => [] as TickerInsight[]),
      fetchWithFallback<Podcast[]>(
        () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 50 }),
        [],
        'getSortedPodcasts:picks',
      ).catch(() => [] as Podcast[]),
    ]).then(([recent, pods]) => {
      if (!alive) return;
      setPicks(Array.isArray(recent) ? recent : []);
      setPodcasters(Array.isArray(pods) ? pods : []);
      setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  // Filtered view: pull each selected channel's history over the last year,
  // newest-first, so settled (older) picks appear — the blended /recent only
  // covers the most recent ~100 across all channels.
  useEffect(() => {
    const names = [...selected];
    if (names.length === 0) { setChannelHistory([]); return; }
    let alive = true;
    setHistoryLoading(true);
    const end = new Date().toISOString().slice(0, 10);
    const start = new Date(Date.now() - 365 * 86_400_000).toISOString().slice(0, 10);
    Promise.all(
      names.map((n) => getInsightsByPodcaster(n, { start_date: start, end_date: end }).catch(() => [] as TickerInsight[])),
    ).then((arrs) => {
      if (!alive) return;
      const merged = arrs
        .flat()
        .sort((a, b) => (b.podcast_launch_time || '').localeCompare(a.podcast_launch_time || ''));
      setChannelHistory(merged);
      setHistoryLoading(false);
    });
    return () => { alive = false; };
  }, [selected]);

  const podcastImageMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of podcasters) if (p.name && p.image_url) m.set(p.name, p.image_url);
    return m;
  }, [podcasters]);

  // Filter options = channels that actually appear in the feed, so a selection
  // always yields results (and the list stays short).
  // Channel filter options come from the blended feed (always present, stable).
  const optionPicks = useMemo(() => picks.filter((p) => isLikelyTradeable(p.ticker)), [picks]);
  const channelOptions = useMemo<ChannelOption[]>(() => {
    const seen = new Map<string, ChannelOption>();
    for (const p of optionPicks) {
      const name = p.podcaster || '';
      if (name && !seen.has(name)) seen.set(name, { name, image_url: podcastImageMap.get(name) });
    }
    return Array.from(seen.values());
  }, [optionPicks, podcastImageMap]);

  // Collapse the stream into master cards: blended recent when no filter; the
  // selected channels' full history when filtered. Repeated calls of the same
  // canonical ticker by one podcaster within 14 days fold into one card.
  const groups = useMemo(() => {
    const src = selected.size === 0 ? picks : channelHistory;
    return groupPicks(src.filter((p) => isLikelyTradeable(p.ticker)));
  }, [picks, channelHistory, selected]);

  // 已揭曉 keeps only cards whose master mention is old enough for the active tier
  // to have settled, so the chosen window's return is always populated.
  const filteredGroups = useMemo(() => {
    if (view !== 'settled') return groups;
    return groups.filter((g) => ageDays(g.master.podcast_launch_time) >= settledTier);
  }, [groups, view, settledTier]);

  // Window returns: in 最新 we only need the visible slice; in 已揭曉 we sort the
  // whole filtered set by the tier's return, so fetch up to the cap.
  const refGroups = useMemo(
    () => filteredGroups.slice(0, view === 'settled' ? WINDOW_FETCH_CAP : visibleCount),
    [filteredGroups, view, visibleCount],
  );
  const pickRefs = useMemo(
    () =>
      refGroups
        .map((g) => ({ ticker: g.canonicalTicker, reference_ms: Date.parse(g.master.podcast_launch_time) }))
        .filter((r) => r.ticker && Number.isFinite(r.reference_ms)),
    [refGroups],
  );
  const windowsMap = useTickerWindowReturns(pickRefs);

  // Dynamic sort: 已揭曉 orders by the active window's return (desc, unsettled
  // last); 最新 keeps the newest-master order from groupPicks.
  const sortedGroups = useMemo(() => {
    if (view !== 'settled') return filteredGroups;
    const wk = TIER_WINDOW[settledTier];
    const ret = (g: (typeof filteredGroups)[number]) => {
      const refMs = Date.parse(g.master.podcast_launch_time);
      const v = Number.isFinite(refMs) ? windowsMap.get(windowReturnsKey(g.canonicalTicker, refMs))?.[wk] : null;
      return v == null ? Number.NEGATIVE_INFINITY : v;
    };
    return [...filteredGroups].sort((a, b) => {
      const ra = ret(a);
      const rb = ret(b);
      // Higher return first; groups with a settled return outrank unsettled ones
      // (−Infinity). Equal (incl. both unsettled) falls back to newest-master.
      if (ra !== rb) return rb - ra;
      return Date.parse(b.master.podcast_launch_time) - Date.parse(a.master.podcast_launch_time);
    });
  }, [filteredGroups, view, settledTier, windowsMap]);

  // Infinite-scroll: render visibleCount, grow as the sentinel scrolls into view.
  const visibleGroups = useMemo(() => sortedGroups.slice(0, visibleCount), [sortedGroups, visibleCount]);

  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [selected, view, settledTier, picks, channelHistory]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleCount((c) => (c < sortedGroups.length ? c + PAGE_SIZE : c));
        }
      },
      { rootMargin: '600px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [sortedGroups.length]);

  const tickers = useMemo(() => visibleGroups.map((g) => g.canonicalTicker), [visibleGroups]);
  const rawTranslationMap = useTranslationMap(tickers);
  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k.toUpperCase(), v.displayName);
    return m;
  }, [rawTranslationMap]);

  // Lazy: the blended feed spans podcasters, so resolve the episode on play
  // rather than pre-fetching every channel's episodes.
  const onPlaySegment = async (episodeId: string, startTimeMs: number) => {
    const seconds = Math.floor(startTimeMs / 1000);
    try {
      const ep = await getEpisodeByIdOnly(episodeId);
      if (!ep) throw new Error('episode not found');
      const spotifyUri = ep.spotify_id ? `spotify:episode:${ep.spotify_id}` : undefined;
      const mp3Url = ep.podcast_name && (ep.mp3_url || ep.mp3_public_url)
        ? getEpisodeAudioUrl(ep.podcast_name, ep.id)
        : undefined;
      playEpisode(
        {
          id: ep.id,
          title: ep.episode_title || ep.id,
          showName: ep.podcast_name || '',
          coverUrl: ep.spotify_images?.[0] || podcastImageMap.get(ep.podcast_name || '') || undefined,
          spotifyUri,
          mp3Url,
        },
        spotifyUri || mp3Url ? { seekTo: seconds } : undefined,
      );
    } catch {
      window.open(`https://open.spotify.com/search/${encodeURIComponent(episodeId)}`, '_blank');
    }
  };

  const toggleChannel = (name: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });

  return (
    <>
      <SEO title="走勢 · 播客選股追蹤" description="財經 Podcaster 點名的個股，從提及當日起算的 7／30／90 天真實走勢。" />
      <PageContent>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] mb-1.5">走勢</h1>
        <p className="text-sm text-muted-foreground mb-4">
          財經 Podcaster 點名的個股，依時間排序，從提及當日起算的 7／30／90 天真實漲跌幅。
        </p>

        <div className="flex items-center gap-3 mb-[18px] flex-wrap">
          {channelOptions.length > 0 && (
            <ChannelFilter
              channels={channelOptions}
              selected={selected}
              onToggle={toggleChannel}
              onClear={() => setSelected(new Set())}
            />
          )}
          <Segmented
            options={[
              { value: 'recent', label: '最新' },
              { value: 'settled', label: '已揭曉' },
            ] as const}
            value={view}
            onChange={(v) => setView(v as 'recent' | 'settled')}
          />
          {view === 'settled' && (
            <Segmented
              options={[
                { value: '7', label: '7日已揭曉' },
                { value: '30', label: '30日已揭曉' },
                { value: '90', label: '90日已揭曉' },
              ] as const}
              value={String(settledTier)}
              onChange={(v) => setSettledTier(Number(v) as SettledTier)}
            />
          )}
        </div>

        {loading || historyLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : visibleGroups.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
            {picks.length === 0
              ? '目前沒有可顯示的標的分析。'
              : view === 'settled'
                ? `所選頻道近期沒有滿 ${settledTier} 天的已揭曉標的，試試較短的天期或其他頻道。`
                : '所選頻道近期沒有標的分析，試試其他頻道。'}
          </div>
        ) : (
          <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {visibleGroups.map((g) => {
              const pick = g.master;
              const refMs = Date.parse(pick.podcast_launch_time);
              const windows = Number.isFinite(refMs)
                ? windowsMap.get(windowReturnsKey(g.canonicalTicker, refMs))
                : undefined;
              return (
                <PickCard
                  key={g.key}
                  pick={pick}
                  windows={windows}
                  displayName={nameMap.get(g.canonicalTicker.toUpperCase())}
                  displayTicker={g.canonicalTicker}
                  podcastImage={podcastImageMap.get(pick.podcaster || '') || undefined}
                  episodeTitle={pick.episode_title}
                  mentions={g.occurrences}
                  shareUrl={`${window.location.origin}/episode/${encodeURIComponent(pick.episode_id)}`}
                  onPlaySegment={onPlaySegment}
                />
              );
            })}
          </div>
          <div ref={sentinelRef} className="h-10 flex items-center justify-center text-xs text-muted-foreground/70 mt-2">
            {visibleGroups.length < sortedGroups.length ? '載入更多…' : `共 ${sortedGroups.length} 筆`}
          </div>
          </>
        )}
      </PageContent>
    </>
  );
};

/** Multi-select channel filter — checkboxes in a searchable dropdown. No selection = all. */
const ChannelFilter: React.FC<{
  channels: ChannelOption[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  onClear: () => void;
}> = ({ channels, selected, onToggle, onClear }) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const q = query.trim().toLowerCase();
  const filtered = q ? channels.filter((c) => c.name.toLowerCase().includes(q)) : channels;
  const label = selected.size === 0 ? '全部頻道' : `已選 ${selected.size} 個頻道`;

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 h-9 pl-3 pr-3 rounded-full bg-muted/60 border border-border text-sm font-medium hover:bg-muted transition-colors"
      >
        <Filter size={14} className="text-muted-foreground" />
        <span>{label}</span>
        <ChevronDown size={15} className={cn('text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute z-30 mt-1.5 w-[280px] bg-card border border-border rounded-lg shadow-lg overflow-hidden">
          <div className="flex items-center gap-2 px-3 border-b border-border">
            <Search size={14} className="text-muted-foreground shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜尋頻道…"
              className="w-full h-9 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            {selected.size > 0 && (
              <button type="button" onClick={onClear} className="text-xs text-accent-info hover:underline shrink-0">
                清除
              </button>
            )}
          </div>
          <ul className="max-h-[320px] overflow-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2.5 text-sm text-muted-foreground">找不到頻道</li>
            ) : (
              filtered.map((c) => {
                const checked = selected.has(c.name);
                return (
                  <li key={c.name}>
                    <button
                      type="button"
                      onClick={() => onToggle(c.name)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-muted transition-colors"
                    >
                      <span
                        className={cn(
                          'w-4 h-4 rounded border flex items-center justify-center shrink-0',
                          checked ? 'bg-accent-info border-accent-info text-white' : 'border-border',
                        )}
                      >
                        {checked && <Check size={12} />}
                      </span>
                      {c.image_url ? (
                        <img src={c.image_url} alt="" className="w-6 h-6 rounded-full object-cover shrink-0" />
                      ) : (
                        <span className="w-6 h-6 rounded-full bg-border shrink-0" />
                      )}
                      <span className="flex-1 truncate">{c.name}</span>
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

export default PicksPage;
