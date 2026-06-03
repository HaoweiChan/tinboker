import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, Play, ExternalLink } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PodcastAvatar } from '@/components/common/PodcastAvatar';
import { PageContent } from '@/components/layout/PageContent';
import { TickerRow } from '@/components/redesign';
import { cn } from '@/lib/utils';
import { getEpisodeById, getPodcastByName, type Episode as ApiEpisode } from '@/services';
import { fetchWithFallback } from '@/services/api/migration';
import { parseTimestampedSections, type TimestampedSection } from '@/utils/parseTimestampedSections';
import { usePlayerStore } from '@/store/usePlayerStore';
import { CommentSection } from '@/components/episode/CommentSection';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { EpisodeInsightCard, type EpisodeInsight } from '@/components/episode/EpisodeInsightCard';
import type { Sentiment } from '@/lib/sentiment';

/** Render plain text with inline `[label](#ticker:SYMBOL)` markers as clickable
 *  localized labels (the agents pipeline emits these in summaries/insights). */
const TICKER_MARKER = /\[([^\]]+)\]\(#ticker:([^)]+)\)/g;
const MentionText: React.FC<{ text: string }> = ({ text }) => {
  const parts: React.ReactNode[] = [];
  const re = new RegExp(TICKER_MARKER);
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const symbol = m[2].trim().toUpperCase();
    parts.push(
      <Link key={key++} to={`/stock/${encodeURIComponent(symbol)}`} className="text-accent-info hover:underline font-medium">
        {m[1]}
      </Link>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
};

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

function bulletsFrom(ep: ApiEpisode | null): string[] {
  if (!ep) return [];
  if (Array.isArray(ep.key_insights) && ep.key_insights.length > 0) return ep.key_insights.filter((s) => s && s.trim()).slice(0, 8);
  const src = ep.modified_summary_content || ep.summary_content || '';
  return src
    .split('\n')
    .map((l) => l.replace(/^[#>\-*\s]+/, '').replace(/\(#time:\s*\d+\)/g, '').replace(/[*_`]/g, '').trim())
    .filter((l) => l.length > 4)
    .slice(0, 8);
}

function cleanSummaryLine(line: string): string {
  return line
    .replace(/^(?:#{1,6}\s*)+/, '')
    .replace(/\s*\(#time:\s*\d+\)/g, '')
    .replace(/^[-*\s]+/, '')
    .replace(/\[([^\]]+)\]\((?!#ticker:)[^)]+\)/g, '$1')
    .replace(/[*_`>~]/g, '')
    .trim();
}

function truncateText(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max).trimEnd()}...` : text;
}

function episodeInsightFrom(ep: ApiEpisode | null, fallbackTitle: string): EpisodeInsight | null {
  if (!ep) return null;
  const src = ep.modified_summary_content || ep.summary_content || '';
  const lines = src.split('\n').map((line) => line.trim()).filter(Boolean);
  const headline = truncateText(cleanSummaryLine(lines.find((line) => line.startsWith('#')) || lines[0] || fallbackTitle), 58);
  const thesis = truncateText(cleanSummaryLine(lines.find((line) => !line.startsWith('#') && line.length > 12) || ''), 96);
  const keyHighlights = Array.isArray(ep.key_insights) ? ep.key_insights.map((line) => truncateText(cleanSummaryLine(line), 34)).filter(Boolean) : [];
  const sectionHighlights = lines
    .filter((line) => /^#{2,}/.test(line))
    .map(cleanSummaryLine)
    .filter((line) => line && line !== headline)
    .map((line) => truncateText(line, 34))
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
      const [ep, podcast] = await Promise.all([
        fetchWithFallback<ApiEpisode | null>(() => getEpisodeById(podcastName, id), null, `getEpisodeById:${podcastName}/${id}`).catch(() => null),
        podcastName ? fetchWithFallback(() => getPodcastByName(podcastName), null, `getPodcastByName:${podcastName}`).catch(() => null) : Promise.resolve(null),
      ]);
      if (!alive) return;
      setEpisode(ep);
      setPodcastImageUrl(podcast?.image_url || null);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [id, podcastName]);

  const bullets = useMemo(() => bulletsFrom(episode), [episode]);
  const chapters = useMemo<TimestampedSection[]>(() => (episode?.events_markdown_content ? parseTimestampedSections(episode.events_markdown_content) : []), [episode]);
  const clips = useMemo<TimestampedSection[]>(() => (episode?.sentences_markdown_content ? parseTimestampedSections(episode.sentences_markdown_content).slice(0, 8) : []), [episode]);
  const tickerSymbols = useMemo(() => (Array.isArray(episode?.related_tickers) ? episode!.related_tickers.slice(0, 8) : []), [episode]);
  const priceMap = useStockPriceMap(tickerSymbols);
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
        changePercent: firstMapValue(priceMap, keys),
      };
    });
  }, [tickerSymbols, rawTranslationMap, episodeSentiments, priceMap, episode]);
  const spotifyUri = useMemo(() => spotifyUriFrom(episode), [episode]);

  const title = episode?.episode_title || (episode?.episode_number != null ? `EP ${episode.episode_number}` : '集數摘要');
  const name = episode?.podcast_name || podcastName || '節目';
  const episodeInsight = useMemo(() => episodeInsightFrom(episode, title), [episode, title]);
  const podcasterImageUrl = podcastImageUrl || episode?.spotify_images?.[0] || null;

  const onPlay = () => {
    if (!episode) return;
    playEpisode({
      id: episode.id,
      title,
      showName: name,
      coverUrl: episode.spotify_images?.[0] || undefined,
      spotifyUri,
      timestampedSections: chapters.length ? chapters : clips,
    });
  };

  return (
    <>
      <SEO title={title} description={`${name} · ${title} — 結構化重點與關鍵片段。`} />
      <PageContent
        rail={
          tickers.length > 0 || chapters.length > 0 ? (
            <nav className="bg-card border border-border rounded-md p-3 max-h-[calc(100vh-96px)] overflow-hidden" aria-label="集數導覽">
              {tickers.length > 0 && (
                <section aria-labelledby="episode-rail-tickers">
                  <h4 id="episode-rail-tickers" className="text-[11px] font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">提及股票</h4>
                  <div className="flex flex-col gap-1.5">
                    {tickers.map((t) => (
                      <TickerRow key={t.symbol} ticker={t} onClick={() => navigate(`/stock/${encodeURIComponent(t.symbol)}`)} />
                    ))}
                  </div>
                </section>
              )}
              {chapters.length > 0 && (
                <section aria-labelledby="episode-rail-chapters" className={cn(tickers.length > 0 && 'mt-4 pt-4 border-t border-border')}>
                  <h4 id="episode-rail-chapters" className="text-[11px] font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">章節</h4>
                  <div className="flex flex-col gap-0.5 max-h-[44vh] overflow-y-auto pr-1">
                  {chapters.map((c, i) => (
                    <button key={i} type="button" onClick={() => requestSeek(c.timestampSeconds)} className="flex items-center gap-2.5 px-2 py-1.5 rounded text-left text-[13px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                      <span className="font-mono text-[11px] text-muted-foreground shrink-0">{c.formattedTime}</span>
                      <span className="truncate">{c.title}</span>
                    </button>
                  ))}
                  </div>
                </section>
              )}
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
                    {timeAgo(episode.spotify_release_date, episode.created_time)}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button type="button" onClick={onPlay} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-foreground text-background text-[13px] font-medium hover:opacity-90 transition-opacity">
                    <Play size={14} className="fill-current" /> 播放本集
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
                  {episode.tags.map((t) => (
                    <Link key={t} to={`/topics/${encodeURIComponent(t)}`} className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-accent-info-soft hover:text-accent-info transition-colors">#{t}</Link>
                  ))}
                </div>
              )}
            </div>

            {episodeInsight && <EpisodeInsightCard insight={episodeInsight} />}

            {/* 本集重點 */}
            {bullets.length > 0 && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">本集重點</h3>
                <ul className="flex flex-col gap-2.5">
                  {bullets.map((b, i) => (
                    <li key={i} className="grid grid-cols-[14px_1fr] gap-2 text-[14px] leading-[1.55]">
                      <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                      <span><MentionText text={b} /></span>
                    </li>
                  ))}
                </ul>
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

            {/* 關鍵片段 */}
            {clips.length > 0 && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">關鍵片段</h3>
                <div className="flex flex-col gap-2">
                  {clips.map((c, i) => (
                    <button key={i} type="button" onClick={() => requestSeek(c.timestampSeconds)} className={cn('grid grid-cols-[56px_1fr] gap-3.5 px-3.5 py-3 rounded-md bg-muted/60 border-l-2 border-muted-foreground/40 text-left hover:bg-muted transition-colors')}>
                      <span className="font-mono text-[12px] font-medium text-muted-foreground">{c.formattedTime}</span>
                      <span className="text-[14px] leading-[1.55]">「{c.title}」</span>
                    </button>
                  ))}
                </div>
              </section>
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
