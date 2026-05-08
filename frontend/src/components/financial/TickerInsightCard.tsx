import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Play, TrendingUp, TrendingDown, Minus, Calendar } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Badge } from '@/components/ui';
import type { TickerRecommendation } from '@/services/types';
import { cn } from '@/lib/utils';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { Episode as MockEpisode } from '@/data/mockData';

interface TickerInsightCardProps {
    recommendation: TickerRecommendation;
    /** Episodes for this ticker (from StockDashboard). Used to launch podcast at reason/risk timestamp. */
    episodes?: MockEpisode[];
}

export const TickerInsightCard: React.FC<TickerInsightCardProps> = ({ recommendation, episodes = [] }) => {
    const [expanded, setExpanded] = useState(false);
    const playEpisode = usePlayerStore((s) => s.playEpisode);

    // Format sentiment
    const getSentimentConfig = (score: number | string, label: string) => {
        const numScore = Number(score);
        if (label === 'POSITIVE' || numScore > 0.6) return { color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400', icon: TrendingUp, label: '看多 (Bullish)' };
        if (label === 'NEGATIVE' || numScore < 0.4) return { color: 'text-red-500 bg-red-50 dark:bg-red-950/30 dark:text-red-400', icon: TrendingDown, label: '看空 (Bearish)' };
        return { color: 'text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-400', icon: Minus, label: '中立 (Neutral)' };
    };

    const sentiment = getSentimentConfig(recommendation.sentiment_score, recommendation.sentiment);
    const SentimentIcon = sentiment.icon;

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('zh-TW', { month: 'long', day: 'numeric', year: 'numeric' });
    };

    // Backend provides start_time in milliseconds; convert to seconds for GlobalPlayer
    const handlePlay = (startTimeMs: number) => {
        const seconds = Math.floor(startTimeMs / 1000);
        const episode = episodes.find((ep) => ep.id === recommendation.episode_id);
        if (!episode) {
            window.open(`https://open.spotify.com/search/${encodeURIComponent(recommendation.episode_id)}`, '_blank');
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
            },
            episode.spotifyUri ? { seekTo: seconds } : undefined
        );
    };

    return (
        <Card className="border-l-4 border-l-emerald-500 shadow-sm hover:shadow-md transition-shadow dark:border-slate-800 dark:border-l-emerald-500">
            <CardHeader className="pb-3 pt-4">
                <div className="flex justify-between items-start">
                    <div className="flex gap-3 items-center flex-wrap">
                        <Badge variant="outline" className="text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 font-normal shrink-0">
                            {recommendation.podcaster || recommendation.episode_id.split('_')[0] || 'Unknown Host'}
                        </Badge>
                        <Badge className={cn("px-2 py-1 flex gap-1 items-center border-0", sentiment.color)}>
                            <SentimentIcon size={14} />
                            {sentiment.label}
                        </Badge>
                        <span className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-1">
                            <Calendar size={14} />
                            {formatDate(recommendation.podcast_launch_time)}
                        </span>
                    </div>
                </div>
                <div className="mt-3">
                    <h4 className="font-bold text-lg text-slate-900 dark:text-slate-50 leading-snug">
                        {recommendation.bluf_thesis || "No explicit thesis provided."}
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
                        {recommendation.reasons && recommendation.reasons.length > 0 && (
                            <div className="bg-slate-50 dark:bg-slate-900/50 rounded-lg p-3">
                                <h5 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                                    投資理由 (Reasons)
                                </h5>
                                <ul className="space-y-3">
                                    {recommendation.reasons.map((reason, idx) => (
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
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 opacity-80 group-hover:opacity-100 transition-opacity shrink-0 flex items-center gap-1"
                                                    onClick={() => handlePlay(reason.start_time)}
                                                    title="跳轉至音檔"
                                                >
                                                    <Play size={14} className="fill-current shrink-0" />
                                                    收聽該podcast段落
                                                </Button>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Risks Section */}
                        {recommendation.risks && recommendation.risks.length > 0 && (
                            <div className="bg-red-50/50 dark:bg-red-950/10 rounded-lg p-3 border border-red-100 dark:border-red-900/20">
                                <h5 className="text-xs font-bold text-red-500/80 uppercase tracking-wider mb-2">
                                    風險提示 (Risks)
                                </h5>
                                <ul className="space-y-3">
                                    {recommendation.risks.map((risk, idx) => (
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
                                                                {risk.severity}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">
                                                        {risk.description}
                                                    </p>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 opacity-80 group-hover:opacity-100 transition-opacity shrink-0 flex items-center gap-1"
                                                    onClick={() => handlePlay(risk.start_time)}
                                                    title="跳轉至音檔"
                                                >
                                                    <Play size={14} className="fill-current shrink-0" />
                                                    收聽該podcast段落
                                                </Button>
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
