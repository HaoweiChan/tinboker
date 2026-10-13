import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { getSentimentDisplay } from '@/lib/sentiment';
import { getEpisodeCrossShow } from '@/services/api/mentions';
import { useAppStore } from '@/store/useAppStore';
import type { CrossShowResponse } from '@/validation/schemas';
import { CROSS_SHOW_LOCKED, comparableRows, crossShowLead, isOpposite, othersCounts, othersLean, stanceZh } from '../../../shared/crossShow.js';

/** 其他節目怎麼看 — for each ticker this episode discussed, its stance next to the lean
 *  of the OTHER shows in the 30 days before it aired. Everyone gets the one-sentence
 *  lead (`data`, the public counts); the per-ticker table is members-only and fetched
 *  here from the member route, so a non-member's page never holds the rows.
 *  Wording comes from shared/crossShow.js; the crawler body prints the same lead. */
export const CrossShowPanel: React.FC<{ episodeId: string; data: CrossShowResponse | null }> = ({ episodeId, data }) => {
  const stockColorMode = useAppStore((s) => s.stockColorMode);
  const isMember = useAppStore((s) => !!s.user?.is_member);
  const [detail, setDetail] = useState<CrossShowResponse | null>(null);
  useEffect(() => {
    setDetail(null);
    if (!isMember) return;
    let alive = true;
    getEpisodeCrossShow(episodeId, true).then((res) => { if (alive) setDetail(res); }).catch(() => {});
    return () => { alive = false; };
  }, [episodeId, isMember]);

  if (!data || data.compared === 0) return null;
  const tone = (stance: Parameters<typeof getSentimentDisplay>[0] | undefined) => getSentimentDisplay(stance ?? null, stockColorMode)?.toneClass ?? 'text-muted-foreground';

  return (
    <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-title">
      <h3 id="cross-show-title" className="heading-accent text-lg font-semibold text-foreground mb-2">其他節目怎麼看</h3>
      <p className="text-sm text-muted-foreground leading-[1.65] mb-3">{crossShowLead(data)}</p>
      {!isMember ? (
        <div className="flex items-center gap-3 rounded-md border border-dashed border-border px-4 py-3">
          <Lock size={15} className="shrink-0 text-muted-foreground" />
          <p className="min-w-0 flex-1 text-xs leading-[1.5] text-muted-foreground">{CROSS_SHOW_LOCKED}</p>
          <Link to="/member" className="shrink-0 rounded-md bg-foreground px-3 py-1.5 text-xs font-semibold text-background hover:opacity-90 transition-opacity">
            升級
          </Link>
        </div>
      ) : detail && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground text-left">
              <th className="font-normal pb-1.5">個股</th>
              <th className="font-normal pb-1.5 px-3 whitespace-nowrap">本集</th>
              <th className="font-normal pb-1.5 whitespace-nowrap">其他節目</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {comparableRows(detail).map((r) => {
              const lean = othersLean(r);
              return (
                <tr key={r.ticker} title={othersCounts(r.others)}>
                  {/* max-w-0 + w-full: the name column takes the slack and truncates inside it. */}
                  <td className="py-2 w-full max-w-0">
                    <span className="flex items-baseline gap-2">
                      <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold text-foreground hover:text-primary truncate">
                        {r.name ? `${r.name}（${r.ticker}）` : r.ticker}
                      </Link>
                      {isOpposite(r) && <span className="shrink-0 text-2xs font-semibold text-primary border border-primary/50 rounded-sm px-1">相反</span>}
                    </span>
                  </td>
                  <td className={`py-2 px-3 whitespace-nowrap font-semibold ${tone(r.stance)}`}>{stanceZh(r.stance)}</td>
                  <td className="py-2 whitespace-nowrap">
                    <span className={`font-semibold ${tone(lean)}`}>{lean ? stanceZh(lean) : '分歧'}</span>
                    <span className="text-xs text-muted-foreground"> · {r.others.shows} 個節目</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="text-2xs text-muted-foreground/80 mt-3 leading-[1.6]">
        比較的是各節目公開說法之間的異同，不是對股價的判斷。
        <Link to="/methodology#stance" className="text-accent-info hover:underline">看多、看空怎麼判定</Link>
      </p>
    </section>
  );
};
