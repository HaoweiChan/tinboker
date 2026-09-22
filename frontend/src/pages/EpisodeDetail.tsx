import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, Play, ExternalLink, Bookmark, Share2, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PodcastAvatar } from '@/components/common/PodcastAvatar';
import { PageContent } from '@/components/layout/PageContent';
import { TickerRow } from '@/components/redesign';
import { cn } from '@/lib/utils';
import { getEpisodeById, getEpisodeByIdOnly, getPodcastByName, type Episode as ApiEpisode } from '@/services';
import { getSectorBoard, type SectorBoardItem } from '@/services/api/podcasts';
import { SectorExposureList } from '@/components/episode/SectorExposureList';
import { fetchWithFallback } from '@/services/api/migration';
import { parseSummaryTopicSections, parseTimestampedSections, skippableSectionsFromSegments, type TimestampedSection } from '@/utils/parseTimestampedSections';
import { usePlayerStore } from '@/store/usePlayerStore';
import { useAppStore, useEpisodeBookmarks } from '@/store/useAppStore';
import { CommentSection } from '@/components/episode/CommentSection';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap, isRecentEpisode } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useTagLabels, useHiddenTagSlugs, tagLabelFor, normalizeTagSlug } from '@/hooks/useTagLabels';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { EpisodeInsightCard } from '@/components/episode/EpisodeInsightCard';
import { episodeLeadFrom } from '@/lib/episodeLead';
import { SummaryMarkdown } from '@/components/episode/SummaryMarkdown';
import { EpisodeDebugPanel } from '@/components/episode/EpisodeDebugPanel';
import { SlideViewer } from '@/components/common/SlideViewer';
import type { Sentiment } from '@/lib/sentiment';

const IS_DEV = import.meta.env.DEV || (import.meta.env.VITE_STAGE as string) === 'DEV';

// Episodes can carry dozens of tags; show only a handful so the row stays meaningful.
const MAX_HERO_TAGS = 6;
// Chips shown before the +n disclosure.
const HERO_CHIPS_COLLAPSED = 4;

function timeAgo(release: string | number | null | undefined, created: number): string {
  const ms = typeof release === 'string' ? Date.parse(release) : (release ?? created);
  const t = Number.isFinite(ms) ? (ms as number) : created;
  const hours = Math.floor((Date.now() - t) / 3_600_000);
  if (hours < 1) return '剛剛';
  if (hours < 24) return `${hours} 小時前`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '昨天';
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} 個月前` : `${Math.floor(months / 12)} 年前`;
}

function spotifyUriFrom(ep: ApiEpisode | null): string | undefined {
  if (!ep) return undefined;
  if (ep.spotify_id) return `spotify:episode:${ep.spotify_id}`;
  if (ep.spotify_url) {
    const m = ep.spotify_url.match(/episode\/([a-zA-Z0-9]+)/);
    if (m?.[1]) return `spotify:episode:${m[1]}`;
    if (ep.spotify_url.startsWith('spotify:episode:')) return ep.spotify_url;
  }
  return undefined;
}

function tickerLookupKeys(symbol: string): string[] {
  const upper = symbol.toUpperCase();
  const bare = upper.replace(/\.[A-Z]+$/i, '');
  return [...new Set([upper, bare, `${bare}.TW`, `${bare}.KS`])];
}

function firstMapValue<T>(map: Map<string, T>, keys: string[]): T | undefined {
  for (const key of keys) {
    const value = map.get(key);
    if (value !== undefined) return value;
  }
  return undefined;
}

export const EpisodeDetail: React.FC = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const podcastName = searchParams.get('podcast') || '';
  const { playEpisode, requestSeek } = usePlayerStore();
  const { toggleEpisodeBookmark } = useAppStore();
  const { guard } = useRequireAuth();
  const episodeBookmarks = useEpisodeBookmarks();
  const tagLabels = useTagLabels();
  const hiddenTagSlugs = useHiddenTagSlugs();

  const [episode, setEpisode] = useState<ApiEpisode | null>(null);
  const [tagsExpanded, setTagsExpanded] = useState(false);
  const [podcastImageUrl, setPodcastImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Per-sector performance + visuals for the 產業/主題曝險 rail, keyed by exposure_id.
  // Sourced from the (cached) hot-sectors board so each exposure shows its aggregate
  // change without a bespoke price fetch.
  const [sectorPerf, setSectorPerf] = useState<Map<string, SectorBoardItem>>(new Map());
  const [sectorPerfLoading, setSectorPerfLoading] = useState(false);
  // Post-mention performance (TKB-001) deliberately does NOT render here: the rail is
  // for what the episode talks about, and per-ticker return chips made it noisy. The
  // stock page keeps its 播客提及後續表現 section.

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setLoading(true);
    setPodcastImageUrl(null);
    (async () => {
      // On a cold load (deep link / refresh / shared URL) there is no ?podcast= to
      // supply the show name, so fall back to the by-id endpoint, then resolve the
      // show name from the response for the podcast-image fetch.
      const fetchEpisode = () =>
        fetchWithFallback<ApiEpisode | null>(
          () => (podcastName ? getEpisodeById(podcastName, id) : getEpisodeByIdOnly(id)),
          null,
          `getEpisodeById:${podcastName || '-'}/${id}`,
        ).catch(() => null);

      // A half-hydrated cold response arrives with a summary source URL but empty
      // content (the server-side GCS fetch hiccuped and the backend returns it
      // no-cache). Retry once — the next read almost always returns the full summary —
      // so the page never gets stuck showing key insights without the summary body.
      const summaryMissing = (e: ApiEpisode | null) =>
        !!e && !e.summary_content && !e.modified_summary_content && !!(e.summary_url || e.summary_public_url);

      let ep = await fetchEpisode();
      if (alive && summaryMissing(ep)) {
        await new Promise((r) => setTimeout(r, 1200));
        if (!alive) return;
        const retry = await fetchEpisode();
        if (retry && (retry.summary_content || retry.modified_summary_content)) ep = retry;
      }
      if (!alive) return;
      setEpisode(ep);
      const resolvedName = ep?.podcast_name || podcastName;
      const podcast = resolvedName
        ? await fetchWithFallback(() => getPodcastByName(resolvedName), null, `getPodcastByName:${resolvedName}`).catch(() => null)
        : null;
      if (!alive) return;
      setPodcastImageUrl(podcast?.image_url || null);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [id, podcastName]);

  // Load the hot-sectors board once an episode with exposures is in hand, then index
  // it by exposure_id so the rail can show each sector's aggregate performance.
  const hasExposures = (episode?.sector_exposures?.length ?? 0) > 0;
  useEffect(() => {
    if (!hasExposures) return;
    let alive = true;
    setSectorPerfLoading(true);
    getSectorBoard()
      .then((items) => {
        if (!alive) return;
        setSectorPerf(new Map(items.map((it) => [it.exposure_id, it])));
      })
      .catch(() => { if (alive) setSectorPerf(new Map()); })
      .finally(() => { if (alive) setSectorPerfLoading(false); });
    return () => { alive = false; };
  }, [hasExposures]);

  const chapters = useMemo<TimestampedSection[]>(() => (episode?.events_markdown_content ? parseTimestampedSections(episode.events_markdown_content) : []), [episode]);
  const summarySections = useMemo<TimestampedSection[]>(() => {
    const content = episode?.modified_summary_content || episode?.summary_content;
    return content ? parseSummaryTopicSections(content, episode?.sentences_markdown_content) : [];
  }, [episode]);
  // Player chapters: ONLY topic-level timestamps — the summary-extracted sections
  // (same as shown in 摘要), else the events-markdown topics. We deliberately do
  // NOT fall back to raw per-sentence transcript timings: surfacing transcript
  // sentences as "chapters" was the bug where seeking landed on arbitrary speech
  // fragments instead of topic boundaries. An episode with no topic timestamps
  // (e.g. a non-financial episode that produced no clustered topics) shows no
  // chapters rather than transcript noise.
  // Non-financial segments (sponsor, life-story chitchat, …) the pipeline dropped
  // from the summary — surfaced as muted "skip past" chips, interleaved by time.
  const skippableSections = useMemo<TimestampedSection[]>(
    () => skippableSectionsFromSegments(episode?.skipped_segments),
    [episode],
  );
  const playerSections = useMemo<TimestampedSection[]>(
    () => {
      const base = summarySections.length ? summarySections : chapters;
      if (!skippableSections.length) return base;
      return [...base, ...skippableSections].sort((a, b) => a.timestampSeconds - b.timestampSeconds);
    },
    [summarySections, chapters, skippableSections],
  );
  const tickerSymbols = useMemo(() => (Array.isArray(episode?.related_tickers) ? episode!.related_tickers.slice(0, 8) : []), [episode]);
  const priceMap = useStockPriceMap(tickerSymbols);
  const episodesForSince = useMemo(() => (episode ? [episode] : []), [episode]);
  const priceSinceMap = useStockPriceSinceMap(episodesForSince);
  const useSince = episode ? !isRecentEpisode(episode) && priceSinceMap.size > 0 : false;
  const activeMap = useSince ? priceSinceMap : priceMap;
  const sinceLabel = useSince ? '播出至今' : null;
  const rawTranslationMap = useTranslationMap(tickerSymbols);
  const episodeIds = useMemo(() => (episode ? [episode.id] : []), [episode]);
  const episodeSentiments = useEpisodeSentimentMap(episodeIds);
  const tickers = useMemo(() => {
    const sent = episode ? episodeSentiments.get(episode.id) : undefined;
    return tickerSymbols.map((s) => {
      const keys = tickerLookupKeys(s);
      return {
        symbol: s,
        name: firstMapValue(rawTranslationMap, keys)?.displayName,
        sentiment: sent ? firstMapValue<Sentiment>(sent, keys) : undefined,
        changePercent: firstMapValue(activeMap, keys),
        sinceLabel,
      };
    });
  }, [tickerSymbols, rawTranslationMap, episodeSentiments, activeMap, episode, sinceLabel]);
  const spotifyUri = useMemo(() => spotifyUriFrom(episode), [episode]);

  // Hero sector chips: collapse duplicate exposure_ids (an episode tags the same
  // sector once per section), keeping first-seen order.
  const heroSectors = useMemo(
    () => [...new Map((episode?.sector_exposures ?? []).map((e) => [e.exposure_id, e])).values()],
    [episode],
  );

  // Drop admin-hidden off-vocab tags (e.g. a junk "TaiwanStocks") from the hero chips.
  const heroTags = useMemo(
    () => (episode?.tags ?? []).filter((t) => !hiddenTagSlugs.has(normalizeTagSlug(t))),
    [episode, hiddenTagSlugs],
  );

  const title = episode?.episode_title || (episode?.episode_number != null ? `EP ${episode.episode_number}` : '集數摘要');
  const name = episode?.podcast_name || podcastName || '節目';
  const episodeLead = useMemo(
    () => episodeLeadFrom(episode?.modified_summary_content || episode?.summary_content || '', title, episode?.key_insights),
    [episode, title],
  );
  const podcasterImageUrl = podcastImageUrl || episode?.spotify_images?.[0] || null;

  // SEO: a PodcastEpisode JSON-LD with Clip parts (one per timestamped section) so
  // Google can surface chapters, plus a canonical URL + og:image. Sections come from
  // the same timestamped parse the page already uses.
  const canonicalUrl = episode ? `https://tinboker.com/episode/${episode.id}` : undefined;
  const seoImage = episode?.summary_image_public_url || episode?.spotify_images?.[0] || podcasterImageUrl || undefined;
  const structuredData = useMemo<Record<string, unknown> | undefined>(() => {
    if (!episode) return undefined;
    const sections = playerSections;
    const data: Record<string, unknown> = {
      '@context': 'https://schema.org',
      '@type': 'PodcastEpisode',
      name: title,
      partOfSeries: { '@type': 'PodcastSeries', name },
    };
    if (canonicalUrl) data.url = canonicalUrl;
    if (seoImage) data.image = seoImage;
    if (episode.released_at_ms) data.datePublished = new Date(episode.released_at_ms).toISOString();
    const contentSections = sections.filter((s) => !s.skippable);
    if (contentSections.length) {
      data.hasPart = contentSections.map((s) => ({
        '@type': 'Clip',
        name: s.title,
        startOffset: s.timestampSeconds,
        ...(canonicalUrl ? { url: `${canonicalUrl}#t-${s.timestampSeconds}` } : {}),
      }));
    }
    return data;
  }, [episode, playerSections, title, name, canonicalUrl, seoImage]);

  const bookmarkKey = episode ? `${episode.podcast_name}_${episode.id}` : '';
  const isBookmarked = episodeBookmarks.includes(bookmarkKey);

  // Playback is Spotify's own embed player (GlobalPlayer → SpotifyEmbed), never audio
  // served from our domain — that re-hosting is what #570/#588 removed for AdSense.
  // Without a player the summary's timestamps had nothing to seek, so a timestamp click
  // starts this episode in the embed at that point, or seeks it if already loaded.
  const playFrom = (seconds?: number) => {
    if (!episode || !spotifyUri) return;
    if (seconds !== undefined && usePlayerStore.getState().player.currentEpisodeId === episode.id) {
      requestSeek(seconds);
      return;
    }
    playEpisode(
      {
        id: episode.id,
        title,
        showName: name,
        coverUrl: episode.spotify_images?.[0] || undefined,
        spotifyUri,
        timestampedSections: playerSections,
      },
      seconds !== undefined ? { seekTo: seconds } : undefined,
    );
  };

  const [shareCopied, setShareCopied] = useState(false);

  const onBookmark = () => {
    if (!episode) return;
    guard(() => toggleEpisodeBookmark(episode.podcast_name, episode.id));
  };

  const onShare = async () => {
    const url = canonicalUrl || window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: `${name} — ${title}`, url });
        return;
      } catch { /* user cancelled */ }
    }
    try {
      await navigator.clipboard.writeText(url);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    } catch { /* clipboard unavailable */ }
  };

  return (
    <>
      <SEO
        title={title}
        description={`${name} · ${title} — 結構化摘要與重點。`}
        image={seoImage}
        url={canonicalUrl}
        structuredData={structuredData}
      />
      <PageContent
        rail={
          (tickers.length > 0 || (episode?.sector_exposures?.length ?? 0) > 0) ? (
            <nav className="bg-card border border-border rounded-md p-3 max-h-[calc(100vh-96px)] overflow-y-auto scrollbar-thin" aria-label="集數導覽">
              {tickers.length > 0 && (
                <section aria-labelledby="episode-rail-tickers">
                  <h4 id="episode-rail-tickers" className="text-2xs font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">提及個股</h4>
                  <div className="ticker-list flex flex-col gap-1.5">
                    {tickers.map((t) => (
                      <TickerRow key={t.symbol} ticker={t} onClick={() => navigate(`/stock/${encodeURIComponent(t.symbol)}`)} />
                    ))}
                  </div>
                </section>
              )}
              {(episode?.sector_exposures?.length ?? 0) > 0 && (
                <section aria-labelledby="episode-rail-sectors" className={tickers.length > 0 ? 'mt-4' : ''}>
                  <h4 id="episode-rail-sectors" className="text-2xs font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">提及產業</h4>
                  <SectorExposureList
                    exposures={episode!.sector_exposures!}
                    perfMap={sectorPerf}
                    loading={sectorPerfLoading}
                  />
                </section>
              )}
            </nav>
          ) : undefined
        }
      >
        <Link to="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-3"><ChevronLeft size={14} /> 回首頁</Link>

        {loading ? (
          <div className="space-y-4">
            <div className="bg-card border border-border rounded-md h-[120px] animate-pulse" />
            <div className="bg-card border border-border rounded-md h-[200px] animate-pulse" />
          </div>
        ) : !episode ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">找不到這集摘要。</div>
        ) : (
          <>
            {/* Hero */}
            <div className="bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
              <div className="flex flex-col gap-3.5 mb-3.5 sm:flex-row sm:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-3.5">
                  <PodcastAvatar name={name} src={podcasterImageUrl} size="md" className="rounded-[9px] shrink-0" />
                  <div className="min-w-0 flex-1">
                    <Link to={`/podcaster/${encodeURIComponent(name)}`} className="block text-lg font-medium leading-snug break-keep hover:underline">{name}</Link>
                    <div className="text-xs text-muted-foreground">
                      {episode.episode_number != null ? `EP ${episode.episode_number} · ` : ''}
                      {timeAgo(episode.released_at_ms ?? episode.spotify_release_date, episode.created_time)}
                    </div>
                  </div>
                  {/* Saving and sharing are secondary to the episode itself, so they
                      sit as icons in the corner rather than as two labelled pills
                      taking a row of their own on a phone. */}
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={onBookmark}
                      aria-pressed={isBookmarked}
                      aria-label={isBookmarked ? '已收藏' : '收藏'}
                      title={isBookmarked ? '已收藏' : '收藏'}
                      className={cn(
                        'grid place-items-center h-9 w-9 rounded-full transition-colors',
                        isBookmarked ? 'bg-accent-info-soft text-accent-info' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}
                    >
                      <Bookmark size={17} className={isBookmarked ? 'fill-current' : ''} />
                    </button>
                    <button
                      type="button"
                      onClick={onShare}
                      aria-label={shareCopied ? '已複製連結' : '分享'}
                      title={shareCopied ? '已複製連結' : '分享'}
                      className="grid place-items-center h-9 w-9 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    >
                      {shareCopied ? <Check size={17} className="text-sentiment-bull" /> : <Share2 size={17} />}
                    </button>
                  </div>
                </div>
                {(spotifyUri || episode.spotify_url) && (
                <div className="flex w-full items-center gap-2 overflow-x-auto pb-1 sm:w-auto sm:shrink-0 sm:overflow-visible sm:pb-0">
                  {/* Spotify embed only — no audio from our own domain (AdSense
                      replicated content, #588). No Spotify URI, no playback. */}
                  {spotifyUri && (
                    <button type="button" onClick={() => playFrom()} className="inline-flex shrink-0 items-center gap-1.5 px-4 py-2 rounded-full bg-foreground text-background text-sm font-medium hover:opacity-90 transition-opacity">
                      <Play size={14} className="fill-current" /> 播放本集
                    </button>
                  )}
                  {episode.spotify_url && (
                    <a href={episode.spotify_url} target="_blank" rel="noopener noreferrer" className="inline-flex shrink-0 items-center gap-1.5 px-3.5 py-2 rounded-full bg-card border border-border text-sm font-medium hover:bg-muted transition-colors">
                      <ExternalLink size={13} /> Spotify
                    </a>
                  )}
                </div>
                )}
              </div>
              <h1 className="text-2xl font-semibold tracking-[-0.015em] leading-[1.3]">{title}</h1>
              {(heroTags.length > 0 || (episode.sector_exposures?.length ?? 0) > 0) && (() => {
                // A well-tagged episode carried 20 of these, ~240px of hashtags, so the
                // first screen was a title and a tag wall with 關鍵洞察 — the episode's
                // actual judgment — pushed below the fold. Show a few and make the rest a
                // disclosure: the values stay reachable, which a plain truncation would
                // not give.
                const chips = [
                  ...heroTags.slice(0, MAX_HERO_TAGS).map((t) => ({
                    key: `t:${t}`, to: `/topics/${encodeURIComponent(t)}`, label: tagLabelFor(t, tagLabels),
                    cls: 'bg-primary/15 text-primary hover:bg-primary/25',
                  })),
                  // Sectors render in the same row, distinguished by the blue tint + their
                  // own /sector route — a sector is a kind of topic, but ticker-backed.
                  // Deduped by exposure_id: an episode tags the same sector once per section.
                  ...heroSectors.map((exp) => ({
                    key: `s:${exp.exposure_id}`, to: `/sector/${encodeURIComponent(exp.exposure_id)}`, label: exp.display_name,
                    cls: 'bg-accent-info-soft text-accent-info hover:bg-accent-info/25',
                  })),
                ];
                const shown = tagsExpanded ? chips : chips.slice(0, HERO_CHIPS_COLLAPSED);
                const hidden = chips.length - shown.length;
                return (
                  <div className="flex gap-1.5 flex-wrap mt-3">
                    {shown.map((c) => (
                      <Link key={c.key} to={c.to} className={`text-2xs px-2.5 py-0.5 rounded-full font-medium transition-colors ${c.cls}`}>#{c.label}</Link>
                    ))}
                    {hidden > 0 && (
                      <button
                        type="button"
                        onClick={() => setTagsExpanded(true)}
                        aria-expanded={false}
                        className="text-2xs px-2.5 py-0.5 rounded-full border border-border text-muted-foreground font-medium hover:text-foreground hover:border-foreground/30 transition-colors"
                      >
                        +{hidden}
                      </button>
                    )}
                  </div>
                );
              })()}
            </div>

            {episodeLead && <EpisodeInsightCard insight={episodeLead.insight} />}

            {IS_DEV && episode.marp_markdown_content && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-base font-semibold text-muted-foreground mb-3.5">投影片</h3>
                <SlideViewer
                  content={episode.marp_markdown_content}
                  onTickerClick={(symbol) => navigate(`/stock/${encodeURIComponent(symbol)}`)}
                  onTagClick={(tag) => navigate(`/topics/${encodeURIComponent(tag)}`)}
                  episodeId={episode.id}
                  episodeTitle={title}
                  episodeSource={name}
                  spotifyUri={spotifyUri}
                  timestampedSections={playerSections}
                />
              </section>
            )}

            {/* 摘要 — structured summary (headings, paragraphs, ticker/tag/time markers)
                minus the headline + thesis the 關鍵洞察 card above already shows. */}
            {episodeLead?.body.trim() && (
              <section className="mb-3.5 sm:bg-card sm:border sm:border-border sm:rounded-md sm:p-6">
                <h3 className="text-base font-semibold text-muted-foreground mb-3.5">摘要</h3>
                <SummaryMarkdown
                  content={episodeLead.body}
                  onSeek={spotifyUri ? playFrom : undefined}
                  focusMs={searchParams.get('t') && /^\d+$/.test(searchParams.get('t') as string) ? Number(searchParams.get('t')) : null}
                />
              </section>
            )}

            {/* 提及個股 — mobile fallback; desktop uses the right rail. */}
            {tickers.length > 0 && (
              <section className="xl:hidden bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-base font-semibold text-muted-foreground mb-3.5">提及個股</h3>
                <div className="ticker-list flex flex-col gap-1.5">
                  {tickers.map((t) => (
                    <TickerRow key={t.symbol} ticker={t} onClick={() => navigate(`/stock/${encodeURIComponent(t.symbol)}`)} />
                  ))}
                </div>
              </section>
            )}

            {/* 產業 / 主題曝險 — mobile fallback; desktop uses the right rail. */}
            {(episode.sector_exposures?.length ?? 0) > 0 && (
              <section className="xl:hidden bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-base font-semibold text-muted-foreground mb-3.5">提及產業</h3>
                <SectorExposureList
                  exposures={episode.sector_exposures!}
                  perfMap={sectorPerf}
                  loading={sectorPerfLoading}
                />
              </section>
            )}

            {IS_DEV && episode && (
              <EpisodeDebugPanel episode={episode} onUpdated={setEpisode} />
            )}

            {id && podcastName && (
              <CommentSection podcastName={podcastName} episodeId={id} />
            )}
          </>
        )}
      </PageContent>
    </>
  );
};

export default EpisodeDetail;
