import { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import {
  EpisodeCardV2,
  FilterPills,
  Segmented,
  RailCard,
  StatGroup,
  SentBar,
  SentimentChip,
  Change,
  PodMark,
  ListRow,
  TickerRow,
} from '@/components/redesign';

/**
 * Dev-only QA surface for the redesign tokens + components.
 * Mounted at /__design only when import.meta.env.DEV is true.
 */
export default function DesignPreview() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const [filter, setFilter] = useState<'最新' | '熱門' | '追蹤' | '今日法說'>('最新');
  const [sort, setSort] = useState<'mentions' | 'change' | 'sentiment'>('mentions');

  return (
    <div className="min-h-screen bg-background text-foreground p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-semibold tracking-tight">Design preview · 設計預覽</h1>
          <button onClick={toggleTheme} className="filter-pill">
            {theme === 'dark' ? '☀ 淺色' : '☾ 深色'}
          </button>
        </div>
        <p className="text-sm text-muted-foreground mb-8">
          Redesign tokens + components QA surface. 字體 Inter / Noto Sans TC / JetBrains Mono.
        </p>

        <FilterPills items={['最新', '熱門', '追蹤', '今日法說'] as const} value={filter} onChange={setFilter} meta={<span><span className="font-mono">11.25</span> · 整理了 <span className="font-mono">7</span> 集</span>} />

        <div className="flex gap-3 items-center mb-6 flex-wrap">
          <Segmented options={[{ value: 'mentions', label: '提及' }, { value: 'change', label: '漲跌' }, { value: 'sentiment', label: '情緒' }] as const} value={sort} onChange={setSort} />
          <SentimentChip sentiment="BULLISH" />
          <SentimentChip sentiment="BEARISH" />
          <SentimentChip sentiment="NEUTRAL" />
          <Change value={1.34} />
          <Change value={-3.4} />
          <Change value={null} />
          <Change value={2.18} big />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-8">
          <EpisodeCardV2
            podcasterName="股癌"
            podcasterInitial="癌"
            podcasterKind="solid"
            episodeNumber="EP 451"
            timeAgo="3 小時前"
            durationMinutes={62}
            title="台積電 2 奈米良率超預期，但乖離率太大，該等回檔再進場"
            summary="先進製程良率提升速度遠超市場預期，展現極強技術領先。本集同時提到輝達 GP200 出貨翻倍。"
            tickers={[
              { symbol: '2330.TW', sentiment: 'BULLISH', changePercent: 1.34 },
              { symbol: 'NVDA', sentiment: 'BULLISH', changePercent: 2.18 },
              { symbol: 'INTC', sentiment: 'BEARISH', changePercent: -3.4 },
            ]}
            tags={['半導體', '法說會', 'AI 基建']}
            commentCount={12}
            isNew
            href="#"
            highlight
          />
          <EpisodeCardV2
            podcasterName="財報狗"
            podcasterInitial="財"
            podcasterKind="info"
            timeAgo="昨天"
            durationMinutes={48}
            title="紅海危機下的航運股，這次和疫情時期不同"
            summary="紅海危機推升運價但需求面遠不如疫情。長榮、陽明短期反彈空間有限。"
            tickers={[
              { symbol: '2603.TW', sentiment: 'NEUTRAL', changePercent: -0.52 },
              { symbol: '2609.TW', sentiment: 'BULLISH', changePercent: 0.8 },
            ]}
            tags={['航運', '紅海', '週期股']}
            commentCount={5}
            href="#"
          />
        </div>

        <div className="grid md:grid-cols-3 gap-4 mb-8">
          <RailCard title="市場脈動" sub="近 30 天">
            <div className="flex flex-col gap-4 text-[13px]">
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] text-muted-foreground tracking-wide">情緒趨勢</span>
                <SentBar bull={24} neutral={8} bear={12} />
                <div className="flex items-center justify-between">
                  <span><span className="text-sentiment-bull">多 24</span><span className="text-muted-foreground"> · 中 8 · </span><span className="text-sentiment-bear">空 12</span></span>
                  <span className="text-sentiment-bull font-mono text-[11px]">↑ +3</span>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[11px] text-muted-foreground tracking-wide">聲量飆升</span>
                <div className="flex items-center justify-between"><span className="font-medium">超微 <span className="font-mono text-[10px] text-muted-foreground">AMD</span></span><span className="text-sentiment-bull font-mono text-[11px]">↑ +12 集</span></div>
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between"><span className="text-[11px] text-muted-foreground tracking-wide">新進個股</span><span className="text-[11px] text-muted-foreground font-mono">+3 檔新上榜</span></div>
                <span className="text-[12px] text-foreground/80">聯發科、緯創、日月光</span>
              </div>
            </div>
          </RailCard>
          <RailCard title="這幾天大家在聊" sub="7 天內提及">
            {[
              { sym: 'NVDA', name: '輝達', chg: 2.18, b: 11, n: 2, e: 1 },
              { sym: '2330.TW', name: '台積電', chg: 1.34, b: 8, n: 2, e: 1 },
              { sym: 'TSLA', name: '特斯拉', chg: -1.25, b: 3, n: 1, e: 4 },
            ].map((t, i) => (
              <div key={t.sym} className="grid grid-cols-[18px_1fr_auto] gap-2.5 items-center py-2 border-t border-border first:border-t-0 text-[13px]">
                <span className="font-mono text-[11px] text-muted-foreground text-right">{String(i + 1).padStart(2, '0')}</span>
                <span className="flex items-center gap-2 min-w-0"><span className="font-mono text-[12px] font-medium">{t.sym}</span><span className="text-[12px] text-muted-foreground truncate">{t.name}</span></span>
                <span className="flex items-center gap-2"><SentBar bull={t.b} neutral={t.n} bear={t.e} width={64} /><Change value={t.chg} /></span>
              </div>
            ))}
          </RailCard>
          <RailCard title="本週更新最勤" sub="更新集數">
            {[
              { name: '股癌', ini: '癌', kind: 'solid' as const, eps: 5, d: '+12%' },
              { name: 'M觀點', ini: 'M', kind: 'mute' as const, eps: 4, d: '+8%' },
              { name: '財報狗', ini: '財', kind: 'info' as const, eps: 3, d: '−3%' },
            ].map((p) => (
              <div key={p.name} className="grid grid-cols-[28px_1fr_auto] gap-2.5 items-center py-2 border-t border-border first:border-t-0">
                <PodMark label={p.ini} kind={p.kind} size={28} />
                <div className="min-w-0"><div className="text-[13px] font-medium">{p.name}</div><div className="text-[11px] text-muted-foreground">本週 {p.eps} 集</div></div>
                <span className="text-[11px] font-mono text-muted-foreground">{p.d}</span>
              </div>
            ))}
          </RailCard>
        </div>

        <h2 className="text-lg font-medium mb-3">StatGroup</h2>
        <div className="mb-8">
          <StatGroup
            items={[
              { label: '本月被提及', value: <>11<span className="text-[14px] text-muted-foreground ml-1">集</span></>, sub: '較上月 +3 集' },
              { label: '情緒比例', value: <SentBar bull={8} neutral={2} bear={1} width={80} />, textValue: true, sub: <span><span className="text-sentiment-bull">多 8</span> · <span className="text-muted-foreground">中 2</span> · <span className="text-sentiment-bear">空 1</span></span> },
              { label: '最新提及', value: '今天', textValue: true, sub: '股癌 EP 451' },
              { label: '相關話題', value: 4, sub: '#半導體 #法說會 +2' },
            ]}
          />
        </div>

        <h2 className="text-lg font-medium mb-3">ListRow / TickerRow</h2>
        <div className="mb-8 space-y-1.5">
          <ListRow lead={<span className="font-mono text-[12px] text-muted-foreground">EP 451</span>} title="台積電 2 奈米良率超預期，該等回檔" subtitle="3 小時前" mid={<div className="flex gap-1"><span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-sentiment-bull-soft text-sentiment-bull">2330.TW</span></div>} trailing={<><span>62m</span><span>12</span></>} href="#" />
          <div className="flex flex-col gap-1.5 max-w-md">
            <TickerRow ticker={{ symbol: '2330.TW', sentiment: 'BULLISH', changePercent: 1.34 }} />
            <TickerRow ticker={{ symbol: 'INTC', sentiment: 'BEARISH', changePercent: -3.4 }} />
            <TickerRow ticker={{ symbol: 'SPY', changePercent: 0.42 }} />
          </div>
        </div>

        <h2 className="text-lg font-medium mb-3">Token swatches</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {([
            ['background', 'bg-background border border-border'],
            ['card', 'bg-card border border-border'],
            ['muted', 'bg-muted'],
            ['foreground', 'bg-foreground'],
            ['primary', 'bg-primary'],
            ['accent-info', 'bg-accent-info'],
            ['accent-info-soft', 'bg-accent-info-soft'],
            ['sentiment-bull', 'bg-sentiment-bull'],
            ['sentiment-bear', 'bg-sentiment-bear'],
            ['sentiment-neutral', 'bg-sentiment-neutral'],
          ] as const).map(([name, cls]) => (
            <div key={name} className="border border-border rounded-md overflow-hidden">
              <div className={`h-14 ${cls}`} />
              <div className="p-2 text-xs font-mono">{name}</div>
            </div>
          ))}
        </div>

        <h2 className="text-lg font-medium mb-3">Type ramp</h2>
        <div className="space-y-2 mb-12">
          <div className="text-2xl font-semibold tracking-tight">台積電 2 奈米良率 EP 451 NVDA +2.18%</div>
          <div className="text-base">先進製程良率提升 — Inter renders Latin/digits, Noto handles Chinese.</div>
          <div className="text-sm text-muted-foreground">tabular numerals: 1,234.56 vs 9,876.54 align vertically when stacked.</div>
          <div className="font-mono text-sm tabular-nums">2330.TW · 1,205.00 · +1.34%</div>
        </div>
      </div>
    </div>
  );
}
