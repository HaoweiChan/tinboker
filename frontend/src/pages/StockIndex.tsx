import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, SentimentChip } from '@/components/redesign';
import { getRecentBuzz, type RecentBuzz } from '@/services/api/podcasts';
import { getSortedStocks } from '@/services/api/stocks';
import type { SentimentLabel } from '@/services/types';
import { fetchWithFallback } from '@/services/api/migration';
import type { Sentiment } from '@/lib/sentiment';
import { inferStockMarket } from '@/utils/stockDisplay';
import { StockIdentity } from '@/components/common/StockIdentity';
import { useStockSummaries } from '@/hooks/useStockSummaries';
import { TickerAvatar } from '@/components/common/TickerAvatar';

type Market = 'all' | 'TW' | 'US';
type Sort = 'mentions' | 'sentiment';

// Stable rank for the "sort by sentiment" segmented control. Spec § 5.3 forbids
// exposing sentiment_score on the wire, so we sort on the label tier locally.
const LABEL_RANK: Record<SentimentLabel, number> = {
  STRONG_BULLISH: 5,
  BULLISH: 4,
  NEUTRAL: 3,
  BEARISH: 2,
  STRONG_BEARISH: 1,
};

// Short market badge per row, keyed by the canonical market inference. KR uses a
// neutral chip; 6-digit codes (005930 Samsung, 000660 SK Hynix) were previously
// mislabeled TW by the all-numeric heuristic.
const MARKET_BADGE: Record<ReturnType<typeof inferStockMarket>, { label: string; cls: string }> = {
  TW: { label: 'TW', cls: 'bg-sentiment-bull-soft text-sentiment-bull' },
  US: { label: 'US', cls: 'bg-accent-info-soft text-accent-info' },
  KR: { label: 'KR', cls: 'bg-muted text-muted-foreground' },
};
function labelToSentiment(label: SentimentLabel): Sentiment {
  if (label === 'STRONG_BULLISH' || label === 'BULLISH') return 'BULLISH';
  if (label === 'STRONG_BEARISH' || label === 'BEARISH') return 'BEARISH';
  return 'NEUTRAL';
}

interface Row {
  ticker: string;
  name: string;
  count: number;
  sentimentLabel: SentimentLabel;
  lastMentioned: string;
}

export const StockIndex: React.FC = () => {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [market, setMarket] = useState<Market>('all');
  const [sort, setSort] = useState<Sort>('mentions');

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      // Real recent mention counts over the last 30 days (zh-TW launch feed),
      // NOT the all-time agents-precomputed trending_tickers (which ignored the
      // window — days=30 and days=90 returned identical all-time totals).
      const emptyBuzz: RecentBuzz = { tickers: [], distinct_count: 0, episode_count: 0 };
      const [buzz, stocks] = await Promise.all([
        fetchWithFallback<RecentBuzz>(() => getRecentBuzz({ days: 30, limit: 200 }), emptyBuzz, 'getRecentBuzz:index').catch(() => emptyBuzz),
        fetchWithFallback<unknown[]>(() => getSortedStocks({ sortBy: 'ticker', limit: 500 }), [], 'getSortedStocks:index').catch(() => [] as unknown[]),
      ]);
      if (!alive) return;
      const nameOf = new Map<string, string>();
      for (const s of Array.isArray(stocks) ? stocks : []) {
        const o = s as { ticker?: string; symbol?: string; name?: string; company_name?: string };
        const t = o.ticker || o.symbol;
        if (t) nameOf.set(t, o.name || o.company_name || t);
      }
      const tickers = Array.isArray(buzz?.tickers) ? buzz.tickers : [];
      setRows(
        tickers.map((t) => ({
          ticker: t.ticker,
          name: nameOf.get(t.ticker) || t.name || t.ticker,
          count: t.count,
          sentimentLabel: LABEL_RANK[t.sentiment_label] ? t.sentiment_label : ('NEUTRAL' as SentimentLabel),
          lastMentioned: String(t.last_mentioned ?? ''),
        })),
      );
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const list = useMemo(() => {
    let arr = rows.filter((r) => {
      if (market !== 'all' && inferStockMarket(r.ticker) !== market) return false;
      if (q) {
        const s = q.toLowerCase();
        return r.ticker.toLowerCase().includes(s) || r.name.toLowerCase().includes(s);
      }
      return true;
    });
    arr = [...arr].sort((a, b) =>
      sort === 'mentions'
        ? b.count - a.count
        : LABEL_RANK[b.sentimentLabel] - LABEL_RANK[a.sentimentLabel],
    );
    return arr;
  }, [rows, q, market, sort]);

  const visibleTickers = useMemo(() => list.slice(0, 100).map((r) => r.ticker), [list]);
  const summaries = useStockSummaries(visibleTickers);

  return (
    <>
      <SEO title="所有個股" description="最近被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。" />
      <PageContent>
        <div className="flex items-baseline justify-between mb-1">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">所有個股</h1>
          {!loading && <div className="text-xs text-muted-foreground font-mono tabular-nums">{rows.length} 檔（近 30 天提及）</div>}
        </div>
        <p className="text-sm text-muted-foreground max-w-[60ch] mb-4">最近 30 天被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。點任一檔進入情緒時間軸與相關集數。</p>

        <div className="flex gap-2.5 items-center mb-4 flex-wrap">
          <label className="flex items-center gap-2 flex-1 min-w-[180px] bg-card border border-border rounded-md px-3 py-2">
            <Search size={14} className="text-muted-foreground shrink-0" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋代號或名稱…" className="flex-1 bg-transparent outline-none text-sm" />
          </label>
          <Segmented options={[{ value: 'all', label: '全部' }, { value: 'TW', label: '台股' }, { value: 'US', label: '美股' }] as const} value={market} onChange={setMarket} />
          <Segmented options={[{ value: 'mentions', label: '提及' }, { value: 'sentiment', label: '情緒' }] as const} value={sort} onChange={setSort} />
        </div>

        <div className="bg-card border border-border rounded-md overflow-hidden">
          <div className="grid grid-cols-[1fr_52px_60px_22px] gap-2.5 items-center px-4 py-2.5 text-2xs font-medium text-muted-foreground uppercase tracking-[0.04em] border-b border-border font-mono">
            <span>個股</span>
            <span className="text-right">提及</span>
            <span className="text-right">情緒</span>
            <span />
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
                  className="grid grid-cols-[1fr_52px_60px_22px] gap-2.5 items-center px-4 py-3.5 border-b border-border last:border-b-0 hover:bg-muted transition-colors"
                >
                  <span className="min-w-0 flex items-center gap-2.5">
                    <TickerAvatar ticker={r.ticker} brandColor={summary?.brand_color} />
                    <span className="min-w-0 flex items-center gap-1.5">
                      <StockIdentity ticker={r.ticker} name={summary?.name ?? r.name} size="md" />
                      <span className={`text-2xs px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 ${badge.cls}`}>{badge.label}</span>
                    </span>
                  </span>
                  <span className="font-mono text-md tabular-nums text-right">{r.count}</span>
                  <span className="text-right">
                    <SentimentChip sentiment={labelToSentiment(r.sentimentLabel)} bare />
                  </span>
                  <ChevronRight size={14} className="text-muted-foreground" />
                </Link>
              );
            })
          )}
        </div>
      </PageContent>
    </>
  );
};
