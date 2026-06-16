import { useEffect, useMemo, useState } from 'react';
import { Target } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { FilterPills, Segmented } from '@/components/redesign';
import { PickCard } from '@/components/financial/PickCard';
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

  const pickRefs = useMemo(
    () =>
      picks
        .map((p) => ({ ticker: p.ticker, reference_ms: Date.parse(p.podcast_launch_time) }))
        .filter((r) => r.ticker && Number.isFinite(r.reference_ms)),
    [picks],
  );
  const windowsMap = useTickerWindowReturns(pickRefs);

  const tickers = useMemo(() => picks.map((p) => p.ticker), [picks]);
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

  const podcasterNames = useMemo(() => podcasters.map((p) => p.name), [podcasters]);
  const hitRatePct = scorecard?.hit_rate != null ? Math.round(scorecard.hit_rate * 100) : null;

  return (
    <>
      <SEO title="走勢 · 播客選股命中率" description="追蹤財經 Podcaster 點名的個股，從提及日起算 7/30/90 天的真實走勢與命中率。" />
      <PageContent>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-1.5">走勢</h1>
        <p className="text-[13px] text-muted-foreground mb-4">
          財經 Podcaster 點名的個股，從提及當日起算的真實漲跌幅與命中率。
        </p>

        {podcasterNames.length > 0 && (
          <FilterPills items={podcasterNames} value={selected} onChange={setSelected} />
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {picks.map((pick) => {
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
        )}
      </PageContent>
    </>
  );
};

export default PicksPage;
