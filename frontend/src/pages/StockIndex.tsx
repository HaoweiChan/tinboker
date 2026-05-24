import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, SentimentChip } from '@/components/redesign';
import { getTrendingTickers } from '@/services/api/podcasts';
import { getSortedStocks } from '@/services/api/stocks';
import type { SentimentLabel, TickerTrending } from '@/services/types';
import { fetchWithFallback } from '@/services/api/migration';
import type { Sentiment } from '@/lib/sentiment';
import { getStockLabel } from '@/utils/stockDisplay';
import { useStockSummaries } from '@/hooks/useStockSummaries';

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

function isTW(ticker: string): boolean {
  return /\.TW[OW]?$/i.test(ticker);
}
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
      // Spec § 5.4: default to days=90, limit=200 on StockIndex.
      const [trending, stocks] = await Promise.all([
        fetchWithFallback<TickerTrending[]>(() => getTrendingTickers({ days: 90, limit: 200 }), [], 'getTrendingTickers:index').catch(() => [] as TickerTrending[]),
        fetchWithFallback<unknown[]>(() => getSortedStocks({ sortBy: 'ticker', limit: 500 }), [], 'getSortedStocks:index').catch(() => [] as unknown[]),
      ]);
      if (!alive) return;
      const nameOf = new Map<string, string>();
      for (const s of Array.isArray(stocks) ? stocks : []) {
        const o = s as { ticker?: string; symbol?: string; name?: string; company_name?: string };
        const t = o.ticker || o.symbol;
        if (t) nameOf.set(t, o.name || o.company_name || t);
      }
      setRows(
        (Array.isArray(trending) ? trending : []).map((t) => ({
          ticker: t.ticker,
          name: nameOf.get(t.ticker) || t.ticker,
          count: t.count,
          sentimentLabel: t.sentiment_label,
          lastMentioned: t.last_mentioned,
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
      if (market === 'TW' && !isTW(r.ticker)) return false;
      if (market === 'US' && isTW(r.ticker)) return false;
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
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">所有個股</h1>
          {!loading && <div className="text-[12px] text-muted-foreground font-mono tabular-nums">{rows.length} 檔（近 90 天提及）</div>}
        </div>
        <p className="text-[13px] text-muted-foreground max-w-[60ch] mb-4">最近 90 天被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。點任一檔進入情緒時間軸與相關集數。</p>

        <div className="flex gap-2.5 items-center mb-4 flex-wrap">
          <label className="flex items-center gap-2 flex-1 min-w-[180px] bg-card border border-border rounded-md px-3 py-2">
            <Search size={14} className="text-muted-foreground shrink-0" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋代號或名稱…" className="flex-1 bg-transparent outline-none text-[13px]" />
          </label>
          <Segmented options={[{ value: 'all', label: '全部' }, { value: 'TW', label: '台股' }, { value: 'US', label: '美股' }] as const} value={market} onChange={setMarket} />
          <Segmented options={[{ value: 'mentions', label: '提及' }, { value: 'sentiment', label: '情緒' }] as const} value={sort} onChange={setSort} />
        </div>

        <div className="bg-card border border-border rounded-md overflow-hidden">
          <div className="grid grid-cols-[1fr_80px_72px_28px] gap-3.5 items-center px-4 py-2.5 text-[11px] font-medium text-muted-foreground uppercase tracking-[0.04em] border-b border-border font-mono">
            <span>個股</span>
            <span className="text-right">提及</span>
            <span className="text-right">情緒</span>
            <span />
          </div>
          {loading ? (
            Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-[45px] border-b border-border last:border-b-0 animate-pulse bg-muted/30" />)
          ) : list.length === 0 ? (
            <div className="px-4 py-12 text-center text-[13px] text-muted-foreground">{q ? `找不到符合「${q}」的個股` : '目前沒有個股資料。'}</div>
          ) : (
            list.map((r) => {
              const summary = summaries[r.ticker];
              const { primary, secondary } = getStockLabel({
                ticker: r.ticker,
                name: summary?.name ?? r.name,
                market: summary?.market,
              });
              return (
                <Link
                  key={r.ticker}
                  to={`/stock/${encodeURIComponent(r.ticker)}`}
                  className="grid grid-cols-[1fr_80px_72px_28px] gap-3.5 items-center px-4 py-3 border-b border-border last:border-b-0 hover:bg-muted transition-colors"
                >
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5">
                      <span className="text-[13.5px] font-medium truncate">{primary}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold ${isTW(r.ticker) ? 'bg-sentiment-bull-soft text-sentiment-bull' : 'bg-accent-info-soft text-accent-info'}`}>{isTW(r.ticker) ? 'TW' : 'US'}</span>
                    </span>
                    {secondary && (
                      <span className="block text-[11px] text-muted-foreground font-mono truncate">{secondary}</span>
                    )}
                  </span>
                  <span className="font-mono text-[13px] tabular-nums text-right">{r.count}</span>
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
