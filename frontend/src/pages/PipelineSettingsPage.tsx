/**
 * Pipeline Settings page — admin-editable LLM model config + read-only view
 * of the full pipeline configuration. Overrides are stored in Postgres and
 * take effect on the next pipeline run (no restart needed).
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  RefreshCw,
  Save,
  CheckCircle2,
  Loader2,
  Zap,
  DollarSign,
  Clock,
  Target,
  FileText,
  Play,
} from 'lucide-react';
import { getPipelineSettings, updatePipelineSettings } from '@/services/api/pipeline';
import type { PipelineSettingsResponse, ModelOption } from '@/types/pipeline';
import { PipelinePromptsSection } from './PipelinePromptsSection';
import { PipelineTrialSection } from './PipelineTrialSection';

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

const ModelCard: React.FC<{
  model: ModelOption;
  selected: boolean;
  onSelect: () => void;
}> = ({ model, selected, onSelect }) => (
  <button
    onClick={onSelect}
    className={`w-full rounded-lg border p-3 text-left transition-all ${
      selected
        ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200 dark:border-blue-400 dark:bg-blue-900/20 dark:ring-blue-800'
        : 'border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600'
    }`}
  >
    <div className="flex items-center justify-between">
      <span className="font-medium text-gray-900 dark:text-white">{model.label}</span>
      {selected && <CheckCircle2 className="h-4 w-4 text-blue-500" />}
    </div>
    <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
      <span className="flex items-center gap-1">
        <DollarSign className="h-3 w-3" />
        {model.price_per_ep}/ep
      </span>
      <span className="flex items-center gap-1">
        <Target className="h-3 w-3" />
        {model.topic_score}
      </span>
      <span className="flex items-center gap-1">
        <Clock className="h-3 w-3" />
        {model.speed}
      </span>
    </div>
    <div className="mt-1 font-mono text-xs text-gray-400 dark:text-gray-500">{model.id}</div>
  </button>
);

const LLM_ROLES = [
  { key: 'extractor_model', label: '事件提取器', description: '從逐字稿提取結構化事件' },
  { key: 'writer_model', label: '報告撰寫', description: '生成中文摘要報告 (markdown)' },
  { key: 'marp_writer_model', label: '投影片撰寫', description: '生成 Marp 投影片 + Ticker 投影片' },
  { key: 'ticker_extractor_model', label: 'Ticker Insights', description: '提取個股觀點、情緒、目標價 → Firestore ticker_insights' },
  { key: 'key_insights_extractor_model', label: '重點洞察', description: '提取關鍵投資洞察 (key_insights)' },
] as const;

type Tab = 'models' | 'prompts' | 'trial';

export const PipelineSettingsPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('models');
  const [data, setData] = useState<PipelineSettingsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getPipelineSettings();
      setData(result);
      setOverrides(result.overrides || {});
      setDirty(false);
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to fetch pipeline settings:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const getModelForRole = (roleKey: string): string => {
    const llmOverrides = (overrides.llm || {}) as Record<string, unknown>;
    return (llmOverrides[roleKey] as string) || '';
  };

  const setModelForRole = (roleKey: string, modelId: string) => {
    const llmOverrides = ((overrides.llm || {}) as Record<string, unknown>);
    const newLlm = { ...llmOverrides, [roleKey]: modelId || undefined };
    // Remove keys with empty/undefined values
    Object.keys(newLlm).forEach((k) => {
      if (!newLlm[k]) delete newLlm[k];
    });
    const newOverrides = { ...overrides, llm: Object.keys(newLlm).length ? newLlm : undefined };
    if (!newOverrides.llm) delete newOverrides.llm;
    setOverrides(newOverrides);
    setDirty(true);
    setSaveSuccess(false);
  };

  const setAllModels = (modelId: string) => {
    const newLlm: Record<string, string> = {};
    LLM_ROLES.forEach((role) => {
      newLlm[role.key] = modelId;
    });
    setOverrides({ ...overrides, llm: newLlm });
    setDirty(true);
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      await updatePipelineSettings({ overrides });
      setSaveSuccess(true);
      setDirty(false);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to save pipeline settings:', error);
    } finally {
      setSaving(false);
    }
  };

  const availableModels = data?.available_models || [];

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-white">
            Pipeline 設定
            <Zap className="h-5 w-5 text-amber-500" />
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            LLM 模型與管線參數設定 · 下次執行時生效
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tab === 'models' && (
            <>
              <button
                onClick={fetchSettings}
                disabled={loading}
                className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                重新整理
              </button>
              <button
                onClick={handleSave}
                disabled={!dirty || saving}
                className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
                  dirty
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'cursor-not-allowed bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-600'
                }`}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : saveSuccess ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {saveSuccess ? '已儲存' : '儲存變更'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setTab('models')}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === 'models'
              ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <Zap className="h-3.5 w-3.5" />
          模型設定
        </button>
        <button
          onClick={() => setTab('prompts')}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === 'prompts'
              ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <FileText className="h-3.5 w-3.5" />
          Prompts
        </button>
        <button
          onClick={() => setTab('trial')}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
            tab === 'trial'
              ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          <Play className="h-3.5 w-3.5" />
          Trial Run
        </button>
      </div>

      {/* Tab: Prompts */}
      {tab === 'prompts' && <PipelinePromptsSection />}

      {/* Tab: Trial Run */}
      {tab === 'trial' && <PipelineTrialSection availableModels={availableModels} />}

      {/* Tab: Models */}
      {tab === 'models' && (
        <>
      {/* Status banner */}
      {data?.meta && (
        <div
          className={`mb-6 flex items-start gap-3 rounded-lg border p-4 ${
            data.meta.live
              ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-900/20'
              : 'border-blue-200 bg-blue-50 dark:border-blue-900/40 dark:bg-blue-900/20'
          }`}
        >
          {data.meta.live ? (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
          ) : (
            <Zap className="mt-0.5 h-5 w-5 shrink-0 text-blue-500" />
          )}
          <div className={`text-sm ${data.meta.live ? 'text-emerald-800 dark:text-emerald-300' : 'text-blue-800 dark:text-blue-300'}`}>
            <p className="font-medium">
              {data.meta.live
                ? 'Live — 即時讀取管線服務'
                : '可編輯 — 選擇模型後點擊「儲存變更」，下次管線執行時套用'}
            </p>
            {data.meta.has_overrides && (
              <p className="mt-0.5 text-emerald-600 dark:text-emerald-400">已套用管理員自訂覆蓋設定</p>
            )}
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      ) : data ? (
        <div className="space-y-8">
          {/* LLM Model Selection */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">LLM 模型設定</h2>
              {availableModels.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">一鍵全選：</span>
                  {availableModels.slice(0, 3).map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setAllModels(m.id)}
                      className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:border-blue-300 hover:bg-blue-50 dark:border-gray-700 dark:text-gray-400 dark:hover:border-blue-600 dark:hover:bg-blue-900/20"
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-6">
              {LLM_ROLES.map((role) => {
                const currentModel = getModelForRole(role.key);
                return (
                  <div key={role.key}>
                    <div className="mb-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">
                        {role.label}
                      </span>
                      <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                        {role.description}
                      </span>
                      {!currentModel && (
                        <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500 dark:bg-gray-800">
                          使用預設
                        </span>
                      )}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      {availableModels.map((model) => (
                        <ModelCard
                          key={model.id}
                          model={model}
                          selected={currentModel === model.id}
                          onSelect={() =>
                            setModelForRole(
                              role.key,
                              currentModel === model.id ? '' : model.id
                            )
                          }
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Model Benchmark */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
              模型效能比較
            </h2>
            <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
              基於 EP363 (21,162 字元, 2,152 句) 的實測數據 · 2026-06-07
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="pb-2 text-left font-medium text-gray-500 dark:text-gray-400">模型</th>
                    <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">價格 (in/out /1M)</th>
                    <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">速度</th>
                    <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">主題準確度</th>
                    <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">每集成本</th>
                    <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">vs 基準</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  <tr className="text-gray-900 dark:text-white">
                    <td className="py-2 font-medium">Xiaomi MiMo-V2.5 ⭐</td>
                    <td className="py-2 text-right font-mono text-xs">$0.140 / $0.280</td>
                    <td className="py-2 text-right">79s</td>
                    <td className="py-2 text-right font-semibold text-emerald-600">6/7</td>
                    <td className="py-2 text-right font-mono">$0.010</td>
                    <td className="py-2 text-right text-emerald-600">-75%</td>
                  </tr>
                  <tr className="text-gray-900 dark:text-white">
                    <td className="py-2 font-medium">DeepSeek V4 Flash</td>
                    <td className="py-2 text-right font-mono text-xs">$0.098 / $0.197</td>
                    <td className="py-2 text-right">170s</td>
                    <td className="py-2 text-right">5/7</td>
                    <td className="py-2 text-right font-mono">$0.007</td>
                    <td className="py-2 text-right text-emerald-600">-82%</td>
                  </tr>
                  <tr className="text-gray-700 dark:text-gray-300">
                    <td className="py-2">Gemini 2.5 Flash (前基準)</td>
                    <td className="py-2 text-right font-mono text-xs">$0.300 / $2.500</td>
                    <td className="py-2 text-right">208s</td>
                    <td className="py-2 text-right">5/7</td>
                    <td className="py-2 text-right font-mono">$0.040</td>
                    <td className="py-2 text-right">—</td>
                  </tr>
                  <tr className="text-gray-700 dark:text-gray-300">
                    <td className="py-2">DeepSeek V3.2</td>
                    <td className="py-2 text-right font-mono text-xs">$0.229 / $0.343</td>
                    <td className="py-2 text-right">401s</td>
                    <td className="py-2 text-right">4/7</td>
                    <td className="py-2 text-right font-mono">$0.014</td>
                    <td className="py-2 text-right text-emerald-600">-65%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Full config (read-only) */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
              完整管線設定（唯讀）
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(data.settings).map(([section, value]) => (
                <div
                  key={section}
                  className="rounded-lg border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50"
                >
                  <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    {section}
                  </h3>
                  <div className="space-y-1.5">
                    {value !== null && typeof value === 'object' && !Array.isArray(value) ? (
                      Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                        <div key={k} className="flex flex-wrap items-baseline gap-2">
                          <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                            {k}
                          </span>
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
          </div>
        </div>
      ) : (
        <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
          無法載入管線設定
        </div>
      )}
        </>
      )}
    </div>
  );
};
