import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Flame, Layers3 } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { RailCard } from '@/components/redesign';
import { getTags } from '@/services/api/podcasts';
import type { Tag } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

// ---------------------------------------------------------------------------
// Word-cloud animation styles — injected once, tree-shakable in production.
// Reduced-motion: stagger and scale transitions are both disabled by the media
// query so the guard is applied at the CSS layer, not just component logic.
// ---------------------------------------------------------------------------
const CLOUD_STYLES = `
@keyframes tb-word-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: var(--tb-word-opacity); transform: translateY(0); }
}
.tb-word {
  animation: tb-word-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: var(--tb-word-delay, 0ms);
  transition: opacity 150ms ease, transform 150ms ease;
}
.tb-word:hover,
.tb-word:focus-visible {
  opacity: 1 !important;
  transform: scale(1.07);
}
@media (prefers-reduced-motion: reduce) {
  .tb-word {
    animation: none;
    opacity: var(--tb-word-opacity);
  }
  .tb-word:hover,
  .tb-word:focus-visible {
    transform: none;
  }
}
`;

let _stylesInjected = false;
function injectCloudStyles() {
  if (_stylesInjected || typeof document === 'undefined') return;
  const el = document.createElement('style');
  el.textContent = CLOUD_STYLES;
  document.head.appendChild(el);
  _stylesInjected = true;
}

const TOPIC_LIMIT = 48;

const topicLabels: Record<string, string> = {
  ai: 'AI',
  ai_chip: 'AI 晶片',
  advanced_packaging: '先進封裝',
  bitcoin: '比特幣',
  capital_expenditure: '資本支出',
  centralbanks: '央行',
  cryptocurrency: '加密貨幣',
  datacenters: '資料中心',
  demographics: '人口趨勢',
  digitalassets: '數位資產',
  earningsreport: '財報',
  electric_vehicles: '電動車',
  electricvehicles: '電動車',
  etf: 'ETF',
  ev: '電動車',
  federalreserve: '聯準會',
  financialregulation: '金融監管',
  fiscalpolicy: '財政政策',
  fixedincome: '固定收益',
  interestrates: '利率',
  interestratepolicy: '利率政策',
  japanmarket: '日本市場',
  labormarket: '就業市場',
  low_earth_orbit_satellite: '低軌衛星',
  marketnarratives: '市場敘事',
  media_industry: '媒體產業',
  mergers_and_acquisitions: '併購',
  monetarypolicy: '貨幣政策',
  powersupply: '電力供應',
  privatemarkets: '私募市場',
  semiconductor: '半導體',
  streaming_services: '串流服務',
  supply_chain: '供應鏈',
  taiwaneconomy: '台灣經濟',
  trade_war: '貿易戰',
  us_stocks: '美股',
  useconomy: '美國經濟',
  usstockmarket: '美股市場',
  ustreasuries: '美債',
  valuation: '估值',
};

const getTopicKey = (name: string) => name.trim().replace(/^#/, '').toLowerCase();

const getTopicLabel = (name: string) => {
  const key = getTopicKey(name);
  return topicLabels[key] ?? name.replace(/^#/, '').replace(/[_-]/g, ' ');
};

export const TopicsCloud: React.FC = () => {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);

  // Inject keyframe styles once on mount
  useEffect(() => { injectCloudStyles(); }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const res = await fetchWithFallback(() => getTags(), { tags: [] }, 'getTags:cloud').catch(() => ({ tags: [] as Tag[] }));
      if (!alive) return;
      setTags(Array.isArray(res?.tags) ? res.tags : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const { sorted, maxCount } = useMemo(() => {
    const s = [...tags].sort((a, b) => (b.episode_count || 0) - (a.episode_count || 0));
    return { sorted: s, maxCount: s[0]?.episode_count || 1 };
  }, [tags]);

  const totalMentions = useMemo(() => sorted.reduce((sum, tag) => sum + (tag.episode_count || 0), 0), [sorted]);
  const posterTags = sorted.slice(0, TOPIC_LIMIT);

  return (
    <>
      <SEO title="熱門話題雲" description="最近熱門的財經話題 — 大小依被提及的集數數量。" />
      <PageContent>
        {/* Page header — matches PodcasterIndex / HomeFeed pattern */}
        <div className="flex items-baseline justify-between mb-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">熱門話題雲</h1>
          {!loading && (
            <div className="text-[12px] text-muted-foreground font-mono tabular-nums">
              {totalMentions.toLocaleString('zh-TW')} 次提及
            </div>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground max-w-[60ch] mb-4">
          字體大小依集數提及數量放大；點擊任一話題可瀏覽相關集數。
        </p>

        {loading ? (
          <div className="bg-card border border-border rounded-md p-10 h-[420px] animate-pulse" />
        ) : sorted.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有話題資料。</div>
        ) : (
          <>
            {/* Word cloud */}
            <section
              className="bg-card border border-border rounded-md px-5 py-6 sm:px-7 sm:py-8 relative overflow-hidden"
              style={{
                // Faint radial vignette: a hint of the accent color pools at the
                // centre, giving the cloud a spotlight feel without neon.
                // Using hsl values that match the dark-mode card + accent-info tokens.
                backgroundImage:
                  'radial-gradient(ellipse 70% 55% at 50% 48%, hsl(222 55% 22% / 0.35) 0%, transparent 72%), ' +
                  'radial-gradient(ellipse 100% 80% at 50% 50%, hsl(222 21% 11% / 0) 60%, hsl(222 22% 7% / 0.45) 100%)',
              }}
            >
              <div className="flex flex-wrap content-center items-center justify-center gap-x-4 gap-y-2 min-h-[340px] sm:min-h-[440px]">
                {posterTags.map((t, index) => {
                  const count = t.episode_count || 1;
                  // Perceptually-tuned power scale:
                  //   rank 0 → ~44px (commands the eye)
                  //   rank ~10 → ~22px (clear secondary tier)
                  //   tail → ~12px (legible but clearly background)
                  const ratio = count / maxCount;
                  const fontSize = Math.round(12 + Math.pow(ratio, 0.38) * 32);

                  // Font weight tracks rank: top words feel heavy, tail stays regular
                  const fontWeight = ratio > 0.6 ? 700 : ratio > 0.3 ? 600 : 500;

                  // Opacity: hot topics are fully opaque, tail fades to 40%
                  const opacity = 0.40 + ratio * 0.60;

                  // Color temperature via CSS custom property:
                  //   top words → accent-info (calm blue #5b8dff in dark)
                  //   mid → foreground at reduced opacity (handled by opacity above)
                  //   tail → muted-foreground colour
                  // We express this as a blend between two token values using
                  // the `color-mix` approach via inline class selection.
                  const colorClass =
                    ratio > 0.55
                      ? 'text-accent-info'
                      : ratio > 0.20
                      ? 'text-foreground'
                      : 'text-muted-foreground';

                  const label = getTopicLabel(t.name);

                  // Stagger: spread first 24 words over 280ms; rest appear instantly
                  const delayMs = index < 24 ? Math.round(index * 12) : 0;

                  return (
                    <Link
                      key={t.id || t.name}
                      to={`/topics/${encodeURIComponent(t.name)}`}
                      aria-label={`${label}，${count} 集提及`}
                      className={`tb-word group relative inline-flex items-baseline gap-1 rounded px-1 py-0.5 leading-snug outline-none focus-visible:ring-2 focus-visible:ring-accent-info ${colorClass}`}
                      style={{
                        fontSize,
                        fontWeight,
                        '--tb-word-opacity': opacity,
                        '--tb-word-delay': `${delayMs}ms`,
                      } as React.CSSProperties}
                    >
                      <span>{label}</span>
                      {/* Count badge — visible on hover/focus */}
                      <span className="font-mono text-[10px] text-muted-foreground opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
                        {count}
                      </span>
                    </Link>
                  );
                })}
              </div>

              <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4 text-[11px] text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Layers3 size={13} />
                  <span>大小依集數提及數量；點擊話題詞可進入相關集數。</span>
                </div>
                <span className="font-mono tabular-nums">TOP {posterTags.length}</span>
              </div>
            </section>

            <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
              {/* Top-10 ranked list */}
              <RailCard
                title={
                  <span className="inline-flex items-center gap-2">
                    <Flame size={15} className="text-accent-info" />
                    熱門排行
                  </span>
                }
                sub="Top 10"
                className="p-4 sm:p-5"
              >
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {sorted.slice(0, 10).map((t, index) => {
                    const count = t.episode_count || 0;
                    const width = `${Math.max(8, Math.round((count / maxCount) * 100))}%`;
                    return (
                      <Link
                        key={`rank-${t.id || t.name}`}
                        to={`/topics/${encodeURIComponent(t.name)}`}
                        className="group rounded-md border border-border bg-background/40 px-3 py-2.5 transition hover:border-accent-info/50 hover:bg-accent-info-soft/30"
                      >
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="min-w-0 text-[13px] font-semibold">
                            <span className="mr-2 font-mono text-[11px] text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
                            <span className="truncate align-bottom">#{getTopicLabel(t.name)}</span>
                          </div>
                          <div className="shrink-0 font-mono text-[11px] text-muted-foreground">{count} 集</div>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-accent-info transition-[width] duration-500" style={{ width }} />
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </RailCard>

              {/* Summary stats */}
              <RailCard title="本月摘要" sub={`${sorted.length} 個話題`} className="p-4 sm:p-5">
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-md bg-muted/70 p-3">
                    <div className="font-mono text-[18px] font-semibold">{sorted.length}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">追蹤話題</div>
                  </div>
                  <div className="rounded-md bg-muted/70 p-3">
                    <div className="font-mono text-[18px] font-semibold">{totalMentions.toLocaleString('zh-TW')}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">總提及</div>
                  </div>
                  <div className="rounded-md bg-muted/70 p-3">
                    <div className="font-mono text-[18px] font-semibold">{maxCount.toLocaleString('zh-TW')}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">最高熱度</div>
                  </div>
                </div>
                <div className="mt-3 rounded-md border border-border bg-background/40 p-3 text-[12px] leading-[1.65] text-muted-foreground">
                  最大字代表最多集數提及；排行條保留精確數字，方便在視覺瀏覽和快速比較之間切換。
                </div>
              </RailCard>
            </div>
          </>
        )}
      </PageContent>
    </>
  );
};
