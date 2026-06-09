/**
 * Pipeline Trial Run section — ad-hoc model testing with result comparison.
 */

import React, { useEffect, useState } from 'react';
import { Play, Trash2, Loader2, Clock } from 'lucide-react';
import {
  startTrialRun,
  getTrialRuns,
  deleteTrialRun,
  type TrialRunResult,
} from '@/services/api/pipeline';
import type { ModelOption } from '@/types/pipeline';

const ROLES = [
  { id: 'marp_writer', label: '投影片 (Marp)' },
  { id: 'writer', label: '報告撰寫' },
  { id: 'ticker_extractor', label: 'Ticker Insights' },
  { id: 'key_insights_extractor', label: '重點洞察' },
  { id: 'extractor', label: '事件提取' },
];

interface Props {
  availableModels: ModelOption[];
}

export const PipelineTrialSection: React.FC<Props> = ({ availableModels }) => {
  const [selectedModel, setSelectedModel] = useState(availableModels[0]?.id || '');
  const [selectedRole, setSelectedRole] = useState('marp_writer');
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<TrialRunResult[]>([]);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  useEffect(() => {
    loadRuns();
  }, []);

  const loadRuns = async () => {
    try {
      const data = await getTrialRuns();
      setRuns(data.runs);
    } catch (e) {
      if (import.meta.env.DEV) console.error('Failed to load trial runs:', e);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    try {
      const result = await startTrialRun({
        model_id: selectedModel,
        role: selectedRole,
      });
      setRuns((prev) => [result, ...prev]);
      setExpandedRun(result.run_id);
    } catch (e) {
      if (import.meta.env.DEV) console.error('Trial run failed:', e);
    } finally {
      setRunning(false);
    }
  };

  const handleDelete = async (runId: string) => {
    try {
      await deleteTrialRun(runId);
      setRuns((prev) => prev.filter((r) => r.run_id !== runId));
    } catch (e) {
      if (import.meta.env.DEV) console.error('Delete failed:', e);
    }
  };

  const modelLabel = (id: string) =>
    availableModels.find((m) => m.id === id)?.label || id;

  return (
    <div className="space-y-6">
      {/* Run controls */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          Trial Run — 模型測試
        </h3>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          選擇模型和角色，對隨機集數執行一次 LLM 呼叫以預覽輸出品質
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
              模型
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} ({m.price_per_ep}/ep, {m.speed})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
              角色
            </label>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            >
              {ROLES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedModel}
            className="flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {running ? '執行中...' : '執行 Trial Run'}
          </button>
        </div>
      </div>

      {/* Results */}
      {runs.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              測試結果 ({runs.length})
            </h3>
            {runs.length > 3 && (
              <button
                onClick={() => {
                  if (confirm('清除所有測試結果？')) {
                    runs.forEach((r) => deleteTrialRun(r.run_id));
                    setRuns([]);
                  }
                }}
                className="text-xs text-red-500 hover:text-red-700"
              >
                清除全部
              </button>
            )}
          </div>
          <div className="space-y-3">
            {runs.map((run) => (
              <div
                key={run.run_id}
                className="rounded-lg border border-gray-100 dark:border-gray-800"
              >
                {/* Run header */}
                <div
                  className="flex cursor-pointer items-center justify-between p-3 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                  onClick={() =>
                    setExpandedRun(expandedRun === run.run_id ? null : run.run_id)
                  }
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        run.error ? 'bg-red-500' : 'bg-emerald-500'
                      }`}
                    />
                    <span className="font-medium text-gray-800 dark:text-gray-200">
                      {modelLabel(run.model_id)}
                    </span>
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500 dark:bg-gray-800">
                      {ROLES.find((r) => r.id === run.role)?.label || run.role}
                    </span>
                    {run.episode_title && (
                      <span className="max-w-[200px] truncate text-xs text-gray-400">
                        {run.episode_title}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1 text-xs text-gray-500">
                      <Clock className="h-3 w-3" />
                      {run.elapsed_ms ? `${(run.elapsed_ms / 1000).toFixed(1)}s` : '—'}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(run.run_id);
                      }}
                      className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Expanded content */}
                {expandedRun === run.run_id && (
                  <div className="border-t border-gray-100 p-4 dark:border-gray-800">
                    {run.error ? (
                      <pre className="rounded bg-red-50 p-3 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
                        {run.error}
                      </pre>
                    ) : run.output ? (
                      <div className="space-y-3">
                        {/* Slides preview for marp_writer */}
                        {run.role === 'marp_writer' && Array.isArray(run.output.slides) && (
                          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                            {(run.output.slides as Array<Record<string, unknown>>).map(
                              (slide, i) => (
                                <div
                                  key={i}
                                  className="rounded-lg border border-gray-700 bg-[#0e1014] p-4"
                                >
                                  <h4 className="mb-2 font-bold text-white">
                                    {slide.heading as string}
                                  </h4>
                                  {Array.isArray(slide.bullet_points) && (
                                    <ul className="space-y-1.5">
                                      {(slide.bullet_points as string[]).map((bp, j) => (
                                        <li
                                          key={j}
                                          className="border-l-2 border-blue-500 pl-2 text-xs text-gray-300"
                                        >
                                          {bp}
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )
                            )}
                          </div>
                        )}
                        {/* Generic JSON output for other roles */}
                        {run.role !== 'marp_writer' && (
                          <pre className="max-h-[400px] overflow-auto rounded bg-gray-50 p-3 font-mono text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                            {JSON.stringify(run.output, null, 2)}
                          </pre>
                        )}
                        {/* Raw JSON toggle for marp_writer too */}
                        {run.role === 'marp_writer' && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs text-gray-500">
                              顯示原始 JSON
                            </summary>
                            <pre className="mt-2 max-h-[300px] overflow-auto rounded bg-gray-50 p-3 font-mono text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                              {JSON.stringify(run.output, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500">無輸出</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
