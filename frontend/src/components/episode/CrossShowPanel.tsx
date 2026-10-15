import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { getSentimentDisplay } from '@/lib/sentiment';
import { SectorExposureList } from '@/components/episode/SectorExposureList';
import { getEpisodeCrossShow } from '@/services/api/mentions';
import type { Episode, SectorBoardItem, SectorExposure } from '@/services/api/podcasts';
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

/** 提及個股 + 提及題材, both from this episode's content_mentions. Other shows' per-subject
 *  comparisons are members-only; the themes keep the icon rows of SectorExposureList. */
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
  const tickers = data.subjects.filter((s) => s.mention_type === 'ticker' && s.ticker);
  const themes = data.subjects.filter((s) => s.mention_type === 'sector' && s.exposure_id);
  // The theme rows reuse the episode's own exposure records (icon, constituents) for the
  // themes content_mentions lists; a theme missing from them still gets a bare row.
  const exposureById = new Map((episode.sector_exposures ?? []).map((e) => [e.exposure_id, e]));
  const themeExposures: SectorExposure[] = themes.map((t) => exposureById.get(t.exposure_id!) ?? {
    exposure_id: t.exposure_id!, exposure_type: 'theme', display_name: t.name || t.exposure_id!,
    mention_text: '', confidence: 0, resolved_tickers: [], total_matches: 0,
  });
  const themeNotes = new Map(themes.flatMap((t) => {
    const row = comparisons.get(subjectKey(t));
    return row && row.others.shows > 0 ? [[t.exposure_id!, `${row.others.shows} 個節目也談到`] as const] : [];
  }));
  const lead = <p className="text-sm text-muted-foreground leading-[1.65] mb-3">{crossShowLead(data)}</p>;

  return (
    <>
      {tickers.length > 0 && (
        <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-title">
          <h3 id="cross-show-title" className="heading-accent text-lg font-semibold text-foreground mb-2">提及個股</h3>
          {lead}
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground text-left">
                <th className="font-normal pb-1.5">個股</th>
                <th className="font-normal pb-1.5 px-3 whitespace-nowrap">本集</th>
                <th className="font-normal pb-1.5 whitespace-nowrap">其他節目</th>
                <th className="hidden sm:table-cell font-normal pb-1.5 pl-3 whitespace-nowrap">播出至今</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tickers.map((subject) => {
                const row = comparisons.get(subjectKey(subject));
                const lean = row ? othersLean(row) : null;
                const ticker = subject.ticker!;
                const change = isRecentEpisode(episode) ? null : priceSinceMap.get(ticker.toUpperCase()) ?? null;
                return (
                  <tr key={subjectKey(subject)}>
                    <td className="py-3 min-w-24">
                      <div className="font-semibold text-foreground">
                        <Link to={`/stock/${encodeURIComponent(ticker)}`} className="hover:text-primary">{subject.name || ticker}</Link>
                        {subject.name && subject.name !== ticker && <span className="block text-xs text-muted-foreground font-normal">{ticker}</span>}
                      </div>
                      {/* Phones: four columns overflow 375px, so the change rides under the name. */}
                      <span className="sm:hidden flex items-baseline gap-1 mt-0.5">
                        <ChangePct value={change} sizeClass="text-xs" />
                        <span className="text-2xs text-muted-foreground">播出至今</span>
                      </span>
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
                    <td className="hidden sm:table-cell py-3 pl-3 whitespace-nowrap"><ChangePct value={change} sizeClass="text-xs" /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
      )}
      {themeExposures.length > 0 && (
        <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-themes-title">
          <h3 id="cross-show-themes-title" className="heading-accent text-lg font-semibold text-foreground mb-3.5">提及題材</h3>
          {tickers.length === 0 && lead}
          <SectorExposureList exposures={themeExposures} perfMap={sectorPerf} loading={sectorPerfLoading} notes={themeNotes} />
        </section>
      )}
    </>
  );
};
