import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { ChevronLeft, Play, ExternalLink } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { PodMark, TickerRow } from '@/components/redesign';
import { cn } from '@/lib/utils';
import { getEpisodeById, type Episode as ApiEpisode } from '@/services';
import { fetchWithFallback } from '@/services/api/migration';
import { parseTimestampedSections, type TimestampedSection } from '@/utils/parseTimestampedSections';
import { usePlayerStore } from '@/store/usePlayerStore';
import { CommentSection } from '@/components/episode/CommentSection';

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

export const EpisodeDetail: React.FC = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const podcastName = searchParams.get('podcast') || '';
  const { playEpisode, requestSeek } = usePlayerStore();

  const [episode, setEpisode] = useState<ApiEpisode | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    window.scrollTo(0, 0);
    if (!id) return;
    let alive = true;
    setLoading(true);
    (async () => {
      const ep = await fetchWithFallback<ApiEpisode | null>(() => getEpisodeById(podcastName, id), null, `getEpisodeById:${podcastName}/${id}`).catch(() => null);
      if (!alive) return;
      setEpisode(ep);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [id, podcastName]);

  const bullets = useMemo(() => bulletsFrom(episode), [episode]);
  const chapters = useMemo<TimestampedSection[]>(() => (episode?.events_markdown_content ? parseTimestampedSections(episode.events_markdown_content) : []), [episode]);
  const clips = useMemo<TimestampedSection[]>(() => (episode?.sentences_markdown_content ? parseTimestampedSections(episode.sentences_markdown_content).slice(0, 8) : []), [episode]);
  const tickers = useMemo(() => (Array.isArray(episode?.related_tickers) ? episode!.related_tickers.slice(0, 8).map((s) => ({ symbol: s })) : []), [episode]);
  const spotifyUri = useMemo(() => spotifyUriFrom(episode), [episode]);

  const title = episode?.episode_title || (episode?.episode_number != null ? `EP ${episode.episode_number}` : '集數摘要');
  const name = episode?.podcast_name || podcastName || '節目';

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
          chapters.length > 0 ? (
            <nav className="bg-card border border-border rounded-md p-3">
              <h4 className="text-[11px] font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2 mb-2">章節</h4>
              <div className="flex flex-col gap-0.5">
                {chapters.map((c, i) => (
                  <button key={i} type="button" onClick={() => requestSeek(c.timestampSeconds)} className="flex items-center gap-2.5 px-2 py-1.5 rounded text-left text-[13px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                    <span className="font-mono text-[11px] text-muted-foreground shrink-0">{c.formattedTime}</span>
                    <span className="truncate">{c.title}</span>
                  </button>
                ))}
              </div>
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
                {episode.spotify_images?.[0] ? <img src={episode.spotify_images[0]} alt="" className="w-10 h-10 rounded-[9px] object-cover shrink-0" /> : <PodMark label={name.charAt(0)} kind="mute" size={40} />}
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

            {/* 本集重點 */}
            {bullets.length > 0 && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">本集重點</h3>
                <ul className="flex flex-col gap-2.5">
                  {bullets.map((b, i) => (
                    <li key={i} className="grid grid-cols-[14px_1fr] gap-2 text-[14px] leading-[1.55]">
                      <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-foreground" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* 提及股票 */}
            {tickers.length > 0 && (
              <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">提及股票</h3>
                <div className="flex flex-col gap-1.5">
                  {tickers.map((t) => (
                    <TickerRow key={t.symbol} ticker={t} onClick={() => (window.location.href = `/stock/${encodeURIComponent(t.symbol)}`)} />
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
