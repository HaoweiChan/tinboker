
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageCircle, Clock, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, Button } from '@/components/ui';
import { recommendationService } from '@/services/recommendationService';
import type { TickerBuzz } from '@/services/types';
import { cn } from '@/lib/utils';

interface WeeklyBuzzWidgetProps {
    className?: string;
    isMobile?: boolean; // Mobile layout prop
}

export const WeeklyBuzzWidget: React.FC<WeeklyBuzzWidgetProps> = ({ className, isMobile }) => {
    const [buzz, setBuzz] = useState<TickerBuzz[]>([]);
    const navigate = useNavigate();

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const data = await recommendationService.getMostDiscussedTickers(30);
                if (!cancelled) setBuzz(data);
            } catch {
                if (!cancelled) setBuzz([]);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    const getSentimentColor = (score: number) => {
        if (score > 0.6) return 'text-emerald-500';
        if (score < 0.4) return 'text-red-500';
        return 'text-slate-400';
    };

    const handleTickerClick = (ticker: string) => {
        navigate(`/stock/${ticker}`);
    };

    if (buzz.length === 0) return null;

    return (
        <Card className={cn("border-slate-200 dark:border-slate-800", className)}>
            <CardHeader className="pb-3 border-b border-slate-100 dark:border-slate-800">
                <CardTitle className="flex items-center gap-2 text-lg">
                    <MessageCircle className="text-accent-info" size={20} />
                    <span>本週市場焦點</span>
                    <span className="text-xs font-normal text-slate-400 ml-auto bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-full">
                        Top 10 (30d)
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 px-0">
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {buzz.map((item, idx) => (
                        <li
                            key={item.ticker}
                            className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer"
                            onClick={() => handleTickerClick(item.ticker)}
                        >
                            <div className="flex items-center p-4 gap-4">
                                <span className="font-mono text-slate-300 text-sm font-bold w-4">
                                    {idx + 1}
                                </span>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-slate-900 dark:text-slate-100">{item.ticker}</span>
                                        <span className={cn("text-xs font-semibold", getSentimentColor(item.sentiment_score))}>
                                            {(item.sentiment_score * 100).toFixed(0)}% Bullish
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 mt-1">
                                        <div className="flex items-center text-xs text-slate-500">
                                            <MessageCircle size={10} className="mr-1" />
                                            {item.count} mentions
                                        </div>
                                        <div className="flex items-center text-xs text-slate-400">
                                            <Clock size={10} className="mr-1" />
                                            {new Date(item.last_mentioned).toLocaleDateString()}
                                        </div>
                                    </div>
                                </div>

                                <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-400 hover:text-accent-info">
                                    <ArrowRight size={16} />
                                </Button>
                            </div>
                        </li>
                    ))}
                </ul>
                {isMobile && (
                    <div className="p-4 border-t border-slate-100 dark:border-slate-800">
                        <Button variant="outline" className="w-full text-xs h-9">
                            查看完整排行
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
