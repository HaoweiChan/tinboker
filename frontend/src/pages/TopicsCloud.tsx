import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Hash, TrendingUp, TrendingDown, Minus, ChevronRight, Flame, BarChart3 } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { RailCard } from '@/components/redesign';
import { getTrendingTags, type TrendingTag, type EpisodePreview } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

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

const getTopicLabel = (name: string) => {
  const key = name.trim().replace(/^#/, '').toLowerCase();
  return topicLabels[key] ?? name.replace(/^#/, '').replace(/[_-]/g, ' ');
};

function timeAgo(ms: number | null | undefined): string {
  if (!ms) return '';
  const hours = Math.floor((Date.now() - ms) / 3_600_000);
  if (hours < 1) return '剛剛';
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return `${Math.floor(days / 7)}w`;
}

// ── Sparkline SVG ──────────────────────────────────────────────────

let sparkId = 0;

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
}

function Sparkline({ data, width = 120, height = 36, className }: SparklineProps) {
  const [id] = useState(() => `sf${++sparkId}`);
  if (!data.length || data.every((v) => v === 0)) {
    return (
      <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`}>
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke="currentColor" strokeOpacity="0.15" strokeDasharray="3 3" />
      </svg>
    );
  }
  const reversed = [...data].reverse();
  const max = Math.max(...reversed, 1);
  const padY = 4;
  const padX = 2;
  const usableW = width - padX * 2;
  const usableH = height - padY * 2;
  const step = usableW / Math.max(reversed.length - 1, 1);

  const points = reversed.map((v, i) => ({
    x: padX + i * step,
    y: padY + usableH - (v / max) * usableH,
  }));

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const area = `${line} L${points[points.length - 1].x.toFixed(1)},${height} L${points[0].x.toFixed(1)},${height} Z`;
  const trend = reversed[reversed.length - 1] - reversed[Math.max(reversed.length - 3, 0)];
  const color = trend > 0 ? 'hsl(var(--sentiment-bull))' : trend < 0 ? 'hsl(var(--sentiment-bear))' : 'hsl(var(--accent-info))';

  return (
    <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dot on the latest point */}
      <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={color} />
    </svg>
  );
}

// ── Trend badge ────────────────────────────────────────────────────

function TrendBadge({ weekly }: { weekly: number[] }) {
  const thisWeek = weekly[0] ?? 0;
  const lastWeek = weekly[1] ?? 0;
  if (thisWeek === 0 && lastWeek === 0) return null;
  const diff = thisWeek - lastWeek;
  const pct = lastWeek > 0 ? Math.round((diff / lastWeek) * 100) : diff > 0 ? 100 : 0;
  if (diff === 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground font-mono">
        <Minus size={11} /> 持平
      </span>
    );
  }
  const up = diff > 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-mono ${up ? 'text-sentiment-bull' : 'text-sentiment-bear'}`}>
      {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {up ? '+' : ''}{pct}%
    </span>
  );
}

// ── Episode preview row ────────────────────────────────────────────

function EpisodeRow({ ep }: { ep: EpisodePreview }) {
  const linkTo = `/episode/${ep.podcast_name}/${ep.id}`;
  return (
    <Link to={linkTo} className="group flex items-start gap-2.5 py-2 first:pt-0 last:pb-0 transition-colors hover:bg-muted/30 rounded px-1.5 -mx-1.5">
      <div className="mt-0.5 w-5 h-5 rounded bg-muted grid place-items-center text-[10px] text-muted-foreground shrink-0">
        {(ep.podcast_name || 'P').charAt(0)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[12px] leading-[1.5] text-foreground truncate group-hover:text-accent-info transition-colors">
          {ep.title || '無標題'}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground truncate max-w-[16ch]">{ep.podcast_name}</span>
          {ep.released_at_ms && (
            <span className="text-[10px] text-muted-foreground font-mono">{timeAgo(ep.released_at_ms)}</span>
          )}
          {ep.related_tickers.length > 0 && (
            <span className="text-[10px] text-accent-info font-mono truncate">
              {ep.related_tickers.slice(0, 3).join(' · ')}
            </span>
          )}
        </div>
      </div>
      <ChevronRight size={12} className="text-muted-foreground mt-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
    </Link>
  );
}

// ── Topic card ─────────────────────────────────────────────────────

function TopicCard({ tag, rank, maxCount }: { tag: TrendingTag; rank: number; maxCount: number }) {
  const label = getTopicLabel(tag.name);
  const barWidth = `${Math.max(8, Math.round((tag.scoped_count / maxCount) * 100))}%`;

  return (
    <div className="bg-card border border-border rounded-md overflow-hidden transition-all hover:border-accent-info/40 hover:shadow-[0_0_12px_-3px_hsl(var(--accent-info)/0.15)]">
      {/* Header */}
      <Link
        to={`/topics/${encodeURIComponent(tag.name)}`}
        className="flex items-center gap-3 px-4 pt-3.5 pb-2 group"
      >
        <div className="relative">
          <div className="w-9 h-9 rounded-md bg-muted grid place-items-center text-foreground">
            <Hash size={16} />
          </div>
          <div className="absolute -top-1.5 -left-1.5 w-5 h-5 rounded-full bg-card border border-border grid place-items-center text-[10px] font-mono font-bold text-muted-foreground">
            {rank}
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[15px] font-semibold tracking-[-0.01em] group-hover:text-accent-info transition-colors">
              #{label}
            </span>
            <TrendBadge weekly={tag.weekly_counts} />
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5 font-mono tabular-nums">
            {tag.scoped_count} 集
          </div>
        </div>
        <Sparkline data={tag.weekly_counts} width={80} height={28} className="shrink-0" />
        <ChevronRight size={14} className="text-muted-foreground shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
      </Link>

      {/* Progress bar */}
      <div className="px-4 pb-2">
        <div className="h-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-accent-info transition-[width] duration-700 ease-out"
            style={{ width: barWidth }}
          />
        </div>
      </div>

      {/* Episode previews */}
      {tag.recent_episodes.length > 0 && (
        <div className="px-4 pb-3 border-t border-border/50 pt-2">
          <div className="text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">最近集數</div>
          <div className="divide-y divide-border/30">
            {tag.recent_episodes.map((ep) => (
              <EpisodeRow key={ep.id} ep={ep} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────

function TopicSkeleton() {
  return (
    <div className="bg-card border border-border rounded-md p-4 animate-pulse">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-md bg-muted" />
        <div className="flex-1">
          <div className="h-4 w-24 bg-muted rounded mb-1.5" />
          <div className="h-3 w-12 bg-muted rounded" />
        </div>
        <div className="w-20 h-7 bg-muted rounded" />
      </div>
      <div className="h-1 bg-muted rounded-full mb-3" />
      <div className="space-y-2">
        <div className="h-3 w-full bg-muted rounded" />
        <div className="h-3 w-4/5 bg-muted rounded" />
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────

export const TopicsCloud: React.FC = () => {
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const res = await fetchWithFallback(
        () => getTrendingTags(6, 3),
        { tags: [] as TrendingTag[] },
        'getTrendingTags',
      ).catch(() => ({ tags: [] as TrendingTag[] }));
      if (!alive) return;
      setTags(Array.isArray(res?.tags) ? res.tags : []);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const totalEpisodes = useMemo(() => tags.reduce((s, t) => s + t.scoped_count, 0), [tags]);
  const maxCount = tags[0]?.scoped_count ?? 1;
  const thisWeekTotal = useMemo(() => tags.reduce((s, t) => s + (t.weekly_counts[0] ?? 0), 0), [tags]);
  const lastWeekTotal = useMemo(() => tags.reduce((s, t) => s + (t.weekly_counts[1] ?? 0), 0), [tags]);
  const weekDelta = thisWeekTotal - lastWeekTotal;

  return (
    <>
      <SEO title="話題排行" description="財經話題即時排行 — 依被提及集數排序，包含趨勢走勢與最新集數預覽。" />
      <PageContent>
        {/* Header */}
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">話題排行</h1>
          {!loading && (
            <div className="text-[12px] text-muted-foreground font-mono tabular-nums flex items-center gap-2">
              <span>{tags.length} 話題</span>
              <span className="text-border">·</span>
              <span>{totalEpisodes.toLocaleString('zh-TW')} 集</span>
            </div>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground max-w-[60ch] mb-5">
          依相關集數排序；走勢圖顯示過去 6 週提及趨勢，點擊話題可瀏覽完整集數。
        </p>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => <TopicSkeleton key={i} />)}
          </div>
        ) : tags.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
            目前沒有話題資料。
          </div>
        ) : (
          <>
            {/* Summary strip */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <RailCard title={<span className="inline-flex items-center gap-1.5"><Flame size={13} className="text-accent-info" />本週新增</span>} className="p-3.5">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[20px] font-semibold">{thisWeekTotal}</span>
                  <span className="text-[11px] text-muted-foreground">集</span>
                  {weekDelta !== 0 && (
                    <span className={`text-[11px] font-mono ${weekDelta > 0 ? 'text-sentiment-bull' : 'text-sentiment-bear'}`}>
                      {weekDelta > 0 ? '+' : ''}{weekDelta}
                    </span>
                  )}
                </div>
              </RailCard>
              <RailCard title={<span className="inline-flex items-center gap-1.5"><BarChart3 size={13} className="text-accent-info" />話題數</span>} className="p-3.5">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[20px] font-semibold">{tags.length}</span>
                  <span className="text-[11px] text-muted-foreground">個活躍話題</span>
                </div>
              </RailCard>
              <RailCard title={<span className="inline-flex items-center gap-1.5"><TrendingUp size={13} className="text-accent-info" />總集數</span>} className="p-3.5">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[20px] font-semibold">{totalEpisodes.toLocaleString('zh-TW')}</span>
                  <span className="text-[11px] text-muted-foreground">集</span>
                </div>
              </RailCard>
            </div>

            {/* Topic cards grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {tags.map((tag, i) => (
                <TopicCard key={tag.id} tag={tag} rank={i + 1} maxCount={maxCount} />
              ))}
            </div>
          </>
        )}
      </PageContent>
    </>
  );
};
