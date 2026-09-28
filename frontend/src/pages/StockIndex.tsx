import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ChevronRight, ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { ExploreTabs } from '@/components/layout/ExploreTabs';
import { getRecentBuzz, type RecentBuzz } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { inferStockMarket } from '@/utils/stockDisplay';
import { StockIdentity } from '@/components/common/StockIdentity';
import { useStockSummaries } from '@/hooks/useStockSummaries';
import { TickerAvatar } from '@/components/common/TickerAvatar';

import { compareOptionalNumbers } from '@/lib/listSort';

type StockSort = 'count' | 'attentionLevel';
type Market = 'all' | 'TW' | 'US';
// Short market badge per row, keyed by the canonical market inference. KR uses a
// neutral chip; 6-digit codes (005930 Samsung, 000660 SK Hynix) were previously
// mislabeled TW by the all-numeric heuristic.
const MARKET_BADGE: Record<ReturnType<typeof inferStockMarket>, { label: string; cls: string }> = {
  TW: { label: 'TW', cls: 'bg-sentiment-bull-soft text-sentiment-bull' },
  US: { label: 'US', cls: 'bg-accent-info-soft text-accent-info' },
  KR: { label: 'KR', cls: 'bg-muted text-muted-foreground' },
};
interface Row {
  ticker: string;
  name: string;
  count: number;
  lastMentioned: string;
  attentionLevel: number | null;
  attentionAsOf: string | null;
}

export const StockIndex: React.FC = () => {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [market, setMarket] = useState<Market>('all');
  const [sort, setSort] = useState<{ key: StockSort; direction: 'asc' | 'desc' }>({ key: 'count', direction: 'desc' });
  const toggleSort = (key: StockSort) => setSort((current) => ({
    key, direction: current.key === key && current.direction === 'desc' ? 'asc' : 'desc',
  }));

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      // Real recent mention counts over the last 30 days (zh-TW launch feed),
      // NOT the all-time agents-precomputed trending_tickers (which ignored the
      // window — days=30 and days=90 returned identical all-time totals).
      const emptyBuzz: RecentBuzz = { tickers: [], distinct_count: 0, episode_count: 0 };
      const buzz = await fetchWithFallback<RecentBuzz>(() => getRecentBuzz({ days: 30, limit: 200 }), emptyBuzz, 'getRecentBuzz:index').catch(() => emptyBuzz);
      if (!alive) return;
      const tickers = Array.isArray(buzz?.tickers) ? buzz.tickers : [];
      setRows(
        tickers.map((t) => ({
          ticker: t.ticker,
          name: t.name || t.ticker,
          count: t.count,
          lastMentioned: String(t.last_mentioned ?? ''),
          attentionLevel: t.attention_level ?? null,
          attentionAsOf: t.attention_as_of ?? null,
        })),
      );
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const list = useMemo(() => {
    const arr = rows.filter((r) => {
      if (market !== 'all' && inferStockMarket(r.ticker) !== market) return false;
      if (q) {
        const s = q.toLowerCase();
        return r.ticker.toLowerCase().includes(s) || r.name.toLowerCase().includes(s);
      }
      return true;
    });
    return [...arr].sort((a, b) => compareOptionalNumbers(a[sort.key], b[sort.key], sort.direction) || a.ticker.localeCompare(b.ticker));
  }, [rows, q, market, sort]);

  const visibleTickers = useMemo(() => list.slice(0, 100).map((r) => r.ticker), [list]);
  const summaries = useStockSummaries(visibleTickers);

  return (
    <>
      <SEO title="所有個股" description="最近被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。" />
      <PageContent>
        <ExploreTabs />
        <div className="flex items-baseline justify-between mb-1">
          <h1 className="heading-accent text-2xl font-semibold tracking-[-0.02em]">所有個股</h1>
          {!loading && <div className="text-xs text-muted-foreground font-mono tabular-nums">{rows.length} 檔（近 30 天提及）</div>}
        </div>
        <p className="text-base text-muted-foreground max-w-[60ch] mb-4">最近 30 天被 TinBoker 追蹤的 Podcast 提及的所有個股。點欄名排序，點個股查看走勢與相關集數。</p>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-border bg-card px-3 py-2 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/30">
            <Search size={14} className="shrink-0 text-muted-foreground" />
            <input aria-label="搜尋代號或名稱" value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋代號或名稱…" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
          </label>
          <div className="flex items-center justify-between gap-2">
            <div role="group" aria-label="股票市場" className="flex shrink-0 items-center gap-1.5">
              {([{ value: 'all', label: '全部' }, { value: 'TW', label: '台股' }, { value: 'US', label: '美股' }] as const).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={market === option.value}
                  onClick={() => setMarket(option.value)}
                  className={`min-h-10 whitespace-nowrap rounded-md border px-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${market === option.value ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border bg-transparent text-muted-foreground hover:border-muted-foreground/40 hover:text-foreground'}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <details className="mb-3 text-xs text-muted-foreground">
          <summary className="w-fit cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">聲量水位怎麼看？</summary>
          <p className="mt-2 max-w-[60ch] leading-relaxed">0–100，比較個股目前與自身近一年的討論聲量。越高代表近期越受關注，不代表看多或預期報酬。「—」表示資料不足或暫無資料。</p>
        </details>
        <div className="bg-card border border-border rounded-md overflow-hidden">
          <div className="grid grid-cols-[minmax(0,1fr)_44px_72px] gap-4 items-center px-3 py-2.5 sm:grid-cols-[1fr_52px_100px_22px] sm:gap-2.5 sm:px-4 text-2xs font-medium text-muted-foreground uppercase tracking-[0.04em] border-b border-border font-mono">
            <span>個股</span>
            {([{ key: 'count', label: '提及' }, { key: 'attentionLevel', label: '聲量水位' }] as const).map((column) => {
              const active = sort.key === column.key;
              const Icon = active ? (sort.direction === 'desc' ? ArrowDown : ArrowUp) : ArrowUpDown;
              return (
                <button
                  key={column.key}
                  type="button"
                  onClick={() => toggleSort(column.key)}
                  aria-label={`${column.label}排序${active ? `，目前${sort.direction === 'desc' ? '由高至低' : '由低至高'}` : ''}，點擊${active && sort.direction === 'desc' ? '由低至高' : '由高至低'}`}
                  className={`-my-2.5 flex min-h-11 items-center justify-end gap-0.5 whitespace-nowrap rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${active ? 'text-primary' : 'hover:text-foreground'}`}
                >
                  {column.label}<Icon size={12} aria-hidden="true" className="shrink-0" />
                </button>
              );
            })}
            <span className="hidden sm:block" />
          </div>
          {loading ? (
            Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-[45px] border-b border-border last:border-b-0 animate-pulse bg-muted/30" />)
          ) : list.length === 0 ? (
            <div className="px-4 py-12 text-center text-sm text-muted-foreground">{q ? `找不到符合「${q}」的個股` : '目前沒有個股資料。'}</div>
          ) : (
            list.map((r) => {
              const summary = summaries[r.ticker];
              const mkt = inferStockMarket(r.ticker);
              const badge = MARKET_BADGE[mkt];
              return (
                <Link
                  key={r.ticker}
                  to={`/stock/${encodeURIComponent(r.ticker)}`}
                  className="grid grid-cols-[minmax(0,1fr)_44px_72px] gap-4 items-center px-3 py-2.5 sm:grid-cols-[1fr_52px_100px_22px] sm:gap-2.5 sm:px-4 border-b border-border last:border-b-0 hover:bg-muted transition-colors"
                >
                  <span className="min-w-0 flex items-center gap-2 sm:gap-2.5">
                    <TickerAvatar ticker={r.ticker} brandColor={summary?.brand_color} />
                    <span className="min-w-0 flex items-center gap-1.5">
                      <StockIdentity ticker={r.ticker} name={summary?.name ?? r.name} size="md" hideCode />
                      <span className={`hidden sm:inline text-2xs px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 ${badge.cls}`}>{badge.label}</span>
                    </span>
                  </span>
                  <span className="text-right font-mono text-xs sm:text-sm tabular-nums">{r.count}</span>
                  <span
                    className="justify-self-end w-12 sm:w-16"
                    title={r.attentionLevel == null ? '聲量水位：資料不足或暫無資料' : `聲量水位 ${r.attentionLevel} / 100${r.attentionAsOf ? ` · ${r.attentionAsOf}` : ''}`}
                    aria-label={r.attentionLevel == null ? '聲量水位：資料不足或暫無資料' : `聲量水位 ${r.attentionLevel} / 100`}
                  >
                    <span className="block text-right font-mono text-xs sm:text-sm tabular-nums">{r.attentionLevel ?? '—'}</span>
                    {r.attentionLevel != null && (
                      <span aria-hidden="true" className="mt-1 block h-0.5 overflow-hidden rounded-full bg-muted">
                        <span className="block h-full rounded-full bg-accent-info" style={{ width: `${r.attentionLevel}%` }} />
                      </span>
                    )}
                  </span>
                  <ChevronRight size={14} className="hidden text-muted-foreground sm:block" />
                </Link>
              );
            })
          )}
        </div>
      </PageContent>
    </>
  );
};
