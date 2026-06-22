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
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Prompt tabs */}
      <div className="flex items-center justify-between border-b border-border px-4 pt-4">
        <div className="flex gap-1 overflow-x-auto">
          {promptNames.map((name) => (
            <button
              key={name}
              onClick={() => selectPrompt(name)}
              className={`whitespace-nowrap rounded-t-md px-3 py-2 text-base font-medium transition-colors ${
                activePrompt === name
                  ? 'border-b-2 border-accent-info text-accent-info'
                  : 'text-muted-foreground hover:text-foreground'
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
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-base font-medium transition-all ${
            dirty
              ? 'bg-accent-info text-accent-info-foreground hover:bg-accent-info/90'
              : 'cursor-not-allowed text-muted-foreground'
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
          className="h-[500px] w-full resize-y rounded-md border border-input bg-muted p-4 font-mono text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
          spellCheck={false}
        />
      </div>
    </div>
  );
};
