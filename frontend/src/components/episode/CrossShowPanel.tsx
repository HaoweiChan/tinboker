import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { getSentimentDisplay } from '@/lib/sentiment';
import { isUmbrellaSector } from '@/lib/sectors';
import { getEpisodeCrossShow } from '@/services/api/mentions';
import type { Episode, SectorBoardItem } from '@/services/api/podcasts';
import { useStockPriceSinceMap, isRecentEpisode } from '@/hooks/useStockPriceSinceMap';
import { useAppStore } from '@/store/useAppStore';
import { ChangePct } from '@/components/topics/ChangePct';
import type { CrossShowResponse } from '@/validation/schemas';
import { CROSS_SHOW_LOCKED, crossShowLead, isOpposite, othersCounts, othersLean, stanceZh } from '../../../shared/crossShow.js';

type Subject = CrossShowResponse['subjects'][number];
const subjectKey = (subject: Subject) => `${subject.mention_type}:${subject.ticker ?? subject.exposure_id}`;

interface Props {
  episode: Episode;
  data: CrossShowResponse | null;
  sectorPerf: Map<string, SectorBoardItem>;
  sectorPerfLoading: boolean;
}

/** One content_mentions list; only other shows' per-subject comparisons require membership. */
export const CrossShowPanel: React.FC<Props> = ({ episode, data, sectorPerf, sectorPerfLoading }) => {
  const stockColorMode = useAppStore((s) => s.stockColorMode);
  const isMember = useAppStore((s) => !!s.user?.is_member);
  const [detail, setDetail] = useState<CrossShowResponse | null>(null);
  const [detailFailed, setDetailFailed] = useState(false);
  useEffect(() => {
    setDetail(null);
    setDetailFailed(false);
    if (!isMember) return;
    let alive = true;
    getEpisodeCrossShow(episode.id, true)
      .then((res) => { if (alive) setDetail(res); })
      .catch(() => { if (alive) setDetailFailed(true); });
    return () => { alive = false; };
  }, [episode.id, isMember]);

  // The hook's input uses only content_mentions, never summary-derived ticker links.
  const priceEpisodes = useMemo(() => [{
    ...episode,
    related_tickers: (data?.subjects ?? []).flatMap((s) => s.mention_type === 'ticker' && s.ticker ? [s.ticker] : []),
  }], [episode, data]);
  const priceSinceMap = useStockPriceSinceMap(priceEpisodes);
  const comparisons = new Map((isMember ? detail?.rows ?? [] : []).map((r) => [subjectKey(r), r]));

  if (!data?.subjects.length || data.episode_id !== episode.id) return null;
  const tone = (stance: Parameters<typeof getSentimentDisplay>[0] | undefined) => getSentimentDisplay(stance ?? null, stockColorMode)?.toneClass ?? 'text-muted-foreground';

  return (
    <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-title">
      <h3 id="cross-show-title" className="heading-accent text-lg font-semibold text-foreground mb-2">這集談到的</h3>
      <p className="text-sm text-muted-foreground leading-[1.65] mb-3">{crossShowLead(data)}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground text-left">
              <th className="font-normal pb-1.5">個股／題材</th>
              <th className="font-normal pb-1.5 px-3 whitespace-nowrap">本集</th>
              <th className="font-normal pb-1.5 whitespace-nowrap">其他節目</th>
              <th className="font-normal pb-1.5 pl-3 whitespace-nowrap">漲跌幅</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.subjects.map((subject) => {
              const row = comparisons.get(subjectKey(subject));
              const lean = row ? othersLean(row) : null;
              const isTicker = subject.mention_type === 'ticker';
              const name = subject.name || subject.ticker || subject.exposure_id;
              const href = isTicker && subject.ticker ? `/stock/${encodeURIComponent(subject.ticker)}`
                : subject.exposure_id && !isUmbrellaSector(subject.exposure_id) ? `/sector/${encodeURIComponent(subject.exposure_id)}` : null;
              const change = isTicker
                ? isRecentEpisode(episode) ? null : priceSinceMap.get(subject.ticker!.toUpperCase()) ?? null
                : sectorPerf.get(subject.exposure_id!)?.avg_change ?? null;
              return (
                <tr key={subjectKey(subject)}>
                  <td className="py-3 min-w-24">
                    <span className="text-2xs text-muted-foreground">{isTicker ? '個股' : '題材'}</span>
                    <div className="font-semibold text-foreground">
                      {href ? <Link to={href} className="hover:text-primary">{name}</Link> : name}
                      {isTicker && subject.name && subject.name !== subject.ticker && <span className="block text-xs text-muted-foreground font-normal">{subject.ticker}</span>}
                    </div>
                  </td>
                  <td className={`py-3 px-3 whitespace-nowrap font-semibold ${tone(subject.stance)}`}>{subject.stance ? stanceZh(subject.stance) : '—'}</td>
                  <td className="py-3" title={row ? othersCounts(row.others) : undefined}>
                    {!isMember ? <span className="text-xs text-muted-foreground whitespace-nowrap">會員限定</span>
                      : !row ? <span className="text-xs text-muted-foreground">{detailFailed ? '暫時無法載入' : detail ? '—' : '載入中…'}</span>
                        : row.others.shows === 0 ? <span className="text-xs text-muted-foreground">無其他節目提及</span>
                          : <>
                            <span className={`font-semibold whitespace-nowrap ${tone(lean)}`}>{lean ? stanceZh(lean) : '未有明確傾向'}</span>
                            {isOpposite(row) && <span className="ml-1 text-2xs text-primary">相反</span>}
                            <span className="block text-xs text-muted-foreground whitespace-nowrap">{row.others.shows} 個節目</span>
                          </>}
                  </td>
                  <td className="py-3 pl-3 whitespace-nowrap">
                    <ChangePct value={change} sizeClass="text-xs" skeleton={!isTicker && sectorPerfLoading} />
                    <span className="block text-2xs text-muted-foreground">{isTicker ? '播出至今' : '題材當日'}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!isMember && (
        <div className="mt-3 flex items-center gap-3 rounded-md border border-dashed border-border px-4 py-3">
          <Lock size={15} className="shrink-0 text-muted-foreground" />
          <p className="min-w-0 flex-1 text-xs leading-[1.5] text-muted-foreground">{CROSS_SHOW_LOCKED}</p>
          <Link to="/member" className="shrink-0 rounded-md bg-foreground px-3 py-1.5 text-xs font-semibold text-background hover:opacity-90 transition-opacity">升級</Link>
        </div>
      )}
      <p className="text-2xs text-muted-foreground/80 mt-3 leading-[1.6]">
        比較的是各節目公開說法之間的異同，不是對股價的判斷。
        <Link to="/methodology#stance" className="text-accent-info hover:underline">看多、看空怎麼判定</Link>
      </p>
    </section>
  );
};
