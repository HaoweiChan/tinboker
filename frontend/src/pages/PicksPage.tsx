import { useEffect, useMemo, useRef, useState } from 'react';
import { Filter, ChevronDown, Search, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { PickCard } from '@/components/financial/PickCard';
import {
  getRecentInsights,
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
import type { TickerInsight } from '@/services/types';

interface ChannelOption {
  name: string;
  image_url?: string | null;
}

export const PicksPage: React.FC = () => {
  const [podcasters, setPodcasters] = useState<Podcast[]>([]);
  const [picks, setPicks] = useState<TickerInsight[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

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

  const podcastImageMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of podcasters) if (p.name && p.image_url) m.set(p.name, p.image_url);
    return m;
  }, [podcasters]);

  // Filter options = channels that actually appear in the feed, so a selection
  // always yields results (and the list stays short).
  const channelOptions = useMemo<ChannelOption[]>(() => {
    const seen = new Map<string, ChannelOption>();
    for (const p of picks) {
      const name = p.podcaster || '';
      if (name && !seen.has(name)) seen.set(name, { name, image_url: podcastImageMap.get(name) });
    }
    return Array.from(seen.values());
  }, [picks, podcastImageMap]);

  const visiblePicks = useMemo(
    () => (selected.size === 0 ? picks : picks.filter((p) => selected.has(p.podcaster || ''))),
    [picks, selected],
  );

  const pickRefs = useMemo(
    () =>
      visiblePicks
        .map((p) => ({ ticker: p.ticker, reference_ms: Date.parse(p.podcast_launch_time) }))
        .filter((r) => r.ticker && Number.isFinite(r.reference_ms)),
    [visiblePicks],
  );
  const windowsMap = useTickerWindowReturns(pickRefs);

  const tickers = useMemo(() => visiblePicks.map((p) => p.ticker), [visiblePicks]);
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
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-1.5">走勢</h1>
        <p className="text-[13px] text-muted-foreground mb-4">
          財經 Podcaster 點名的個股，依時間排序，從提及當日起算的 7／30／90 天真實漲跌幅。
        </p>

        {channelOptions.length > 0 && (
          <div className="mb-[18px]">
            <ChannelFilter
              channels={channelOptions}
              selected={selected}
              onToggle={toggleChannel}
              onClear={() => setSelected(new Set())}
            />
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : visiblePicks.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
            {picks.length === 0 ? '目前沒有可顯示的標的分析。' : '所選頻道近期沒有標的分析，試試其他頻道。'}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {visiblePicks.map((pick) => {
              const refMs = Date.parse(pick.podcast_launch_time);
              const windows = Number.isFinite(refMs)
                ? windowsMap.get(windowReturnsKey(pick.ticker, refMs))
                : undefined;
              return (
                <PickCard
                  key={`${pick.episode_id}-${pick.ticker}`}
                  pick={pick}
                  windows={windows}
                  displayName={nameMap.get(pick.ticker.toUpperCase())}
                  podcastImage={podcastImageMap.get(pick.podcaster || '') || undefined}
                  shareUrl={`${window.location.origin}/episode/${encodeURIComponent(pick.episode_id)}`}
                  onPlaySegment={onPlaySegment}
                />
              );
            })}
          </div>
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
        className="flex items-center gap-2 h-9 pl-3 pr-3 rounded-full bg-muted/60 border border-border text-[13px] font-medium hover:bg-muted transition-colors"
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
              className="w-full h-9 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
            {selected.size > 0 && (
              <button type="button" onClick={onClear} className="text-[12px] text-accent-info hover:underline shrink-0">
                清除
              </button>
            )}
          </div>
          <ul className="max-h-[320px] overflow-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2.5 text-[13px] text-muted-foreground">找不到頻道</li>
            ) : (
              filtered.map((c) => {
                const checked = selected.has(c.name);
                return (
                  <li key={c.name}>
                    <button
                      type="button"
                      onClick={() => onToggle(c.name)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-[13px] hover:bg-muted transition-colors"
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
