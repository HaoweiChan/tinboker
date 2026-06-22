/**
 * Status card component for admin dashboard.
 */

import React from 'react';

interface StatusCardProps {
    title: string;
    icon: React.ReactNode;
    status: string;
    value: string;
    subtitle: string;
    color: 'green' | 'yellow' | 'red';
    loading?: boolean;
}

export const StatusCard: React.FC<StatusCardProps> = ({
    title,
    icon,
    status,
    value,
    subtitle,
    color,
    loading,
}) => {
    const colorClasses = {
        green: 'bg-sentiment-bull-soft text-sentiment-bull ring-sentiment-bull/20',
        yellow: 'bg-primary/10 text-primary ring-primary/20',
        red: 'bg-destructive/10 text-destructive ring-destructive/20',
    };

    const dotClasses = {
        green: 'bg-sentiment-bull',
        yellow: 'bg-primary',
        red: 'bg-destructive',
    };

    return (
        <div className="rounded-lg border border-border bg-card p-4">
            {/* Header */}
            <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-muted-foreground">
                    {icon}
                    <span className="text-base font-medium">{title}</span>
                </div>
                <div className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${colorClasses[color]}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${dotClasses[color]}`} />
                    {status}
                </div>
            </div>

            {/* Value */}
            <div className="mb-1">
                {loading ? (
                    <div className="h-8 w-24 animate-pulse rounded bg-muted" />
                ) : (
                    <span className="text-2xl font-bold text-foreground">
                        {value}
                    </span>
                )}
            </div>

            {/* Subtitle */}
            {loading ? (
                <div className="h-4 w-32 animate-pulse rounded bg-muted" />
            ) : (
                <span className="text-base text-muted-foreground">
                    {subtitle}
                </span>
            )}
        </div>
    );
};
