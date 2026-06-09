/**
 * Pipeline Prompts section — inline editable YAML prompts.
 */

import React, { useEffect, useState } from 'react';
import { Save, Loader2, CheckCircle2, FileText } from 'lucide-react';
import { getPipelinePrompts, updatePipelinePrompt } from '@/services/api/pipeline';

const ROLE_LABELS: Record<string, string> = {
  extractor: '事件提取器',
  writer: '報告撰寫',
  marp_writer: '投影片撰寫 (Marp)',
  ticker_extractor: 'Ticker Insights',
  key_insights_extractor: '重點洞察',
};

export const PipelinePromptsSection: React.FC = () => {
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [promptNames, setPromptNames] = useState<string[]>([]);
  const [activePrompt, setActivePrompt] = useState<string>('');
  const [editedContent, setEditedContent] = useState<string>('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await getPipelinePrompts();
        setPrompts(data.prompts);
        setPromptNames(data.prompt_names);
        if (data.prompt_names.length > 0) {
          const first = data.prompt_names[0];
          setActivePrompt(first);
          setEditedContent(data.prompts[first] || '');
        }
      } catch (e) {
        if (import.meta.env.DEV) console.error('Failed to load prompts:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectPrompt = (name: string) => {
    if (dirty && !confirm('尚未儲存，確定切換？')) return;
    setActivePrompt(name);
    setEditedContent(prompts[name] || '');
    setDirty(false);
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updatePipelinePrompt(activePrompt, editedContent);
      setPrompts((prev) => ({ ...prev, [activePrompt]: editedContent }));
      setDirty(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e) {
      if (import.meta.env.DEV) console.error('Failed to save prompt:', e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      {/* Prompt tabs */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 pt-4 dark:border-gray-700">
        <div className="flex gap-1 overflow-x-auto">
          {promptNames.map((name) => (
            <button
              key={name}
              onClick={() => selectPrompt(name)}
              className={`whitespace-nowrap rounded-t-md px-3 py-2 text-sm font-medium transition-colors ${
                activePrompt === name
                  ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              <FileText className="mr-1.5 inline h-3.5 w-3.5" />
              {ROLE_LABELS[name] || name}
            </button>
          ))}
        </div>
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
            dirty
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'cursor-not-allowed text-gray-400 dark:text-gray-600'
          }`}
        >
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : saveSuccess ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <Save className="h-3.5 w-3.5" />
          )}
          {saveSuccess ? '已儲存' : '儲存'}
        </button>
      </div>

      {/* Editor */}
      <div className="p-4">
        <textarea
          value={editedContent}
          onChange={(e) => {
            setEditedContent(e.target.value);
            setDirty(e.target.value !== prompts[activePrompt]);
            setSaveSuccess(false);
          }}
          className="h-[500px] w-full resize-y rounded-md border border-gray-200 bg-gray-50 p-4 font-mono text-sm text-gray-800 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200"
          spellCheck={false}
        />
      </div>
    </div>
  );
};
