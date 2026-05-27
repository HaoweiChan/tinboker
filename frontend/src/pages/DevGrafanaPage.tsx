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
        <BarChart2 className="h-6 w-6 text-gray-500 dark:text-gray-400" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Grafana Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Monitoring &amp; metrics — dev environment
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        {error ? (
          <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-8 dark:border-gray-600 dark:bg-gray-800/50">
            <AlertCircle className="mb-3 h-8 w-8 text-gray-400" />
            <p className="mb-2 text-center text-sm font-medium text-gray-600 dark:text-gray-400">
              Grafana Not Reachable
            </p>
            <p className="mb-4 text-center text-xs text-gray-500 dark:text-gray-500">
              Ensure Grafana is running and accessible at{' '}
              <code className="rounded bg-gray-100 px-1 dark:bg-gray-700">{baseUrl}</code>
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setError(false);
                  setLoading(true);
                }}
                className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                Retry
              </button>
              <a
                href={baseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-700 dark:text-gray-400"
              >
                Open directly <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        ) : (
          <div className="relative" style={{ minHeight: '700px' }}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-700">
                <div className="flex flex-col items-center gap-2">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-violet-500 border-t-transparent" />
                  <span className="text-sm text-gray-500 dark:text-gray-400">
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
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
          >
            Open in new tab <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>
    </div>
  );
};
