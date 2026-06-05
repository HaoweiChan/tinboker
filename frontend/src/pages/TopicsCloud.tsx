import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Flame, Hash, Layers3, TrendingUp } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { RailCard } from '@/components/redesign';
import { getTags } from '@/services/api/podcasts';
import type { Tag } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

const TOPIC_LIMIT = 48;

const topicTone = [
  { color: '#22f4e6', shadow: 'rgba(34, 244, 230, 0.34)' },
  { color: '#ff8a1f', shadow: 'rgba(255, 138, 31, 0.34)' },
  { color: '#ffe138', shadow: 'rgba(255, 225, 56, 0.32)' },
  { color: '#ff3d83', shadow: 'rgba(255, 61, 131, 0.3)' },
  { color: '#8fb0d8', shadow: 'rgba(143, 176, 216, 0.22)' },
  { color: '#f4f7fb', shadow: 'rgba(244, 247, 251, 0.2)' },
];

const topicAngles = [-2, 1, 0, -1, 2, -3, 1.5, -1.5, 0.5, -2.5, 2.5, -0.5];

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

const getTodayLabel = () => {
  const parts = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());

  const year = parts.find((part) => part.type === 'year')?.value ?? '';
  const month = parts.find((part) => part.type === 'month')?.value ?? '';
  const day = parts.find((part) => part.type === 'day')?.value ?? '';
  return [year, month, day].filter(Boolean).join(' / ');
};

export const TopicsCloud: React.FC = () => {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);

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
  const todayLabel = useMemo(() => getTodayLabel(), []);

  return (
    <>
      <SEO title="熱門話題雲" description="最近熱門的財經話題 — 大小依被提及的集數數量。" />
      <PageContent>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between mb-4">
          <div>
            <div className="text-[11px] uppercase font-mono tracking-[0.24em] text-accent-info mb-1">TinBoker Topics</div>
            <h1 className="text-[24px] sm:text-[28px] font-semibold tracking-[-0.02em]">熱門話題雲</h1>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <TrendingUp size={14} className="text-accent-info" />
            <span>依本月被提及集數放大顯示</span>
          </div>
        </div>

        {loading ? (
          <div className="bg-card border border-border rounded-md p-10 h-[420px] animate-pulse" />
        ) : sorted.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有話題資料。</div>
        ) : (
          <>
            <section className="relative overflow-hidden rounded-md border border-cyan-300/15 bg-[#060b16] px-4 py-5 shadow-[0_22px_70px_-48px_rgba(34,244,230,0.72)] sm:px-7 sm:py-6">
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 opacity-80"
                style={{
                  background:
                    'radial-gradient(circle at 22% 18%, rgba(34,244,230,0.16), transparent 26%), radial-gradient(circle at 78% 72%, rgba(255,138,31,0.13), transparent 30%), linear-gradient(180deg, rgba(8,13,28,0.38), rgba(1,4,12,0.96))',
                }}
              />
              <div aria-hidden="true" className="pointer-events-none absolute inset-4 rounded-md border border-cyan-200/10 shadow-[inset_0_0_44px_rgba(34,244,230,0.1)]" />

              <div className="relative z-10 mb-6 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.24em] text-cyan-300">
                    <Hash size={13} />
                    <span>Hot Hashtag Board</span>
                  </div>
                  <h2 className="mt-2 text-[20px] font-semibold tracking-[0.1em] text-white sm:text-[25px]">Podcast 財經熱門字雲</h2>
                </div>
                <div className="text-right font-mono text-[12px] tracking-[0.18em] text-slate-400">
                  <div>{todayLabel}</div>
                  <div className="mt-1 text-[10px] tracking-[0.16em] text-cyan-200/60">{totalMentions.toLocaleString('zh-TW')} 次提及</div>
                </div>
              </div>

              <div className="relative z-10 flex min-h-[360px] flex-wrap content-center items-center justify-center gap-x-3 gap-y-1.5 rounded-md bg-black/16 px-2 py-5 ring-1 ring-white/5 sm:min-h-[460px] sm:gap-x-5 sm:gap-y-2 sm:px-5">
                {posterTags.map((t, index) => {
                  const count = t.episode_count || 1;
                  const weight = Math.sqrt(count / maxCount);
                  const tone = topicTone[index % topicTone.length];
                  const rankBoost = index < 3 ? 1.14 : index < 8 ? 1.06 : 1;
                  const fontSize = Math.round((16 + weight * 54) * rankBoost);
                  const label = getTopicLabel(t.name);
                  const angle = topicAngles[index % topicAngles.length];

                  return (
                    <Link
                      key={t.id || t.name}
                      to={`/topics/${encodeURIComponent(t.name)}`}
                      aria-label={`${label}，${count} 集提及`}
                      className="group relative inline-flex max-w-full shrink-0 items-baseline rounded-[3px] px-1.5 py-0.5 font-black leading-none tracking-[0] text-white outline-none transition duration-200 hover:z-20 hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-cyan-200 sm:px-2"
                      style={{
                        color: tone.color,
                        fontSize,
                        opacity: 0.58 + weight * 0.42,
                        transform: `rotate(${angle}deg)`,
                        textShadow: `0 0 ${index < 8 ? 18 : 10}px ${tone.shadow}`,
                      }}
                    >
                      <span className="min-w-0 break-words">{label}</span>
                      {index < 14 && (
                        <span className="ml-1.5 rounded-full bg-white/8 px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none text-slate-200 opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                          {count}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>

              <div className="relative z-10 mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-4 text-[11px] text-slate-400">
                <div className="flex items-center gap-2">
                  <Layers3 size={14} className="text-cyan-300" />
                  <span>顏色與大小用來強調相對熱度，點擊任一詞可瀏覽相關集數。</span>
                </div>
                <span className="font-mono tracking-[0.14em]">TOP {posterTags.length}</span>
              </div>
            </section>

            <div className="mt-[18px] grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
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
