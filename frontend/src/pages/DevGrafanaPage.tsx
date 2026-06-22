import React, { useState, useMemo } from 'react';
import { ExternalLink, AlertCircle, BarChart2 } from 'lucide-react';

const getGrafanaUrl = (): string => {
  if (typeof window !== 'undefined') {
    const { hostname } = window.location;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:3000/';
    }
    if (hostname.includes('dev.tinboker.com')) {
      return 'https://dev-api.tinboker.com/grafana/';
    }
  }
  return 'https://dev-api.tinboker.com/grafana/';
};

export const DevGrafanaPage: React.FC = () => {
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const baseUrl = useMemo(() => getGrafanaUrl(), []);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex items-center gap-3">
        <BarChart2 className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Grafana Dashboard</h1>
          <p className="text-base text-muted-foreground">
            Monitoring &amp; metrics — dev environment
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        {error ? (
          <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/50 p-8">
            <AlertCircle className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="mb-2 text-center text-base font-medium text-foreground">
              Grafana Not Reachable
            </p>
            <p className="mb-4 text-center text-xs text-muted-foreground">
              Ensure Grafana is running and accessible at{' '}
              <code className="rounded bg-muted px-1">{baseUrl}</code>
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setError(false);
                  setLoading(true);
                }}
                className="text-base text-accent-info hover:text-accent-info/70"
              >
                Retry
              </button>
              <a
                href={baseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-base text-muted-foreground hover:text-foreground"
              >
                Open directly <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        ) : (
          <div className="relative" style={{ minHeight: '700px' }}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-muted">
                <div className="flex flex-col items-center gap-2">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-accent-info border-t-transparent" />
                  <span className="text-base text-muted-foreground">
                    Loading Grafana...
                  </span>
                </div>
              </div>
            )}
            <iframe
              src={baseUrl}
              title="Grafana Dashboard"
              className="w-full rounded-lg border-0"
              style={{ height: '700px' }}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false);
                setError(true);
              }}
              allow="fullscreen"
              sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
            />
          </div>
        )}

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
    </div>
  );
};
