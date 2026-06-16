import { useEffect, useMemo, useRef, useState } from 'react';
import { Target, ChevronDown, Search } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign';
import { PickCard } from '@/components/financial/PickCard';
import { cn } from '@/lib/utils';
import {
  getSortedPodcasts,
  getInsightsByPodcaster,
  getPodcasterScorecard,
  getPodcastByName,
  getPodcastEpisodes,
  getEpisodeAudioUrl,
  type Episode,
  type Podcast,
} from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useTickerWindowReturns, windowReturnsKey } from '@/hooks/useTickerWindowReturns';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { PodcasterScorecard, TickerInsight } from '@/services/types';

type WindowKey = '7' | '30' | '90';
const WINDOW_OPTIONS = [
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
] as const;

const DAY_MS = 86_400_000;
const isoDate = (ms: number) => new Date(ms).toISOString().slice(0, 10);
// Cap the rendered feed — an active channel can have 1000+ picks over 180d.
// The 命中率 stat is still computed server-side over the full set.
const MAX_CARDS = 40;

/** Searchable channel filter — a compact dropdown that scales to any number of
 *  channels, instead of a fixed wall of pills. */
const ChannelSelect: React.FC<{
  channels: Podcast[];
  value: string;
  onChange: (name: string) => void;
}> = ({ channels, value, onChange }) => {
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

  const selected = channels.find((c) => c.name === value);
  const q = query.trim().toLowerCase();
  const filtered = q ? channels.filter((c) => c.name.toLowerCase().includes(q)) : channels;

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 h-9 pl-2.5 pr-3 rounded-full bg-muted/60 border border-border text-[13px] font-medium hover:bg-muted transition-colors min-w-[180px]"
      >
        {selected?.image_url ? (
          <img src={selected.image_url} alt="" className="w-5 h-5 rounded-full object-cover shrink-0" />
        ) : (
          <span className="w-5 h-5 rounded-full bg-border shrink-0" />
        )}
        <span className="flex-1 text-left truncate">{value || '選擇頻道'}</span>
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
          </div>
          <ul className="max-h-[320px] overflow-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2.5 text-[13px] text-muted-foreground">找不到頻道</li>
            ) : (
              filtered.map((c) => (
                <li key={c.name}>
                  <button
                    type="button"
                    onClick={() => { onChange(c.name); setOpen(false); setQuery(''); }}
                    className={cn(
                      'w-full flex items-center gap-2.5 px-3 py-2 text-left text-[13px] hover:bg-muted transition-colors',
                      c.name === value && 'bg-muted font-medium',
                    )}
                  >
                    {c.image_url ? (
                      <img src={c.image_url} alt="" className="w-6 h-6 rounded-full object-cover shrink-0" />
                    ) : (
                      <span className="w-6 h-6 rounded-full bg-border shrink-0" />
                    )}
                    <span className="flex-1 truncate">{c.name}</span>
                    {typeof c.episode_count === 'number' && c.episode_count > 0 && (
                      <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">{c.episode_count}</span>
                    )}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

export const PicksPage: React.FC = () => {
  const [podcasters, setPodcasters] = useState<Podcast[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [picks, setPicks] = useState<TickerInsight[]>([]);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [meta, setMeta] = useState<Podcast | null>(null);
  const [scorecard, setScorecard] = useState<PodcasterScorecard | null>(null);
  const [windowDays, setWindowDays] = useState<WindowKey>('30');
  const [loading, setLoading] = useState(true);

  const playEpisode = usePlayerStore((s) => s.playEpisode);

  // Load the podcaster list once; default to the most recently updated channel.
  useEffect(() => {
    let alive = true;
    fetchWithFallback<Podcast[]>(
      () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 30 }),
      [],
      'getSortedPodcasts:picks',
    )
      .then((list) => {
        if (!alive) return;
        const arr = Array.isArray(list) ? list : [];
        setPodcasters(arr);
        setSelected((cur) => cur || (arr[0]?.name ?? ''));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // Load this channel's picks + episodes + cover. A wide (180d) window so older
  // picks — the only ones with completed 30/90D returns — are included (the picks
  // feed deliberately bypasses the homepage recency filter).
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setLoading(true);
    const end = isoDate(Date.now());
    const start = isoDate(Date.now() - 180 * DAY_MS);
    Promise.all([
      getInsightsByPodcaster(selected, { start_date: start, end_date: end }).catch(() => [] as TickerInsight[]),
      getPodcastEpisodes(selected, { limit: 50, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }).catch(() => [] as Episode[]),
      getPodcastByName(selected).catch(() => null),
    ]).then(([ins, eps, m]) => {
      if (!alive) return;
      setPicks(Array.isArray(ins) ? ins : []);
      setEpisodes(Array.isArray(eps) ? eps : []);
      setMeta(m);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [selected]);

  // 命中率 stat — refetched when the channel or scoring window changes.
  useEffect(() => {
    if (!selected) { setScorecard(null); return; }
    let alive = true;
    getPodcasterScorecard(selected, Number(windowDays) as 7 | 30 | 90)
      .then((sc) => { if (alive) setScorecard(sc); })
      .catch(() => {});
    return () => { alive = false; };
  }, [selected, windowDays]);

  // picks arrive sorted newest-first; show the most recent MAX_CARDS.
  const visiblePicks = useMemo(() => picks.slice(0, MAX_CARDS), [picks]);

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

  const episodeMap = useMemo(() => {
    const m = new Map<string, Episode>();
    for (const e of episodes) m.set(e.id, e);
    return m;
  }, [episodes]);

  const onPlaySegment = (episodeId: string, startTimeMs: number) => {
    const ep = episodeMap.get(episodeId);
    const seconds = Math.floor(startTimeMs / 1000);
    if (!ep) {
      window.open(`https://open.spotify.com/search/${encodeURIComponent(episodeId)}`, '_blank');
      return;
    }
    const spotifyUri = ep.spotify_id ? `spotify:episode:${ep.spotify_id}` : undefined;
    const mp3Url = ep.podcast_name && (ep.mp3_url || ep.mp3_public_url)
      ? getEpisodeAudioUrl(ep.podcast_name, ep.id)
      : undefined;
    playEpisode(
      {
        id: ep.id,
        title: ep.episode_title || ep.id,
        showName: selected,
        coverUrl: ep.spotify_images?.[0] || meta?.image_url || undefined,
        spotifyUri,
        mp3Url,
      },
      spotifyUri || mp3Url ? { seekTo: seconds } : undefined,
    );
  };

  const hitRatePct = scorecard?.hit_rate != null ? Math.round(scorecard.hit_rate * 100) : null;

  return (
    <>
      <SEO title="走勢 · 播客選股命中率" description="追蹤財經 Podcaster 點名的個股，從提及日起算 7/30/90 天的真實走勢與命中率。" />
      <PageContent>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-1.5">走勢</h1>
        <p className="text-[13px] text-muted-foreground mb-4">
          財經 Podcaster 點名的個股，從提及當日起算的真實漲跌幅與命中率。
        </p>

        {podcasters.length > 0 && (
          <div className="mb-[18px]">
            <ChannelSelect channels={podcasters} value={selected} onChange={setSelected} />
          </div>
        )}

        {/* 命中率 header */}
        <div className="bg-card border border-border rounded-md p-4 mb-[18px] flex items-center gap-4 flex-wrap">
          <Target className="text-accent-info shrink-0" size={22} />
          <div className="flex-1 min-w-0">
            <div className="text-[13px] text-muted-foreground">{selected || '—'} 的命中率</div>
            {hitRatePct != null ? (
              <div className="flex items-baseline gap-2">
                <span className="text-[26px] font-semibold tabular-nums">{hitRatePct}%</span>
                <span className="text-[12px] text-muted-foreground">
                  {scorecard?.n_hit}/{scorecard?.n_scored} 檔命中
                  {scorecard?.avg_return != null && ` · 平均報酬 ${scorecard.avg_return > 0 ? '+' : ''}${scorecard.avg_return}%`}
                </span>
              </div>
            ) : (
              <div className="text-[14px] text-muted-foreground mt-0.5">此區間尚無足夠完成的走勢可計算</div>
            )}
          </div>
          <Segmented
            options={WINDOW_OPTIONS}
            value={windowDays}
            onChange={(v) => setWindowDays(v as WindowKey)}
          />
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : picks.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
            此頻道近半年沒有可顯示的標的分析。
          </div>
        ) : (
          <>
            {picks.length > MAX_CARDS && (
              <p className="text-[12px] text-muted-foreground mb-2.5">
                顯示最近 {MAX_CARDS} 筆，共 {picks.length} 筆標的分析
              </p>
            )}
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
                  podcastImage={meta?.image_url || undefined}
                  episodeTitle={episodeMap.get(pick.episode_id)?.episode_title || undefined}
                  shareUrl={`${window.location.origin}/episode/${encodeURIComponent(pick.episode_id)}`}
                  onPlaySegment={onPlaySegment}
                />
              );
            })}
          </div>
          </>
        )}
      </PageContent>
    </>
  );
};

export default PicksPage;
