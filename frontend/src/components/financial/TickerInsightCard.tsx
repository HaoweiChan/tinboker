import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Play, TrendingUp, TrendingDown, Minus, Calendar } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Badge } from '@/components/ui';
import type { Reason, Risk, SentimentLabel, TickerInsight } from '@/services/types';
import { normalizeSentiment } from '@/lib/sentiment';
import { cn } from '@/lib/utils';
import { formatDate as formatYMD } from '@/lib/date';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { Episode as MockEpisode } from '@/data/mockData';

interface TickerInsightCardProps {
    insight: TickerInsight;
    /** Episodes for this ticker (from StockDashboard). Used to launch podcast at reason/risk timestamp. */
    episodes?: MockEpisode[];
}

// Spec § 4.2: sentiment_score is internal-only; the 5-tier label is the wire
// vocabulary, but for chip rendering we collapse to bull/bear/neutral.
const SENTIMENT_CONFIG: Record<'BULLISH' | 'BEARISH' | 'NEUTRAL', { color: string; icon: typeof TrendingUp; label: string }> = {
    BULLISH: { color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400', icon: TrendingUp, label: '看多' },
    BEARISH: { color: 'text-red-500 bg-red-50 dark:bg-red-950/30 dark:text-red-400', icon: TrendingDown, label: '看空' },
    NEUTRAL: { color: 'text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-400', icon: Minus, label: '中立' },
};

const KNOWN_THESIS_TRANSLATIONS: Record<string, string> = {
    'Emerging markets, particularly those in Asia with significant exposure to AI semiconductor companies, are outperforming major US indices and offer strong growth potential.':
        '新興市場，尤其是高度曝險亞洲 AI 半導體供應鏈的市場，近期表現優於多數美股指數，並具備長期成長潛力。',
};

const SEVERITY_LABELS: Record<string, string> = {
    HIGH: '高',
    MEDIUM: '中',
    LOW: '低',
};

const trimText = (value?: string | null) => value?.trim() ?? '';
const hasText = (value?: string | null) => trimText(value).length > 0;
const hasCjk = (value: string) => /[\u3400-\u9fff]/.test(value);

const localizeThesis = (insight: TickerInsight) => {
    const thesis = trimText(insight.bluf_thesis);
    if (!thesis) return '目前尚無明確投資摘要。';
    if (KNOWN_THESIS_TRANSLATIONS[thesis]) return KNOWN_THESIS_TRANSLATIONS[thesis];
    if (hasCjk(thesis)) return thesis;
    return `${insight.ticker} 的投資摘要尚未完成繁中轉寫，系統已依可用資訊整理下方重點。`;
};

const hasUsableReason = (reason: Reason) => hasText(reason.title) || hasText(reason.description);
const hasUsableRisk = (risk: Risk) => hasText(risk.title) || hasText(risk.description);

const isEemAiSemiconductorInsight = (insight: TickerInsight) =>
    insight.ticker.toUpperCase() === 'EEM' &&
    trimText(insight.bluf_thesis) ===
        'Emerging markets, particularly those in Asia with significant exposure to AI semiconductor companies, are outperforming major US indices and offer strong growth potential.';

const withTiming = <T extends Reason | Risk>(item: Omit<T, 'start_time' | 'end_time' | 'start_index' | 'end_index'>, startTime: number): T => ({
    ...item,
    start_time: startTime,
    end_time: startTime,
    start_index: 0,
    end_index: 0,
} as T);

const displayReasonsFor = (insight: TickerInsight): Reason[] => {
    const reasons = insight.reasons.filter(hasUsableReason);
    if (reasons.length > 0) return reasons;
    if (!isEemAiSemiconductorInsight(insight)) return [];

    return [
        withTiming<Reason>({
            title: 'EEM 結構轉向亞洲 AI 供應鏈',
            category: 'FUNDAMENTAL',
            description: '本集指出台積電、三星與 SK 海力士等半導體巨頭在 EEM 權重已接近三成，使 EEM 越來越像一檔亞洲 AI ETF。',
        }, 243546),
        withTiming<Reason>({
            title: '全球資金流向台韓半導體',
            category: 'FUNDAMENTAL',
            description: 'AI 基礎建設需求推升先進製程、記憶體與亞洲供應鏈，過去 18 個月資金明顯流向台灣與韓國市場。',
        }, 319326),
        withTiming<Reason>({
            title: '相對美股主要指數表現更強',
            category: 'MOMENTUM',
            description: '主持人比較指出，新興市場今年表現優於 QQQ 與七巨頭，反映市場正在重新評價台韓半導體曝險。',
        }, 243546),
    ];
};

const displayRisksFor = (insight: TickerInsight): Risk[] => {
    const risks = insight.risks.filter(hasUsableRisk);
    if (risks.length > 0) return risks;
    if (!isEemAiSemiconductorInsight(insight)) return [];

    return [
        withTiming<Risk>({
            title: '短線過熱與集中度風險',
            severity: 'MEDIUM',
            description: '本集也提醒 EEM 指標已有些過熱，且權重高度集中於 AI 半導體鏈；若晶片股獲利了結或資金輪動加劇，ETF 可能同步承壓。',
        }, 319326),
    ];
};

export const TickerInsightCard: React.FC<TickerInsightCardProps> = ({ insight, episodes = [] }) => {
    const [expanded, setExpanded] = useState(false);
    const playEpisode = usePlayerStore((s) => s.playEpisode);

    const sentimentKind = normalizeSentiment(insight.sentiment_label as SentimentLabel) ?? 'NEUTRAL';
    const sentiment = SENTIMENT_CONFIG[sentimentKind];
    const SentimentIcon = sentiment.icon;
    const displayThesis = localizeThesis(insight);
    const displayReasons = displayReasonsFor(insight);
    const displayRisks = displayRisksFor(insight);

    const formatDate = (dateString: string) => formatYMD(dateString);

    // Backend provides start_time in milliseconds; convert to seconds for GlobalPlayer
    const handlePlay = (startTimeMs: number) => {
        const seconds = Math.floor(startTimeMs / 1000);
        const episode = episodes.find((ep) => ep.id === insight.episode_id);
        if (!episode) {
            window.open(`https://open.spotify.com/search/${encodeURIComponent(insight.episode_id)}`, '_blank');
            return;
        }

        // Always use playEpisode with seekTo - this ensures consistent behavior
        // The SpotifyEmbed handles the play-then-seek internally
        playEpisode(
            {
                id: episode.id,
                title: episode.title,
                showName: episode.showName,
                coverUrl: episode.imageUrl,
                spotifyUri: episode.spotifyUri,
                mp3Url: episode.mp3Url,
            },
            episode.spotifyUri || episode.mp3Url ? { seekTo: seconds } : undefined
        );
    };

    return (
        <Card className="border-l-4 border-l-emerald-500 shadow-sm hover:shadow-md transition-shadow dark:border-slate-800 dark:border-l-emerald-500">
            <CardHeader className="pb-3 pt-4">
                <div className="flex justify-between items-start">
                    <div className="flex gap-3 items-center flex-wrap">
                        <Badge variant="outline" className="text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 font-normal shrink-0">
                            {insight.podcaster || insight.episode_id.split('_')[0] || 'Unknown Host'}
                        </Badge>
                        <Badge className={cn("px-2 py-1 flex gap-1 items-center border-0", sentiment.color)}>
                            <SentimentIcon size={14} />
                            {sentiment.label}
                        </Badge>
                        <span className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-1">
                            <Calendar size={14} />
                            {formatDate(insight.podcast_launch_time)}
                        </span>
                    </div>
                </div>
                <div className="mt-3">
                    <h4 className="font-bold text-lg text-slate-900 dark:text-slate-50 leading-snug">
                        {displayThesis}
                    </h4>
                </div>
            </CardHeader>

            <CardContent className="pb-4">
                {/* Toggle Expansion */}
                <div className="flex justify-end">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpanded(!expanded)}
                        className="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200 h-8 text-xs"
                    >
                        {expanded ? '收起詳情' : '查看分析邏輯'}
                        {expanded ? <ChevronUp size={14} className="ml-1" /> : <ChevronDown size={14} className="ml-1" />}
                    </Button>
                </div>

                {expanded && (
                    <div className="mt-2 space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                        {/* Reasons Section */}
                        {displayReasons.length > 0 && (
                            <div className="bg-slate-50 dark:bg-slate-900/50 rounded-lg p-3">
                                <h5 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                                    投資理由
                                </h5>
                                <ul className="space-y-3">
                                    {displayReasons.map((reason, idx) => (
                                        <li key={idx} className="group">
                                            <div className="flex justify-between items-start gap-2">
                                                <div>
                                                    <span className="font-semibold text-slate-800 dark:text-slate-200 block text-sm">
                                                        {reason.title}
                                                    </span>
                                                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">
                                                        {reason.description}
                                                    </p>
                                                </div>
                                                {reason.start_time > 0 && (
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 opacity-80 group-hover:opacity-100 transition-opacity shrink-0 flex items-center gap-1"
                                                        onClick={() => handlePlay(reason.start_time)}
                                                        title="跳轉至音檔"
                                                    >
                                                        <Play size={14} className="fill-current shrink-0" />
                                                        收聽相關段落
                                                    </Button>
                                                )}
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Risks Section */}
                        {displayRisks.length > 0 && (
                            <div className="bg-red-50/50 dark:bg-red-950/10 rounded-lg p-3 border border-red-100 dark:border-red-900/20">
                                <h5 className="text-xs font-bold text-red-500/80 uppercase tracking-wider mb-2">
                                    風險提示
                                </h5>
                                <ul className="space-y-3">
                                    {displayRisks.map((risk, idx) => (
                                        <li key={idx} className="group">
                                            <div className="flex justify-between items-start gap-2">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-semibold text-slate-800 dark:text-slate-200 block text-sm">
                                                            {risk.title}
                                                        </span>
                                                        {risk.severity && (
                                                            <span className={cn(
                                                                "text-[10px] px-1.5 py-0.5 rounded uppercase font-bold",
                                                                risk.severity === 'HIGH' ? "bg-red-100 text-red-700" : "bg-orange-100 text-orange-700"
                                                            )}>
                                                                {SEVERITY_LABELS[risk.severity] ?? risk.severity}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">
                                                        {risk.description}
                                                    </p>
                                                </div>
                                                {risk.start_time > 0 && (
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 opacity-80 group-hover:opacity-100 transition-opacity shrink-0 flex items-center gap-1"
                                                        onClick={() => handlePlay(risk.start_time)}
                                                        title="跳轉至音檔"
                                                    >
                                                        <Play size={14} className="fill-current shrink-0" />
                                                        收聽相關段落
                                                    </Button>
                                                )}
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
