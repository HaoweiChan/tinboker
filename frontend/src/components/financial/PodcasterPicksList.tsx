import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, ArrowUpRight, TrendingUp, TrendingDown, Minus, Play, ChevronDown, ChevronUp } from 'lucide-react';
import { Card, Button, Badge } from '@/components/ui';
import { recommendationService } from '@/services/recommendationService';
import type { TickerRecommendation } from '@/services/types';
import { cn } from '@/lib/utils';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { Episode as MockEpisode } from '@/data/mockData';

interface PodcasterPicksListProps {
    podcasterName: string;
    /** Episodes for this podcaster (from PodcasterPage). Used to launch podcast at reason/risk timestamp. */
    episodes?: MockEpisode[];
    /** Optional podcast slug/id; passed to recommendations API for episode_id matching when available. */
    podcastSlug?: string;
}

export const PodcasterPicksList: React.FC<PodcasterPicksListProps> = ({ podcasterName, episodes = [], podcastSlug }) => {
    const [picks, setPicks] = useState<TickerRecommendation[]>([]);
    const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
    const navigate = useNavigate();
    const playEpisode = usePlayerStore((s) => s.playEpisode);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const data = await recommendationService.getRecommendationsByPodcaster(podcasterName, {
                    ...(podcastSlug && { podcast_slug: podcastSlug }),
                });
                if (!cancelled) setPicks(data);
            } catch {
                if (!cancelled) setPicks([]);
            }
        })();
        return () => { cancelled = true; };
    }, [podcasterName, podcastSlug]);

    const handleTickerClick = (ticker: string) => {
        navigate(`/stock/${ticker}`);
    };

    const toggleExpand = (e: React.MouseEvent, id: number) => {
        e.stopPropagation();
        setExpandedItems(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    // Backend provides start_time in milliseconds; convert to seconds for GlobalPlayer
    const handlePlayTimestamp = (e: React.MouseEvent, episodeId: string, timestampMs: number) => {
        e.stopPropagation();
        const episode = episodes.find((ep) => ep.id === episodeId);
        if (!episode) {
            window.open(`https://open.spotify.com/search/${encodeURIComponent(episodeId)}`, '_blank');
            return;
        }

        const seconds = Math.floor(timestampMs / 1000);

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

    const getSentimentStyle = (label: string, score: number | string) => {
        const numScore = Number(score);
        if (label === 'POSITIVE' || numScore > 0.6) return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
        if (label === 'NEGATIVE' || numScore < 0.4) return 'text-red-500 bg-red-500/10 border-red-500/20';
        return 'text-slate-500 bg-slate-500/10 border-slate-500/20';
    };

    const getSentimentIcon = (label: string, score: number | string) => {
        const numScore = Number(score);
        if (label === 'POSITIVE' || numScore > 0.6) return <TrendingUp size={14} className="mr-1" />;
        if (label === 'NEGATIVE' || numScore < 0.4) return <TrendingDown size={14} className="mr-1" />;
        return <Minus size={14} className="mr-1" />;
    };

    if (picks.length === 0) {
        return (
            <div className="text-center py-8 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                <p className="text-slate-500 text-sm">此創作者近期無標的分析紀錄。</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h3 className="text-lg font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50">
                <Target className="text-emerald-500" size={20} />
                Recent Picks ({picks.length})
            </h3>

            <div className="grid grid-cols-1 gap-3">
                {picks.map((pick) => {
                    const isExpanded = expandedItems.has(pick.id);
                    return (
                        <Card
                            key={pick.id}
                            className={cn(
                                "p-4 transition-all border-l-4 border-l-transparent hover:border-l-emerald-500 group",
                                isExpanded ? "ring-1 ring-emerald-500/20" : "hover:shadow-md"
                            )}
                        >
                            {/* Header Row */}
                            <div
                                className="cursor-pointer"
                                onClick={() => handleTickerClick(pick.ticker)}
                            >
                                <div className="flex justify-between items-start">
                                    <div>
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-bold text-lg text-slate-900 dark:text-slate-50 group-hover:text-emerald-600 transition-colors">
                                                {pick.ticker}
                                            </span>
                                            <Badge variant="outline" className={cn("font-normal border", getSentimentStyle(pick.sentiment, pick.sentiment_score))}>
                                                {getSentimentIcon(pick.sentiment, pick.sentiment_score)}
                                                {pick.sentiment || 'NEUTRAL'}
                                            </Badge>
                                        </div>
                                        <p className="text-xs text-slate-500 mb-2">
                                            {new Date(pick.podcast_launch_time).toLocaleDateString()} • {pick.time_horizon || 'Medium Term'}
                                        </p>
                                        <p className={cn(
                                            "text-sm text-slate-700 dark:text-slate-300 leading-relaxed",
                                            !isExpanded && "line-clamp-2"
                                        )}>
                                            {pick.bluf_thesis || "Viewing recommendation details..."}
                                        </p>
                                    </div>
                                    <div className="flex flex-col gap-1">
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="text-slate-300 group-hover:text-emerald-500"
                                            onClick={(e) => { e.stopPropagation(); handleTickerClick(pick.ticker); }}
                                        >
                                            <ArrowUpRight size={18} />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                            onClick={(e) => toggleExpand(e, pick.id)}
                                        >
                                            {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                                        </Button>
                                    </div>
                                </div>
                            </div>

                            {/* Expanded Content: Reasons & Risks */}
                            {isExpanded && (
                                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 animate-in fade-in slide-in-from-top-1">
                                    {/* Reasons */}
                                    {pick.reasons && pick.reasons.length > 0 && (
                                        <div className="mb-4">
                                            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                                                看多理由 (Reasons)
                                            </h4>
                                            <ul className="space-y-2">
                                                {pick.reasons.map((reason, idx) => (
                                                    <li key={idx} className="bg-slate-50 dark:bg-slate-900/50 rounded p-2 text-sm flex gap-2 justify-between group/item">
                                                        <span className="text-slate-700 dark:text-slate-300">{reason.title}</span>
                                                        <Button
                                                            size="icon"
                                                            variant="ghost"
                                                            className="h-5 w-5 opacity-40 group-hover/item:opacity-100 hover:text-emerald-500 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                                                            title="Play segment"
                                                            onClick={(e) => handlePlayTimestamp(e, pick.episode_id, reason.start_time)}
                                                        >
                                                            <Play size={12} className="fill-current" />
                                                        </Button>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}

                                    {/* Risks */}
                                    {pick.risks && pick.risks.length > 0 && (
                                        <div>
                                            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                                                風險提示 (Risks)
                                            </h4>
                                            <ul className="space-y-2">
                                                {pick.risks.map((risk, idx) => (
                                                    <li key={idx} className="bg-red-50 dark:bg-red-900/10 rounded p-2 text-sm flex gap-2 justify-between group/item border border-red-100 dark:border-red-900/20">
                                                        <span className="text-slate-700 dark:text-slate-300">{risk.title}</span>
                                                        <Button
                                                            size="icon"
                                                            variant="ghost"
                                                            className="h-5 w-5 opacity-40 group-hover/item:opacity-100 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                                                            title="Play segment"
                                                            onClick={(e) => handlePlayTimestamp(e, pick.episode_id, risk.start_time)}
                                                        >
                                                            <Play size={12} className="fill-current" />
                                                        </Button>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}
                        </Card>
                    );
                })}
            </div>
        </div>
    );
};
