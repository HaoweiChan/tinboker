import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Play } from 'lucide-react';
import type { Reason, Risk, SentimentLabel, TickerInsight } from '@/services/types';
import { normalizeSentiment } from '@/lib/sentiment';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/date';
import { Change } from '@/components/redesign';
import type { MentionPerformance } from '@/validation/schemas';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { Episode as MockEpisode } from '@/data/mockData';

interface TickerInsightCardProps {
    insight: TickerInsight;
    /** Episodes for this ticker (from StockDashboard). Used to launch podcast at reason/risk timestamp. */
    episodes?: MockEpisode[];
    /** Post-mention 1/5/20/60 trading-day returns for this episode (TKB-001), when computed. */
    performance?: MentionPerformance | null;
}

const WINDOWS: { key: keyof MentionPerformance; label: string }[] = [
    { key: 'r1d', label: '1日' }, { key: 'r5d', label: '5日' }, { key: 'r20d', label: '20日' }, { key: 'r60d', label: '60日' },
];

// Semantic stance colours (green bull / red bear), matching the rail, the chart dots
// and the SentBar — not the market's price colours.
const RAIL: Record<'BULLISH' | 'BEARISH' | 'NEUTRAL', string> = {
    BULLISH: 'bg-sentiment-bull',
    BEARISH: 'bg-sentiment-bear',
    NEUTRAL: 'bg-muted-foreground/40',
};
const STANCE: Record<'BULLISH' | 'BEARISH' | 'NEUTRAL', { cls: string; label: string }> = {
    BULLISH: { cls: 'text-sentiment-bull', label: '看多' },
    BEARISH: { cls: 'text-sentiment-bear', label: '看空' },
    NEUTRAL: { cls: 'text-muted-foreground', label: '中立' },
};

const SEVERITY_LABELS: Record<string, string> = { HIGH: '高', MEDIUM: '中', LOW: '低' };

const trimText = (value?: string | null) => value?.trim() ?? '';
const hasText = (value?: string | null) => trimText(value).length > 0;
const hasCjk = (value: string) => /[㐀-鿿]/.test(value);

const localizeThesis = (insight: TickerInsight) => {
    const thesis = trimText(insight.bluf_thesis);
    if (!thesis) return '目前尚無明確投資摘要。';
    if (hasCjk(thesis)) return thesis;
    return `${insight.ticker} 的投資摘要尚未完成繁中轉寫，系統已依可用資訊整理下方重點。`;
};

const mmss = (ms: number) => {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/**
 * One podcast take on a ticker, as a row in the 觀點 list: who · when · stance · horizon,
 * the one-line thesis, and a fold-out with the reasons and risks (each with a jump-to
 * button when the pipeline kept a timestamp). Rows, not cards: the stock page lists
 * dozens of these and the old two-column cards with a 20px thesis were mostly air.
 */
export const TickerInsightCard: React.FC<TickerInsightCardProps> = ({ insight, episodes = [], performance }) => {
    const [expanded, setExpanded] = useState(false);
    const playEpisode = usePlayerStore((s) => s.playEpisode);

    const kind = normalizeSentiment(insight.sentiment_label as SentimentLabel) ?? 'NEUTRAL';
    const reasons: Reason[] = insight.reasons.filter((r) => hasText(r.title) || hasText(r.description));
    const risks: Risk[] = insight.risks.filter((r) => hasText(r.title) || hasText(r.description));
    const hasDetail = reasons.length > 0 || risks.length > 0;
    // Only windows that have elapsed; a fresh mention shows nothing rather than four dashes.
    const returns = WINDOWS.filter((w) => typeof performance?.[w.key] === 'number');
    const toggle = () => { if (hasDetail) setExpanded((v) => !v); };

    // Backend provides start_time in milliseconds; convert to seconds for GlobalPlayer
    const handlePlay = (startTimeMs: number) => {
        const seconds = Math.floor(startTimeMs / 1000);
        const episode = episodes.find((ep) => ep.id === insight.episode_id);
        if (!episode) {
            window.open(`https://open.spotify.com/search/${encodeURIComponent(insight.episode_id)}`, '_blank');
            return;
        }
        playEpisode(
            { id: episode.id, title: episode.title, showName: episode.showName, coverUrl: episode.imageUrl, spotifyUri: episode.spotifyUri },
            episode.spotifyUri ? { seekTo: seconds } : undefined,
        );
    };

    const Jump: React.FC<{ ms: number; tone: 'bull' | 'bear' }> = ({ ms, tone }) => (
        <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handlePlay(ms); }}
            title="跳轉至音檔"
            className={cn(
                'inline-flex items-center gap-1 shrink-0 rounded px-1.5 py-0.5 text-2xs font-mono tabular-nums transition-colors',
                tone === 'bull' ? 'text-sentiment-bull hover:bg-sentiment-bull-soft' : 'text-sentiment-bear hover:bg-sentiment-bear-soft',
            )}
        >
            <Play size={10} className="fill-current" />
            {mmss(ms)}
        </button>
    );

    return (
        <article
            className={cn('relative px-4 py-3 hover:bg-muted/30 transition-colors', hasDetail && 'cursor-pointer')}
            onClick={toggle}
            onKeyDown={(e) => { if (hasDetail && (e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); toggle(); } }}
            tabIndex={hasDetail ? 0 : undefined}
            aria-expanded={hasDetail ? expanded : undefined}
        >
            <span className={cn('absolute left-0 top-3 bottom-3 w-0.5 rounded-full', RAIL[kind])} aria-hidden />
            <div className="flex items-center gap-x-2.5 gap-y-1 flex-wrap text-xs text-muted-foreground">
                <span className="text-sm font-medium text-foreground">{insight.podcaster || insight.episode_id.split('_')[0] || '—'}</span>
                <span className="tabular-nums">{formatDate(insight.podcast_launch_time)}</span>
                <span className={cn('font-medium', STANCE[kind].cls)}>{STANCE[kind].label}</span>
                {insight.time_horizon && <span>{insight.time_horizon}</span>}
                {returns.length > 0 && (
                    <span className="inline-flex items-center gap-2 tabular-nums" title="提及後 N 個交易日的報酬">
                        {returns.map((w) => (
                            <span key={w.key} className="inline-flex items-baseline gap-1"><span className="text-muted-foreground/70">{w.label}</span><Change value={performance![w.key]} /></span>
                        ))}
                    </span>
                )}
                {hasDetail && (
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggle(); }}
                        className="ml-auto inline-flex items-center gap-0.5 text-2xs text-muted-foreground/80 hover:text-foreground transition-colors"
                        tabIndex={-1}
                    >
                        {expanded ? '收起' : '分析邏輯'}
                        {reasons.length > 0 && !expanded && <span className="font-mono tabular-nums">{reasons.length}</span>}
                        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                )}
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">{localizeThesis(insight)}</p>

            {expanded && hasDetail && (
                <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
                    {reasons.length > 0 && (
                        <div className="rounded-md bg-muted/40 p-3">
                            <div className="text-2xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-1.5">投資理由</div>
                            <ul className="space-y-2">
                                {reasons.map((r, i) => (
                                    <li key={i} className="text-xs leading-relaxed">
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="font-medium text-foreground">{r.title}</span>
                                            {r.start_time > 0 && <Jump ms={r.start_time} tone="bull" />}
                                        </div>
                                        {hasText(r.description) && <p className="text-muted-foreground mt-0.5">{r.description}</p>}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {risks.length > 0 && (
                        <div className="rounded-md bg-sentiment-bear-soft/40 p-3">
                            <div className="text-2xs font-semibold uppercase tracking-[0.08em] text-sentiment-bear/80 mb-1.5">風險提示</div>
                            <ul className="space-y-2">
                                {risks.map((r, i) => (
                                    <li key={i} className="text-xs leading-relaxed">
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="font-medium text-foreground">
                                                {r.title}
                                                {r.severity && <span className="ml-1.5 text-2xs text-sentiment-bear">{SEVERITY_LABELS[r.severity] ?? r.severity}</span>}
                                            </span>
                                            {r.start_time > 0 && <Jump ms={r.start_time} tone="bear" />}
                                        </div>
                                        {hasText(r.description) && <p className="text-muted-foreground mt-0.5">{r.description}</p>}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </article>
    );
};
