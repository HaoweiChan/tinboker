import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Lock } from 'lucide-react';
import { getSentimentDisplay } from '@/lib/sentiment';
import { SectorExposureList } from '@/components/episode/SectorExposureList';
import { getEpisodeCrossShow } from '@/services/api/mentions';
import type { Episode, SectorBoardItem, SectorExposure } from '@/services/api/podcasts';
import { useStockPriceSinceMap, isRecentEpisode } from '@/hooks/useStockPriceSinceMap';
import { useAppStore } from '@/store/useAppStore';
import { ChangePct } from '@/components/topics/ChangePct';
import type { CrossShowResponse } from '@/validation/schemas';
import { crossShowLead, isOpposite, othersCounts, othersLean, stanceZh } from '../../../shared/crossShow.js';

type Subject = CrossShowResponse['subjects'][number];
// Stock rows a non-member sees unblurred when the public route has no preview rows.
const FREE_VISIBLE = 2;
// Rows each list shows before 「顯示全部」, and blurred rows a non-member gets as a teaser.
const LIST_LIMIT = 5;
const BLURRED_TEASE = 3;

const ShowAllToggle: React.FC<{ open: boolean; onToggle: () => void; label: string }> = ({ open, onToggle, label }) => (
  <button
    type="button"
    onClick={onToggle}
    aria-expanded={open}
    className="mt-2 flex w-full items-center justify-center gap-1 rounded-md py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
  >
    {open ? '收合' : label}
    <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
  </button>
);
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
  // Members get every comparison; everyone else gets the public route's FREE_PREVIEW_ROWS.
  const comparisons = new Map((isMember ? detail?.rows ?? [] : data?.rows ?? []).map((r) => [subjectKey(r), r]));

  const [showAllStocks, setShowAllStocks] = useState(false);
  const [showAllThemes, setShowAllThemes] = useState(false);

  if (!data?.subjects.length || data.episode_id !== episode.id) return null;
  const tone = (stance: Parameters<typeof getSentimentDisplay>[0] | undefined) => getSentimentDisplay(stance ?? null, stockColorMode)?.toneClass ?? 'text-muted-foreground';
  const allTickers = data.subjects.filter((s) => s.mention_type === 'ticker' && s.ticker);
  // Non-members: the previewed stocks lead (or the first two when nothing was compared);
  // the rest render blurred, with placeholder comparison text, under the upgrade prompt.
  const previewKeys = new Set(isMember ? [] : (data.rows.length ? data.rows.map(subjectKey) : allTickers.slice(0, FREE_VISIBLE).map(subjectKey)));
  const tickers = isMember ? allTickers
    : [...allTickers.filter((t) => previewKeys.has(subjectKey(t))), ...allTickers.filter((t) => !previewKeys.has(subjectKey(t)))];
  const isBlurred = (subject: Subject) => !isMember && !previewKeys.has(subjectKey(subject));
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

  const clearStocks = tickers.filter((t) => !isBlurred(t));
  const hiddenStocks = tickers.filter((t) => isBlurred(t));
  const renderStockRow = (subject: Subject) => {
    const row = comparisons.get(subjectKey(subject));
    const lean = row ? othersLean(row) : null;
    const ticker = subject.ticker!;
    const change = isRecentEpisode(episode) ? null : priceSinceMap.get(ticker.toUpperCase()) ?? null;
    const blurred = isBlurred(subject);
    const others = blurred ? <span>其他 5 個節目 看多</span>
      : !isMember && !row ? <span>其他節目沒有提到</span>
      : !row ? <span>{detailFailed ? '其他節目：暫時無法載入' : detail ? '' : '其他節目：載入中…'}</span>
        : row.others.shows === 0 ? <span>其他節目沒有提到</span>
          : <span>
            其他 {row.others.shows} 個節目
            <span className={`ml-1 font-semibold ${tone(lean)}`}>{lean ? stanceZh(lean) : '看法分歧'}</span>
            {isOpposite(row) && <span className="ml-1 text-primary">相反</span>}
          </span>;
    return (
      <div
        key={subjectKey(subject)}
        aria-hidden={blurred || undefined}
        className={`flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-2 ${blurred ? 'blur-[3px] select-none pointer-events-none' : ''}`}
      >
        <div className="flex-1 min-w-0">
          <Link to={`/stock/${encodeURIComponent(ticker)}`} className="block text-sm font-medium hover:underline truncate leading-snug">
            {subject.name && subject.name !== ticker ? <>{subject.name}<span className="ml-1.5 font-mono text-2xs text-muted-foreground">{ticker}</span></> : ticker}
          </Link>
          {/* Never truncate: the stance at the end of this line is the point of it. */}
          <span className="block text-2xs text-muted-foreground" title={row ? othersCounts(row.others) : undefined}>{others}</span>
        </div>
        <span className={`w-10 shrink-0 text-center text-xs font-semibold ${tone(subject.stance)}`}>{subject.stance ? stanceZh(subject.stance) : '—'}</span>
        {/* ChangePct is a flex box, so text-right alone left it left-aligned. */}
        <span className="w-16 shrink-0 flex justify-end"><ChangePct value={change} sizeClass="text-xs" /></span>
        <span className="w-[18px] shrink-0 -mr-0.5" aria-hidden />
      </div>
    );
  };
  const shownThemes = showAllThemes ? themeExposures : themeExposures.slice(0, LIST_LIMIT);

  return (
    <>
      {tickers.length > 0 && (
        <section className="bg-card border border-border rounded-md p-5 sm:p-6 mb-3.5" aria-labelledby="cross-show-title">
          <h3 id="cross-show-title" className="heading-accent text-lg font-semibold text-foreground mb-2">提及個股</h3>
          {lead}
          {/* Same row shape as 提及題材 (SectorExposureList): name + one muted line on the
              left, then fixed-width stance, change and a chevron-sized gap, so the two
              sections' change columns line up. */}
          <div className="flex items-center gap-2 px-2.5 pb-1 text-2xs text-muted-foreground">
            <span className="flex-1">個股</span>
            <span className="w-10 text-center">本集</span>
            <span className="w-16 text-right">播出至今</span>
            <span className="w-[18px] -mr-0.5" aria-hidden />
          </div>
          {!isMember ? (
            <>
              <div className="flex flex-col gap-1.5">{clearStocks.map(renderStockRow)}</div>
              {hiddenStocks.length > 0 && (
                // A taste of the member table: a few blurred rows under the upgrade prompt.
                <div className="relative mt-1.5">
                  <div inert className="flex flex-col gap-1.5">{hiddenStocks.slice(0, BLURRED_TEASE).map(renderStockRow)}</div>
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 rounded-md bg-background/40 px-4 text-center">
                    <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                      <Lock size={14} className="shrink-0" />升級會員才看得到另外 {hiddenStocks.length} 檔的節目比較
                    </p>
                    <Link to="/member" className="rounded-md bg-foreground px-4 py-2 text-xs font-semibold text-background hover:opacity-90 transition-opacity">
                      升級會員
                    </Link>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">{(showAllStocks ? tickers : tickers.slice(0, LIST_LIMIT)).map(renderStockRow)}</div>
              {tickers.length > LIST_LIMIT && (
                <ShowAllToggle open={showAllStocks} onToggle={() => setShowAllStocks((v) => !v)} label={`顯示全部 ${tickers.length} 檔`} />
              )}
            </>
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
          <SectorExposureList exposures={shownThemes} perfMap={sectorPerf} loading={sectorPerfLoading} notes={themeNotes} />
          {themeExposures.length > LIST_LIMIT && (
            <ShowAllToggle open={showAllThemes} onToggle={() => setShowAllThemes((v) => !v)} label={`顯示全部 ${themeExposures.length} 個題材`} />
          )}
        </section>
      )}
    </>
  );
};
