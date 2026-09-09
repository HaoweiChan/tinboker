import React, { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TimeframeOption } from '@/services/types';

interface ChartControlsProps {
    timeframe: TimeframeOption;
    onTimeframeChange: (timeframe: TimeframeOption) => void;
    subChart: string;
    onSubChartChange: (subChart: string) => void;
    activeIndicators: string[];
    onToggleIndicator: (indicator: string, active: boolean) => void;
    /** Stock card PNG to offer as a download. Omit to hide the button. */
    downloadUrl?: string;
}

const TIMEFRAMES: { value: TimeframeOption; label: string }[] = [
    { value: '1D', label: '日' },
    { value: '1W', label: '週' },
    { value: '1M', label: '月' },
];

const SUB_CHARTS: Record<string, string> = {
    Volume: '成交量', KD: 'KD', MACD: 'MACD', RSI: 'RSI', Bias: '乖離率',
};

const INDICATORS: { key: string; label: string; dot: string }[] = [
    { key: 'MA5', label: '5MA', dot: 'bg-[#ff9800]' },
    { key: 'MA20', label: '20MA', dot: 'bg-[#a78bfa]' },
    { key: 'MA60', label: '60MA', dot: 'bg-[#00bcd4]' },
];

/**
 * One row: timeframe on the left, everything else behind a single 指標 button.
 *
 * It used to be three stacked rows on a phone — timeframes, three MA checkboxes, then a
 * sub-chart dropdown — which pushed the chart itself down the card and left it short and
 * cramped. Controls are not why anyone opens a stock page.
 *
 * The popover opens on click rather than on hover. The old one used `group-hover`, which
 * a touch screen has no way to trigger, so the sub-chart picker was effectively unusable
 * on a phone.
 */
export const ChartControls: React.FC<ChartControlsProps> = ({
    timeframe,
    onTimeframeChange,
    subChart,
    onSubChartChange,
    activeIndicators,
    onToggleIndicator,
    downloadUrl,
}) => {
    const [open, setOpen] = useState(false);
    const popRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent) => {
            if (popRef.current && !popRef.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, [open]);

    return (
        <div className="flex items-center justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-1">
                {TIMEFRAMES.map((tf) => (
                    <button
                        key={tf.value}
                        onClick={() => onTimeframeChange(tf.value)}
                        className={cn(
                            'px-2.5 py-0.5 text-sm rounded transition-colors min-w-[2rem]',
                            timeframe === tf.value
                                ? 'bg-primary text-primary-foreground font-semibold'
                                : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {tf.label}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-2">
                {downloadUrl && (
                    // A plain anchor, not a fetch/blob dance: the backend sends
                    // Content-Disposition, which is what actually triggers the save. The
                    // `download` attribute is kept for the same-origin dev proxy, where
                    // it supplies the filename; cross-origin the browser ignores it.
                    <a
                        href={downloadUrl}
                        download
                        className="flex items-center gap-1 px-1.5 py-0.5 text-sm text-muted-foreground hover:text-foreground rounded hover:bg-muted transition-colors"
                        title="下載這檔股票的走勢圖卡"
                    >
                        <Download className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">圖卡</span>
                    </a>
                )}

                <div className="relative" ref={popRef}>
                    <button
                        onClick={() => setOpen((v) => !v)}
                        aria-expanded={open}
                        className="flex items-center gap-1 px-1.5 py-0.5 text-sm text-foreground rounded hover:bg-muted transition-colors"
                    >
                        <span>指標</span>
                        <span className="text-muted-foreground">{SUB_CHARTS[subChart] ?? subChart}</span>
                        <svg className={cn('w-3 h-3 text-muted-foreground transition-transform', open && 'rotate-180')} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                    </button>

                    {open && (
                        <div className="absolute right-0 top-full mt-1 w-40 py-1.5 bg-popover rounded-md shadow-lg border border-border z-50">
                            <div className="px-3 pb-1 text-2xs text-muted-foreground">均線</div>
                            {INDICATORS.map((ind) => {
                                const on = activeIndicators.includes(ind.key);
                                return (
                                    <button
                                        key={ind.key}
                                        onClick={() => onToggleIndicator(ind.key, !on)}
                                        className="w-full flex items-center gap-2 px-3 py-1 text-xs text-left text-foreground hover:bg-muted transition-colors"
                                    >
                                        <span className={cn('w-3.5 h-3.5 rounded border flex items-center justify-center', on ? `${ind.dot} border-transparent` : 'border-border')}>
                                            {on && <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>}
                                        </span>
                                        {ind.label}
                                    </button>
                                );
                            })}
                            <div className="mt-1.5 pt-1.5 border-t border-border px-3 pb-1 text-2xs text-muted-foreground">副圖</div>
                            {Object.entries(SUB_CHARTS).map(([key, label]) => (
                                <button
                                    key={key}
                                    onClick={() => { onSubChartChange(key); setOpen(false); }}
                                    className={cn(
                                        'w-full text-left px-3 py-1 text-xs transition-colors',
                                        subChart === key ? 'bg-muted text-accent-info font-medium' : 'text-muted-foreground hover:bg-muted',
                                    )}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
