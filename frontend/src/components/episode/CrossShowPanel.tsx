import React from 'react';
import { Link } from 'react-router-dom';
import { getSentimentDisplay } from '@/lib/sentiment';
import { useAppStore } from '@/store/useAppStore';
import type { CrossShowResponse } from '@/validation/schemas';
import { RELATION_ZH, comparableRows, crossShowLead, othersLine, stanceZh } from '../../../shared/crossShow.js';

/** 其他節目怎麼看 — for each ticker this episode discussed, how many OTHER shows mentioned
 *  it in the 30 days before it aired, how those mentions split, and how this episode's
 *  stance sits against them. The one thing on the page a single show cannot tell you.
 *  Wording comes from shared/crossShow.js; the crawler body prints the same sentences. */
export const CrossShowPanel: React.FC<{ data: CrossShowResponse | null }> = ({ data }) => {
  const stockColorMode = useAppStore((s) => s.stockColorMode);
  const rows = comparableRows(data);
  if (!data || rows.length === 0) return null;

  return (
    <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-title">
      <h3 id="cross-show-title" className="heading-accent text-lg font-semibold text-foreground mb-2">其他節目怎麼看</h3>
      <p className="text-sm text-muted-foreground leading-[1.65] mb-3.5">{crossShowLead(data)}</p>
      <ul className="divide-y divide-border text-sm">
        {rows.map((r) => {
          const tone = getSentimentDisplay(r.stance ?? null, stockColorMode)?.toneClass ?? 'text-muted-foreground';
          return (
            <li key={r.ticker} className="py-2.5 grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5">
              <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold text-foreground hover:text-primary truncate">
                {r.name ? `${r.name}（${r.ticker}）` : r.ticker}
              </Link>
              <span className="text-xs text-foreground text-right whitespace-nowrap">{RELATION_ZH[r.relation]}</span>
              <span className="col-span-2 text-xs text-muted-foreground">
                本集<span className={`font-semibold ${tone}`}>{stanceZh(r.stance)}</span> · 其他 {othersLine(r.others)}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-2xs text-muted-foreground/80 mt-3 leading-[1.6]">
        比較的是各節目公開說法之間的異同，不是對股價的判斷。
        <Link to="/methodology#stance" className="text-accent-info hover:underline">看多、看空怎麼判定</Link>
      </p>
    </section>
  );
};
