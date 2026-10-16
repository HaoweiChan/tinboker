import React, { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Lock } from 'lucide-react';
import { getSentimentDisplay } from '@/lib/sentiment';
import { SectorExposureList } from '@/components/episode/SectorExposureList';
import type { Episode, SectorBoardItem, SectorExposure } from '@/services/api/podcasts';
import { isRecentEpisode } from '@/hooks/useStockPriceSinceMap';
import { useAppStore } from '@/store/useAppStore';
import { ChangePct } from '@/components/topics/ChangePct';
import type { useCrossShowPanelData } from '@/hooks/useCrossShowPanelData';
import type { CrossShowResponse } from '@/validation/schemas';
import { isOpposite, othersCounts, othersLean, stanceZh } from '../../../shared/crossShow.js';

type Subject = CrossShowResponse['subjects'][number];
// Rows of each kind a non-member sees unblurred when the public route previews none.
const FREE_VISIBLE = 2;
// Rows each list shows before 「顯示全部」, and blurred rows a non-member gets as a teaser.
const LIST_LIMIT = 5;
const BLURRED_TEASE = 3;

/** A few blurred, inert rows under 「升級會員才看得到」 and a button to the member page. */
const LockedTeaser: React.FC<{ detail: string; children: React.ReactNode }> = ({ detail, children }) => (
  <div className="relative mt-1.5">
    <div inert aria-hidden className="blur-[3px] select-none">{children}</div>
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 rounded-md bg-background/40 px-4 text-center">
      <div>
        <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-foreground">
          <Lock size={14} className="shrink-0" />升級會員才看得到
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>
      </div>
      <Link to="/member" className="rounded-md bg-foreground px-4 py-2 text-xs font-semibold text-background hover:opacity-90 transition-opacity">
        升級會員
      </Link>
    </div>
  </div>
);

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
  panelData: ReturnType<typeof useCrossShowPanelData>;
  data: CrossShowResponse | null;
  sectorPerf: Map<string, SectorBoardItem>;
  sectorPerfLoading: boolean;
}

/** 提及個股 + 提及題材, both from this episode's content_mentions. Other shows' per-subject
 *  comparisons are members-only; the themes keep the icon rows of SectorExposureList. */
export const CrossShowPanel: React.FC<Props> = ({ episode, data, sectorPerf, sectorPerfLoading, panelData }) => {
  const stockColorMode = useAppStore((s) => s.stockColorMode);
  const titleId = useId();
  const { isMember, detail, detailFailed, priceSinceMap } = panelData;
  // Members get every comparison; everyone else gets the public route's FREE_PREVIEW_ROWS.
  const comparisons = new Map((isMember ? detail?.rows ?? [] : data?.rows ?? []).map((r) => [subjectKey(r), r]));

  const [showAllStocks, setShowAllStocks] = useState(false);
  const [showAllThemes, setShowAllThemes] = useState(false);

  if (!data?.subjects.length || data.episode_id !== episode.id) return null;
  const tone = (stance: Parameters<typeof getSentimentDisplay>[0] | undefined) => getSentimentDisplay(stance ?? null, stockColorMode)?.toneClass ?? 'text-muted-foreground';
  const allTickers = data.subjects.filter((s) => s.mention_type === 'ticker' && s.ticker);
  // Non-members: the previewed stocks lead (or the first two when nothing was compared);
  // the rest render blurred, with placeholder comparison text, under the upgrade prompt.
  const allThemes = data.subjects.filter((s) => s.mention_type === 'sector' && s.exposure_id);
  // Per kind: the public route's preview rows, or the first FREE_VISIBLE when it has none.
  const previewOf = (subjects: Subject[]) => {
    const keys = new Set(subjects.map(subjectKey));
    const previewed = data.rows.map(subjectKey).filter((k) => keys.has(k));
    return previewed.length ? previewed : subjects.slice(0, FREE_VISIBLE).map(subjectKey);
  };
  const previewKeys = new Set(isMember ? [] : [...previewOf(allTickers), ...previewOf(allThemes)]);
  const isBlurred = (subject: Subject) => !isMember && !previewKeys.has(subjectKey(subject));
  const previewFirst = (subjects: Subject[]) => isMember ? subjects
    : [...subjects.filter((t) => !isBlurred(t)), ...subjects.filter(isBlurred)];
  const tickers = previewFirst(allTickers);
  const themes = previewFirst(allThemes);
  // The theme rows reuse the episode's own exposure records (icon, constituents) for the
  // themes content_mentions lists; a theme missing from them still gets a bare row.
  const exposureById = new Map((episode.sector_exposures ?? []).map((e) => [e.exposure_id, e]));
  const themeExposures: SectorExposure[] = themes.map((t) => exposureById.get(t.exposure_id!) ?? {
    exposure_id: t.exposure_id!, exposure_type: 'theme', display_name: t.name || t.exposure_id!,
    mention_text: '', confidence: 0, resolved_tickers: [], total_matches: 0,
  });
  const themeNotes = new Map(themes.flatMap((t) => {
    if (isBlurred(t)) return [[t.exposure_id!, '5 個節目也談到'] as const];  // placeholder under the blur
    const row = comparisons.get(subjectKey(t));
    return row && row.others.shows > 0 ? [[t.exposure_id!, `${row.others.shows} 個節目也談到`] as const] : [];
  }));

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
        className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-2"
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
  const clearThemes = themeExposures.filter((_, i) => !isBlurred(themes[i]));
  const hiddenThemes = themeExposures.filter((_, i) => isBlurred(themes[i]));

  return (
    <>
      {tickers.length > 0 && (
        <section className="bg-card border border-border rounded-md p-5 sm:p-6 xl:p-3 mb-3.5" aria-labelledby={`${titleId}-stocks`}>
          <h3 id={`${titleId}-stocks`} className="heading-accent text-lg font-semibold text-foreground mb-3">提及個股</h3>
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
                <LockedTeaser detail={`另外 ${hiddenStocks.length} 檔與其他節目的看法對照`}>
                  <div className="flex flex-col gap-1.5">{hiddenStocks.slice(0, BLURRED_TEASE).map(renderStockRow)}</div>
                </LockedTeaser>
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
        <section className="bg-card border border-border rounded-md p-5 sm:p-6 xl:p-3 mb-3.5" aria-labelledby={`${titleId}-themes`}>
          <h3 id={`${titleId}-themes`} className="heading-accent text-lg font-semibold text-foreground mb-3.5">提及題材</h3>
          {!isMember ? (
            <>
              <SectorExposureList exposures={clearThemes} perfMap={sectorPerf} loading={sectorPerfLoading} notes={themeNotes} />
              {hiddenThemes.length > 0 && (
                <LockedTeaser detail={`另外 ${hiddenThemes.length} 個題材在其他節目的討論`}>
                  <SectorExposureList exposures={hiddenThemes.slice(0, BLURRED_TEASE)} perfMap={sectorPerf} loading={sectorPerfLoading} notes={themeNotes} />
                </LockedTeaser>
              )}
            </>
          ) : (
            <>
              <SectorExposureList exposures={shownThemes} perfMap={sectorPerf} loading={sectorPerfLoading} notes={themeNotes} />
              {themeExposures.length > LIST_LIMIT && (
                <ShowAllToggle open={showAllThemes} onToggle={() => setShowAllThemes((v) => !v)} label={`顯示全部 ${themeExposures.length} 個題材`} />
              )}
            </>
          )}
        </section>
      )}
    </>
  );
};
