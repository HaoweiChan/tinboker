import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { aggregateSentiment, dominantSentiment } from '@/lib/sentiment';
import type { Episode as ApiEpisode } from '@/services/api';
import type { TickerInsight } from '@/services/types';

interface PodcasterFocusCardProps {
  insights: TickerInsight[];
  episodes: ApiEpisode[];
  translationMap: Map<string, string>;
}

const SENT_CLASS = { BULLISH: 'text-sentiment-bull', BEARISH: 'text-sentiment-bear', NEUTRAL: 'text-muted-foreground' } as const;
const SENT_LABEL = { BULLISH: '偏多', BEARISH: '偏空', NEUTRAL: '中性' } as const;

/** What this channel talks about: the ten tickers it mentions most (with its usual
 *  stance on each) and the sector mix of its recent episodes. Both derive from data the
 *  page already loads — 180 days of insights and the latest 30 episodes. */
export const PodcasterFocusCard: React.FC<PodcasterFocusCardProps> = ({ insights, episodes, translationMap }) => {
  const tickers = useMemo(() => {
    const by = new Map<string, TickerInsight[]>();
    for (const i of insights) {
      if (!i.ticker) continue;
      if (!by.has(i.ticker)) by.set(i.ticker, []);
      by.get(i.ticker)!.push(i);
    }
    return [...by.entries()]
      .map(([ticker, list]) => ({ ticker, n: list.length, stance: dominantSentiment(aggregateSentiment(list.map((i) => ({ sentiment_label: i.sentiment_label })))) }))
      .sort((a, b) => b.n - a.n)
      .slice(0, 10);
  }, [insights]);

  const sectors = useMemo(() => {
    // One vote per episode per sector, so a sector named ten times in one episode
    // counts once — this is "how often the show goes there", not mention volume.
    const counts = new Map<string, { display_name: string; icon_id?: string | null; color_hex?: string | null; n: number }>();
    for (const ep of episodes) {
      const seen = new Set<string>();
      for (const s of ep.sector_exposures ?? []) {
        if (!s.exposure_id || seen.has(s.exposure_id)) continue;
        seen.add(s.exposure_id);
        const cur = counts.get(s.exposure_id);
        if (cur) cur.n += 1;
        else counts.set(s.exposure_id, { display_name: s.display_name, icon_id: (s as { icon_id?: string | null }).icon_id, color_hex: (s as { color_hex?: string | null }).color_hex, n: 1 });
      }
    }
    return [...counts.entries()].map(([exposure_id, v]) => ({ exposure_id, ...v })).sort((a, b) => b.n - a.n).slice(0, 8);
  }, [episodes]);

  if (tickers.length === 0 && sectors.length === 0) return null;
  const maxN = tickers[0]?.n ?? 1;
  const epCount = episodes.length || 1;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
      {tickers.length > 0 && (
        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">最常提到的個股 · 近 180 天</h3>
          <div className="flex flex-col gap-2">
            {tickers.map((t) => (
              <Link key={t.ticker} to={`/stock/${encodeURIComponent(t.ticker)}`} className="group flex items-center gap-3 min-w-0">
                <span className="w-28 shrink-0 truncate text-sm font-medium group-hover:text-primary transition-colors">
                  {translationMap.get(t.ticker) ? `${t.ticker} ${translationMap.get(t.ticker)}` : t.ticker}
                </span>
                <span className="relative flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <span className="absolute inset-y-0 left-0 rounded-full bg-primary/60" style={{ width: `${(t.n / maxN) * 100}%` }} />
                </span>
                <span className="w-8 shrink-0 text-right text-xs font-mono tabular-nums text-muted-foreground">{t.n}</span>
                <span className={`w-8 shrink-0 text-right text-2xs font-medium ${SENT_CLASS[t.stance]}`}>{SENT_LABEL[t.stance]}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {sectors.length > 0 && (
        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">常聊的產業與題材 · 最近 {episodes.length} 集</h3>
          <div className="flex flex-col gap-2">
            {sectors.map((s) => (
              <Link key={s.exposure_id} to={`/sector/${encodeURIComponent(s.exposure_id)}`} className="group flex items-center gap-2.5 min-w-0">
                <SectorIcon exposureId={s.exposure_id} iconId={s.icon_id} color={s.color_hex} size={13} variant="chip" />
                <span className="w-32 shrink-0 truncate text-sm font-medium group-hover:text-primary transition-colors">{s.display_name}</span>
                <span className="relative flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(s.n / epCount) * 100}%`, backgroundColor: s.color_hex || 'hsl(var(--primary) / 0.6)' }} />
                </span>
                <span className="w-12 shrink-0 text-right text-xs font-mono tabular-nums text-muted-foreground">{Math.round((s.n / epCount) * 100)}%</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
