import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { SentBar } from '@/components/redesign';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { getWeek } from '@/services/api/weekly';
import type { Weekly, WeeklyTicker } from '@/validation/schemas';

const WEEK_RE = /^(\d{4})-W(\d{2})$/;

/** ISO week arithmetic without a date library: shift by whole weeks via the Monday. */
function shiftWeek(week: string, delta: number): string | null {
  const m = week.match(WEEK_RE);
  if (!m) return null;
  const year = Number(m[1]), num = Number(m[2]);
  // Monday of ISO week 1 is the Monday on or before Jan 4.
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const monday = new Date(jan4.getTime() - ((jan4.getUTCDay() + 6) % 7) * 86400e3 + (num - 1 + delta) * 7 * 86400e3);
  const thursday = new Date(monday.getTime() + 3 * 86400e3);
  const isoYear = thursday.getUTCFullYear();
  const firstThu = new Date(Date.UTC(isoYear, 0, 4));
  const firstMonday = new Date(firstThu.getTime() - ((firstThu.getUTCDay() + 6) % 7) * 86400e3);
  const n = Math.round((monday.getTime() - firstMonday.getTime()) / (7 * 86400e3)) + 1;
  return `${isoYear}-W${String(n).padStart(2, '0')}`;
}

const weekTitle = (w: Weekly) => `${w.start.replace(/-/g, '/')} – ${w.end.slice(5).replace('-', '/')} Podcast 週報`;

const stance = (t: WeeklyTicker) => {
  const cur = t.bull - t.bear, prev = t.prev_bull - t.prev_bear;
  if (t.prev_bull + t.prev_neu + t.prev_bear === 0) return { label: '本週新進', cls: 'text-accent-info' };
  if (cur > 0 && prev <= 0) return { label: '轉多', cls: 'text-sentiment-bull' };
  if (cur < 0 && prev >= 0) return { label: '轉空', cls: 'text-sentiment-bear' };
  return { label: '持平', cls: 'text-muted-foreground' };
};

export const WeeklyPage: React.FC = () => {
  const { week = '' } = useParams<{ week: string }>();
  const [data, setData] = useState<Weekly | null>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'missing'>('loading');

  useEffect(() => {
    if (!WEEK_RE.test(week)) { setState('missing'); return; }
    let alive = true;
    setState('loading');
    getWeek(week)
      .then((w) => { if (alive) { setData(w); setState('ok'); } })
      .catch(() => { if (alive) setState('missing'); });
    return () => { alive = false; };
  }, [week]);

  const prev = useMemo(() => shiftWeek(week, -1), [week]);
  const next = useMemo(() => shiftWeek(week, 1), [week]);
  const canonical = typeof window !== 'undefined' ? `${window.location.origin}/weekly/${week}` : undefined;
  const title = data ? weekTitle(data) : `${week} Podcast 週報`;
  const description = data
    ? `${data.start.replace(/-/g, '/')} 到 ${data.end.replace(/-/g, '/')}，${data.podcasts.length} 個節目共 ${data.episode_count} 集。本週最常提到：${data.tickers.slice(0, 5).map((t) => t.name ? `${t.name}（${t.ticker}）` : t.ticker).join('、')}。`
    : '這一週台灣財經 Podcast 聊了哪些個股與題材，由 TinBoker 結構化整理。';
  const structuredData = data ? {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: title,
    datePublished: `${data.end}T23:59:00+08:00`,
    url: canonical,
    publisher: { '@type': 'Organization', name: '聽播客 TinBoker' },
  } : undefined;

  return (
    <>
      <SEO title={title} description={description} url={canonical} type="article" structuredData={structuredData} />
      <PageContent>
        <div className="flex items-center justify-between gap-3 mb-3">
          <Link to="/weekly" className="text-xs text-muted-foreground hover:text-foreground">← 所有週報</Link>
          <div className="flex items-center gap-1 text-xs">
            {prev && <Link to={`/weekly/${prev}`} className="inline-flex items-center gap-0.5 px-2 py-1 rounded-md border border-border hover:bg-muted"><ChevronLeft size={12} />上一週</Link>}
            {next && <Link to={`/weekly/${next}`} className="inline-flex items-center gap-0.5 px-2 py-1 rounded-md border border-border hover:bg-muted">下一週<ChevronRight size={12} /></Link>}
          </div>
        </div>

        {state === 'loading' && <div className="bg-card border border-border rounded-md h-40 animate-pulse mb-[18px]" />}
        {state === 'missing' && (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">這一週沒有已分析的集數。</div>
        )}
        {state === 'ok' && data && (
          <>
            <div className="bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
              <h1 className="text-2xl font-semibold tracking-[-0.02em]">{title}</h1>
              <p className="text-base text-muted-foreground mt-1 max-w-[60ch] leading-[1.55]">{description}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {data.podcasts.map((p) => (
                  <Link key={p.name} to={`/podcaster/${encodeURIComponent(p.name)}`} className="text-xs px-3 py-1 rounded-full bg-muted text-muted-foreground hover:text-foreground">
                    {p.name} <strong className="font-mono text-foreground ml-1 tabular-nums">{p.episodes}</strong>
                  </Link>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-[18px]">
              <div className="lg:col-span-2 bg-card border border-border rounded-md p-5">
                <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">本週熱門個股</h2>
                <div className="divide-y divide-border/60">
                  {data.tickers.map((t) => {
                    const s = stance(t);
                    const total = t.bull + t.neu + t.bear;
                    return (
                      <div key={t.ticker} className="flex items-center gap-3 py-2 min-w-0">
                        <Link to={`/stock/${encodeURIComponent(t.ticker)}`} className="w-36 shrink-0 truncate text-sm font-medium hover:text-primary transition-colors">
                          {t.name ? `${t.name} ${t.ticker}` : t.ticker}
                        </Link>
                        <span className="w-10 shrink-0 text-xs font-mono tabular-nums text-muted-foreground">{t.episodes} 集</span>
                        <div className="flex-1 min-w-0">{total > 0 ? <SentBar bull={t.bull} neutral={t.neu} bear={t.bear} /> : <div className="sent-bar opacity-30" />}</div>
                        <span className="w-24 shrink-0 text-right text-xs tabular-nums">
                          {total > 0 ? <><span className="text-sentiment-bull">多 {t.bull}</span> · <span className="text-muted-foreground">中 {t.neu}</span> · <span className="text-sentiment-bear">空 {t.bear}</span></> : <span className="text-muted-foreground">—</span>}
                        </span>
                        <span className={`w-14 shrink-0 text-right text-2xs font-medium ${s.cls}`}>{s.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="bg-card border border-border rounded-md p-5">
                <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">本週產業與題材</h2>
                <div className="flex flex-col gap-2">
                  {data.sectors.map((sec) => (
                    <Link key={sec.exposure_id} to={`/sector/${encodeURIComponent(sec.exposure_id)}`} className="group flex items-center gap-2.5 min-w-0">
                      <SectorIcon exposureId={sec.exposure_id} iconId={sec.icon_id} color={sec.color_hex} size={13} variant="chip" />
                      <span className="flex-1 truncate text-sm font-medium group-hover:text-primary transition-colors">{sec.display_name}</span>
                      <span className="relative w-20 h-2 rounded-full bg-muted overflow-hidden shrink-0">
                        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(sec.episodes / data.episode_count) * 100}%`, backgroundColor: sec.color_hex || 'hsl(var(--primary) / 0.6)' }} />
                      </span>
                      <span className="w-8 shrink-0 text-right text-xs font-mono tabular-nums text-muted-foreground">{sec.episodes}</span>
                    </Link>
                  ))}
                </div>
              </div>
            </div>

            <h2 className="text-sm font-semibold text-muted-foreground mb-3">本週集數</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.episodes.map((ep) => (
                <Link key={ep.id} to={`/episode/${encodeURIComponent(ep.id)}`} className="block bg-card border border-border rounded-md p-4 hover:bg-muted/40 transition-colors">
                  <div className="text-2xs text-muted-foreground tabular-nums mb-1">
                    {ep.podcast_name}{ep.released_at_ms ? ` · ${new Date(ep.released_at_ms).toISOString().slice(5, 10).replace('-', '/')}` : ''}
                  </div>
                  <div className="text-sm font-medium leading-snug">{ep.episode_title || (ep.episode_number != null ? `EP ${ep.episode_number}` : ep.id)}</div>
                  {ep.key_insights.length > 0 && (
                    <ul className="mt-2 text-xs text-muted-foreground leading-relaxed list-disc pl-4">
                      {ep.key_insights.map((k, i) => <li key={i}>{k}</li>)}
                    </ul>
                  )}
                </Link>
              ))}
            </div>
          </>
        )}
      </PageContent>
    </>
  );
};

export default WeeklyPage;
