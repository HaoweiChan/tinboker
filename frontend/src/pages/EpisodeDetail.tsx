import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, Play, ExternalLink, Bookmark } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PodcastAvatar } from '@/components/common/PodcastAvatar';
import { PageContent } from '@/components/layout/PageContent';
import { TickerRow } from '@/components/redesign';
import { cn } from '@/lib/utils';
import { getEpisodeById, getEpisodeByIdOnly, getEpisodeAudioUrl, getPodcastByName, type Episode as ApiEpisode } from '@/services';
import { fetchWithFallback } from '@/services/api/migration';
import { parseTimestampedSections, type TimestampedSection } from '@/utils/parseTimestampedSections';
import { usePlayerStore } from '@/store/usePlayerStore';
import { useAppStore, useEpisodeBookmarks } from '@/store/useAppStore';
import { CommentSection } from '@/components/episode/CommentSection';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap, isRecentEpisode } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { EpisodeInsightCard, type EpisodeInsight } from '@/components/episode/EpisodeInsightCard';
import { SummaryMarkdown } from '@/components/episode/SummaryMarkdown';
import { EpisodeDebugPanel } from '@/components/episode/EpisodeDebugPanel';
import type { Sentiment } from '@/lib/sentiment';

const IS_DEV = import.meta.env.DEV || (import.meta.env.VITE_STAGE as string) === 'DEV';

// Episodes can carry dozens of tags; show only a handful so the row stays meaningful.
const MAX_HERO_TAGS = 6;

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

function cleanSummaryLine(line: string): string {
  return line
    .replace(/^(?:#{1,6}\s*)+/, '')
    .replace(/\s*\(#time:\s*\d+\)/g, '')
    .replace(/^[-*\s]+/, '')
    // Strip ALL inline markers ([label](#ticker:..|#tag:..|url)) down to their label
    // so the insight reads as plain text, never raw markdown.
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`>~]/g, '')
    .trim();
}

function episodeInsightFrom(ep: ApiEpisode | null, fallbackTitle: string): EpisodeInsight | null {
  if (!ep) return null;
  const src = ep.modified_summary_content || ep.summary_content || '';
  const lines = src.split('\n').map((line) => line.trim()).filter(Boolean);
  // No truncation: the insight is the concise essence of the article and is shown
  // in full (no "…"). The headline / thesis / section headings are already short.
  const headline = cleanSummaryLine(lines.find((line) => line.startsWith('#')) || lines[0] || fallbackTitle);
  const thesis = cleanSummaryLine(lines.find((line) => !line.startsWith('#') && line.length > 12) || '');
  const keyHighlights = Array.isArray(ep.key_insights) ? ep.key_insights.map((line) => cleanSummaryLine(line)).filter(Boolean) : [];
  const sectionHighlights = lines
    .filter((line) => /^#{2,}/.test(line))
    .map(cleanSummaryLine)
    .filter((line) => line && line !== headline)
    .slice(0, 3);
  const highlights = (keyHighlights.length > 0 ? keyHighlights : sectionHighlights).slice(0, 3);

  if (!headline && !thesis && highlights.length === 0) return null;
  return {
    headline: headline || fallbackTitle,
    thesis: thesis || undefined,
    highlights,
  };
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
  const episodeBookmarks = useEpisodeBookmarks();

  const [episode, setEpisode] = useState<ApiEpisode | null>(null);
  const [podcastImageUrl, setPodcastImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    window.scrollTo(0, 0);
    if (!id) return;
    let alive = true;
    setLoading(true);
    setPodcastImageUrl(null);
    (async () => {
      // On a cold load (deep link / refresh / shared URL) there is no ?podcast= to
      // supply the show name, so fall back to the by-id endpoint, then resolve the
      // show name from the response for the podcast-image fetch.
      const ep = await fetchWithFallback<ApiEpisode | null>(
        () => (podcastName ? getEpisodeById(podcastName, id) : getEpisodeByIdOnly(id)),
        null,
        `getEpisodeById:${podcastName || '-'}/${id}`,
      ).catch(() => null);
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

  const chapters = useMemo<TimestampedSection[]>(() => (episode?.events_markdown_content ? parseTimestampedSections(episode.events_markdown_content) : []), [episode]);
  const clips = useMemo<TimestampedSection[]>(() => (episode?.sentences_markdown_content ? parseTimestampedSections(episode.sentences_markdown_content).slice(0, 8) : []), [episode]);
  const summarySections = useMemo<TimestampedSection[]>(() => {
    const content = episode?.modified_summary_content || episode?.summary_content;
    return content ? parseTimestampedSections(content) : [];
  }, [episode]);
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

  const title = episode?.episode_title || (episode?.episode_number != null ? `EP ${episode.episode_number}` : '集數摘要');
  const name = episode?.podcast_name || podcastName || '節目';
  const episodeInsight = useMemo(() => episodeInsightFrom(episode, title), [episode, title]);
  const podcasterImageUrl = podcastImageUrl || episode?.spotify_images?.[0] || null;

  // SEO: a PodcastEpisode JSON-LD with Clip parts (one per timestamped section) so
  // Google can surface chapters, plus a canonical URL + og:image. Sections come from
  // the same timestamped parse the page already uses.
  const canonicalUrl = episode ? `https://tinboker.com/episode/${episode.id}` : undefined;
  const seoImage = episode?.summary_image_public_url || episode?.spotify_images?.[0] || podcasterImageUrl || undefined;
  const structuredData = useMemo<Record<string, unknown> | undefined>(() => {
    if (!episode) return undefined;
    const sections = chapters.length ? chapters : clips.length ? clips : summarySections;
    const data: Record<string, unknown> = {
      '@context': 'https://schema.org',
      '@type': 'PodcastEpisode',
      name: title,
      partOfSeries: { '@type': 'PodcastSeries', name },
    };
    if (canonicalUrl) data.url = canonicalUrl;
    if (seoImage) data.image = seoImage;
    if (episode.released_at_ms) data.datePublished = new Date(episode.released_at_ms).toISOString();
    if (sections.length) {
      data.hasPart = sections.map((s) => ({
        '@type': 'Clip',
        name: s.title,
        startOffset: s.timestampSeconds,
        ...(canonicalUrl ? { url: `${canonicalUrl}#t-${s.timestampSeconds}` } : {}),
      }));
    }
    return data;
  }, [episode, chapters, clips, summarySections, title, name, canonicalUrl, seoImage]);

  const bookmarkKey = episode ? `${episode.podcast_name}_${episode.id}` : '';
  const isBookmarked = episodeBookmarks.includes(bookmarkKey);

  const onPlay = () => {
    if (!episode) return;
    playEpisode({
      id: episode.id,
      title,
      showName: name,
      coverUrl: episode.spotify_images?.[0] || undefined,
      spotifyUri,
      mp3Url: episode.mp3_url || episode.mp3_public_url
        ? getEpisodeAudioUrl(episode.podcast_name, episode.id)
        : undefined,
      timestampedSections: chapters.length ? chapters : clips.length ? clips : summarySections,
    });
  };

  const onBookmark = () => {
    if (!episode) return;
    toggleEpisodeBookmark(episode.podcast_name, episode.id);
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
          tickers.length > 0 ? (
            <nav className="bg-card border border-border rounded-md p-3 max-h-[calc(100vh-96px)] overflow-hidden" aria-label="集數導覽">
              <section aria-labelledby="episode-rail-tickers">
                <h4 id="episode-rail-tickers" className="text-[11px] font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">提及股票</h4>
                <div className="flex flex-col gap-1.5">
                  {tickers.map((t) => (
                    <TickerRow key={t.symbol} ticker={t} onClick={() => navigate(`/stock/${encodeURIComponent(t.symbol)}`)} />
                  ))}
                </div>
              </section>
            </nav>
          ) : undefined
        }
      >
        <Link to="/" className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground mb-3"><ChevronLeft size={14} /> 回首頁</Link>

        {loading ? (
          <div className="space-y-4">
            <div className="bg-card border border-border rounded-md h-[120px] animate-pulse" />
            <div className="bg-card border border-border rounded-md h-[200px] animate-pulse" />
          </div>
        ) : !episode ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">找不到這集摘要。</div>
        ) : (
          <>
            {/* Hero */}
            <div className="bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
              <div className="flex items-center gap-3.5 mb-3.5">
                <PodcastAvatar name={name} src={podcasterImageUrl} size="md" className="rounded-[9px]" />
                <div className="min-w-0 flex-1">
                  <Link to={`/podcaster/${encodeURIComponent(name)}`} className="text-[14px] font-medium hover:underline">{name}</Link>
                  <div className="text-[12px] text-muted-foreground">
                    {episode.episode_number != null ? `EP ${episode.episode_number} · ` : ''}
                    {timeAgo(episode.released_at_ms ?? episode.spotify_release_date, episode.created_time)}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button type="button" onClick={onPlay} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-foreground text-background text-[13px] font-medium hover:opacity-90 transition-opacity">
                    <Play size={14} className="fill-current" /> 播放本集
                  </button>
                  <button
                    type="button"
                    onClick={onBookmark}
                    className={cn(
                      'inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[13px] font-medium transition-colors',
                      isBookmarked ? 'bg-accent-info-soft text-accent-info' : 'bg-card border border-border hover:bg-muted',
                    )}
                  >
                    <Bookmark size={13} className={isBookmarked ? 'fill-current' : ''} />
                    {isBookmarked ? '已收藏' : '收藏'}
                  </button>
                  {episode.spotify_url && (
                    <a href={episode.spotify_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-card border border-border text-[13px] font-medium hover:bg-muted transition-colors">
                      <ExternalLink size={13} /> Spotify
                    </a>
                  )}
                </div>
              </div>
              <h1 className="text-[24px] sm:text-[26px] font-semibold tracking-[-0.015em] leading-[1.3]">{title}</h1>
              {episode.tags && episode.tags.length > 0 && (
                <div className="flex gap-1.5 flex-wrap mt-3">
                  {episode.tags.slice(0, MAX_HERO_TAGS).map((t) => (
                    <Link key={t} to={`/topics/${encodeURIComponent(t)}`} className="text-[12px] px-2.5 py-0.5 rounded-full bg-amber-400/20 text-amber-700 dark:text-amber-300 font-medium hover:bg-amber-400/35 transition-colors">#{t}</Link>
                  ))}
                </div>
              )}
            </div>

            {episodeInsight && <EpisodeInsightCard insight={episodeInsight} />}

            {/* 摘要 — full structured summary (headings, paragraphs, ticker/tag/time markers) */}
            {(episode.modified_summary_content || episode.summary_content) && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">摘要</h3>
                <SummaryMarkdown content={episode.modified_summary_content || episode.summary_content || ''} onSeek={requestSeek} />
              </section>
            )}

            {/* 提及股票 — mobile fallback; desktop uses the right rail. */}
            {tickers.length > 0 && (
              <section className="xl:hidden bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">提及股票</h3>
                <div className="flex flex-col gap-1.5">
                  {tickers.map((t) => (
                    <TickerRow key={t.symbol} ticker={t} onClick={() => navigate(`/stock/${encodeURIComponent(t.symbol)}`)} />
                  ))}
                </div>
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
