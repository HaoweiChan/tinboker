/**
 * Netdata embed component for admin dashboard.
 * Embeds Netdata dashboard via iframe when available.
 */

import React, { useState, useMemo } from 'react';
import { ExternalLink, AlertCircle } from 'lucide-react';

interface NetdataEmbedProps {
    /** Height of the iframe */
    height?: string;
}

// Netdata is proxied through Caddy at /netdata/* on each env's API host
const getNetdataUrl = (): string => {
    if (!import.meta.env.PROD) {
        return 'http://localhost:19999/';
    }
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        if (hostname.includes('dev.')) return 'https://dev-api.tinboker.com/netdata/';
        if (hostname.includes('staging')) return 'https://staging-api.tinboker.com/netdata/';
        if (hostname === 'tinboker.com' || hostname === 'www.tinboker.com') {
            return 'https://api.tinboker.com/netdata/';
        }
    }
    return 'https://dev-api.tinboker.com/netdata/';
};

export const NetdataEmbed: React.FC<NetdataEmbedProps> = ({
    height = '600px',
}) => {
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(true);

    // Memoize the netdata URL
    const baseUrl = useMemo(() => getNetdataUrl(), []);

    // Netdata URL for the dashboard with theme
    const netdataUrl = `${baseUrl}#menu_system;theme=slate`;

    const handleLoad = () => {
        setLoading(false);
    };

    const handleError = () => {
        setLoading(false);
        setError(true);
    };

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted p-8">
                <AlertCircle className="mb-3 h-8 w-8 text-muted-foreground" />
                <p className="mb-2 text-center text-base font-medium text-muted-foreground">
                    Netdata Not Configured
                </p>
                <p className="mb-4 text-center text-xs text-muted-foreground">
                    Please ensure Netdata container is running and Caddy reverse proxy is configured
                </p>
                <div className="flex gap-3">
                    <button
                        onClick={() => {
                            setError(false);
                            setLoading(true);
                        }}
                        className="text-base text-accent-info hover:text-accent-info/80"
                    >
                        Retry
                    </button>
                    <a
                        href="https://netdata.cloud/docs/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-base text-muted-foreground hover:text-foreground"
                    >
                        Docs <ExternalLink className="h-3 w-3" />
                    </a>
                </div>
            </div>
        );
    }

    return (
        <div className="relative" style={{ minHeight: height }}>
            {/* Loading overlay */}
            {loading && (
                <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-muted">
                    <div className="flex flex-col items-center gap-2">
                        <div className="h-8 w-8 animate-spin rounded-full border-4 border-accent-info border-t-transparent" />
                        <span className="text-base text-muted-foreground">
                            Loading Netdata...
                        </span>
                    </div>
                </div>
            )}

            {/* Netdata iframe */}
            <iframe
                src={netdataUrl}
                title="Netdata Dashboard"
                className="w-full rounded-lg border-0"
                style={{ height }}
                onLoad={handleLoad}
                onError={handleError}
                allow="fullscreen"
                sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
            />

            {/* Instructions banner */}
            <div className="mt-2 rounded-md bg-accent-info-soft p-3">
                <p className="text-xs text-accent-info">
                    💡 <strong>Tip:</strong> If you see a "Welcome to Netdata" screen, click <strong>"Skip and use the dashboard anonymously"</strong> at the bottom right to view metrics.
                </p>
            </div>

            {/* Open in new tab */}
            <div className="mt-2 flex justify-end">
                <a
                    href={baseUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                >
                    Open in new tab <ExternalLink className="h-3 w-3" />
                </a>
            </div>
        </div>
    );
};
