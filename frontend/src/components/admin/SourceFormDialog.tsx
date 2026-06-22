/**
 * Modal form for creating or editing a content source.
 * Field set adapts to the source type (podcast vs news).
 */

import React, { useEffect, useState } from 'react';
import { X, Loader2 } from 'lucide-react';
import type { ContentSource, SourceType } from '@/types/contentSource';

export interface SourceFormValues {
  source_type: SourceType;
  name: string;
  feed_url: string;
  region: string;
  language: string;
  spotify_url: string;
  lookback_days: string; // kept as string for the input; normalized on save
  max_episodes: string;
  transcript_service: string;
  transcript_model: string;
  active: boolean;
}

interface SourceFormDialogProps {
  isOpen: boolean;
  /** Type for a new source (ignored when editing). */
  sourceType: SourceType;
  /** When set, the dialog edits this source; otherwise it creates a new one. */
  editing: ContentSource | null;
  onClose: () => void;
  onSave: (values: SourceFormValues, editingId?: number) => Promise<void>;
}

const TRANSCRIPT_SERVICES = ['', 'groq', 'whisper', 'openai'];

function emptyValues(sourceType: SourceType): SourceFormValues {
  return {
    source_type: sourceType,
    name: '',
    feed_url: '',
    region: '',
    language: sourceType === 'podcast' ? 'zh-TW' : '',
    spotify_url: '',
    lookback_days: '30',
    max_episodes: '',
    transcript_service: '',
    transcript_model: '',
    active: true,
  };
}

function fromSource(s: ContentSource): SourceFormValues {
  return {
    source_type: s.source_type,
    name: s.name,
    feed_url: s.feed_url,
    region: s.region ?? '',
    language: s.language ?? '',
    spotify_url: s.spotify_url ?? '',
    lookback_days: s.lookback_days == null ? '' : String(s.lookback_days),
    max_episodes: s.max_episodes == null ? '' : String(s.max_episodes),
    transcript_service: s.transcript_service ?? '',
    transcript_model: s.transcript_model ?? '',
    active: s.active,
  };
}

export const SourceFormDialog: React.FC<SourceFormDialogProps> = ({
  isOpen,
  sourceType,
  editing,
  onClose,
  onSave,
}) => {
  const [values, setValues] = useState<SourceFormValues>(emptyValues(sourceType));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setValues(editing ? fromSource(editing) : emptyValues(sourceType));
  }, [isOpen, editing, sourceType]);

  if (!isOpen) return null;

  const isPodcast = values.source_type === 'podcast';

  const set = <K extends keyof SourceFormValues>(key: K, value: SourceFormValues[K]) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!values.name.trim() || !values.feed_url.trim()) {
      setError('Name and Feed URL are required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(values, editing?.id);
      onClose();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : null);
      setError(detail || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const labelCls = 'block text-base font-medium text-foreground';
  const fieldCls =
    'mt-1 w-full rounded-md border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-card p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-foreground">
            {editing ? 'Edit Source' : `Add ${isPodcast ? 'Podcast' : 'News Feed'}`}
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>Name *</label>
            <input
              type="text"
              value={values.name}
              onChange={(e) => set('name', e.target.value)}
              className={fieldCls}
              autoFocus
            />
          </div>

          <div>
            <label className={labelCls}>Feed URL *</label>
            <input
              type="text"
              value={values.feed_url}
              onChange={(e) => set('feed_url', e.target.value)}
              className={fieldCls}
              placeholder="https://…"
            />
          </div>

          {isPodcast ? (
            <>
              <div>
                <label className={labelCls}>Language</label>
                <select
                  value={values.language}
                  onChange={(e) => set('language', e.target.value)}
                  className={fieldCls}
                >
                  <option value="zh-TW">Chinese (zh-TW)</option>
                  <option value="en">English</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Spotify URL</label>
                <input
                  type="text"
                  value={values.spotify_url}
                  onChange={(e) => set('spotify_url', e.target.value)}
                  className={fieldCls}
                  placeholder="https://open.spotify.com/show/…"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Transcript Service</label>
                  <select
                    value={values.transcript_service}
                    onChange={(e) => set('transcript_service', e.target.value)}
                    className={fieldCls}
                  >
                    {TRANSCRIPT_SERVICES.map((s) => (
                      <option key={s} value={s}>
                        {s || '(default)'}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Transcript Model</label>
                  <input
                    type="text"
                    value={values.transcript_model}
                    onChange={(e) => set('transcript_model', e.target.value)}
                    className={fieldCls}
                    placeholder="whisper-large-v3"
                  />
                </div>
              </div>
            </>
          ) : (
            <div>
              <label className={labelCls}>Region</label>
              <select
                value={values.region}
                onChange={(e) => set('region', e.target.value)}
                className={fieldCls}
              >
                <option value="">(none)</option>
                <option value="US">US</option>
                <option value="TW">TW</option>
              </select>
            </div>
          )}

          {/* Ingest recency — applies to both podcasts and news */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Lookback (days)</label>
              <input
                type="number"
                min={1}
                value={values.lookback_days}
                onChange={(e) => set('lookback_days', e.target.value)}
                className={fieldCls}
                placeholder="30"
              />
              <p className="mt-1 text-xs text-muted-foreground">Only ingest items newer than this</p>
            </div>
            <div>
              <label className={labelCls}>Max episodes</label>
              <input
                type="number"
                min={1}
                value={values.max_episodes}
                onChange={(e) => set('max_episodes', e.target.value)}
                className={fieldCls}
                placeholder="(no cap)"
              />
              <p className="mt-1 text-xs text-muted-foreground">Optional safety cap per run</p>
            </div>
          </div>

          <label className="flex items-center gap-2 text-base text-foreground">
            <input
              type="checkbox"
              checked={values.active}
              onChange={(e) => set('active', e.target.checked)}
              className="h-4 w-4 rounded border-input text-accent-info focus:ring-accent-info"
            />
            Active (followed by the pipeline)
          </label>

          {error && <p className="text-base text-destructive">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-4 py-2 text-base text-foreground hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 rounded-md bg-accent-info px-4 py-2 text-base text-accent-info-foreground hover:bg-accent-info/90 disabled:opacity-50"
            >
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              {editing ? 'Save' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
