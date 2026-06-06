/**
 * Read-only Pipeline Settings page.
 *
 * Renders a committed static snapshot of the agents' podcast pipeline config
 * (tinboker-agents/services/podcast/configs/default.yaml). Read-only by design — the
 * agents repo remains the source of truth.
 */

import React, { useEffect, useState } from 'react';
import { RefreshCw, Lock, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { getPipelineSettings } from '@/services/api/pipeline';
import type { PipelineSettingsResponse } from '@/types/pipeline';

/** Recursively render a config value (primitive, array, or nested object) read-only. */
const ConfigValue: React.FC<{ value: unknown }> = ({ value }) => {
  if (Array.isArray(value)) {
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <span
            key={i}
            className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200"
          >
            {String(v)}
          </span>
        ))}
      </span>
    );
  }
  if (value !== null && typeof value === 'object') {
    return (
      <div className="mt-1 space-y-1 border-l border-gray-200 pl-3 dark:border-gray-700">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">{k}</span>
            <ConfigValue value={v} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <span className="font-mono text-sm text-gray-900 dark:text-white">{String(value)}</span>
  );
};

export const PipelineSettingsPage: React.FC = () => {
  const [data, setData] = useState<PipelineSettingsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      setData(await getPipelineSettings());
    } catch (error) {
      console.error('Failed to fetch pipeline settings:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-white">
            Pipeline Settings
            <Lock className="h-4 w-4 text-gray-400" />
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Read-only view of the content pipeline configuration
          </p>
        </div>
        <button
          onClick={fetchSettings}
          className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Source banner — live from the pipeline service, or snapshot fallback */}
      {data?.meta &&
        (data.meta.live ? (
          <div className="mb-6 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/40 dark:bg-emerald-900/20">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
            <div className="text-sm text-emerald-800 dark:text-emerald-300">
              <p className="font-medium">Live — read directly from the pipeline service</p>
              <p className="mt-0.5">Read-only. The tinboker-agents repo is the source of truth.</p>
              <p className="mt-1 text-xs">
                Source: <code className="font-mono">{data.meta.source}</code>
                {data.meta.fetched_from ? <> · {data.meta.fetched_from}</> : null}
              </p>
            </div>
          </div>
        ) : (
          <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/40 dark:bg-amber-900/20">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
            <div className="text-sm text-amber-800 dark:text-amber-300">
              <p className="font-medium">Showing committed snapshot (pipeline service unreachable)</p>
              {data.meta.note ? <p className="mt-0.5">{data.meta.note}</p> : null}
              <p className="mt-1 text-xs">
                Source: <code className="font-mono">{data.meta.source}</code>
                {data.meta.snapshot_date ? (
                  <> · snapshot {data.meta.snapshot_date} ({data.meta.snapshot_of_commit})</>
                ) : null}
              </p>
            </div>
          </div>
        ))}

      {/* Sections */}
      {loading && !data ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      ) : data ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(data.settings).map(([section, value]) => (
            <div
              key={section}
              className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
            >
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {section}
              </h3>
              <div className="space-y-1.5">
                {value !== null && typeof value === 'object' && !Array.isArray(value) ? (
                  Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                    <div key={k} className="flex flex-wrap items-baseline gap-2">
                      <span className="font-mono text-xs text-gray-500 dark:text-gray-400">{k}</span>
                      <ConfigValue value={v} />
                    </div>
                  ))
                ) : (
                  <ConfigValue value={value} />
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
          Could not load pipeline settings
        </div>
      )}
    </div>
  );
};
