import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Save, X, Plus } from 'lucide-react';
import { patchEpisode, getEpisodeHeavy, type Episode } from '@/services';

interface Props {
  episode: Episode;
  onUpdated: (ep: Episode) => void;
}

type SectionId = 'transcript' | 'summary' | 'insights' | 'tickers' | 'tags';

function Section({ id, label, open, onToggle, saving, onSave, children }: {
  id: SectionId;
  label: string;
  open: boolean;
  onToggle: () => void;
  saving?: boolean;
  onSave?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border rounded-md">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left text-[13px] font-medium hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {label}
        </span>
        {onSave && open && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onSave(); }}
            disabled={saving}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-blue-600 text-white text-[11px] font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            儲存
          </button>
        )}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

function TagEditor({ values, onChange }: { values: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState('');
  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput('');
  };
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted text-[12px]">
            {v}
            <button type="button" onClick={() => onChange(values.filter((x) => x !== v))} className="hover:text-destructive">
              <X size={11} />
            </button>
          </span>
        ))}
        {values.length === 0 && <span className="text-[12px] text-muted-foreground">（空）</span>}
      </div>
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="輸入後按 Enter 新增"
          className="flex-1 px-2.5 py-1.5 border border-border rounded text-[12px] bg-background"
        />
        <button type="button" onClick={add} className="px-2 py-1.5 rounded border border-border hover:bg-muted text-[12px]">
          <Plus size={12} />
        </button>
      </div>
    </div>
  );
}

function InsightEditor({ values, onChange }: { values: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState('');
  const add = () => {
    const v = input.trim();
    if (v) onChange([...values, v]);
    setInput('');
  };
  return (
    <div>
      <ul className="space-y-1 mb-2">
        {values.map((v, i) => (
          <li key={i} className="flex items-start gap-2 text-[12px]">
            <span className="flex-1 bg-muted/40 rounded px-2 py-1">{v}</span>
            <button type="button" onClick={() => onChange(values.filter((_, j) => j !== i))} className="shrink-0 mt-0.5 hover:text-destructive">
              <X size={12} />
            </button>
          </li>
        ))}
        {values.length === 0 && <li className="text-[12px] text-muted-foreground">（空）</li>}
      </ul>
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="新增重點"
          className="flex-1 px-2.5 py-1.5 border border-border rounded text-[12px] bg-background"
        />
        <button type="button" onClick={add} className="px-2 py-1.5 rounded border border-border hover:bg-muted text-[12px]">
          <Plus size={12} />
        </button>
      </div>
    </div>
  );
}

export const EpisodeDebugPanel: React.FC<Props> = ({ episode, onUpdated }) => {
  const [openSections, setOpenSections] = useState<Set<SectionId>>(new Set());
  const [saving, setSaving] = useState<SectionId | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  // Editable state — initialised from episode
  const [summary, setSummary] = useState(episode.modified_summary_content || episode.summary_content || '');
  const [insights, setInsights] = useState<string[]>(episode.key_insights ?? []);
  const [tickers, setTickers] = useState<string[]>(episode.related_tickers ?? []);
  const [tags, setTags] = useState<string[]>(episode.tags ?? []);

  // Transcript (lazy-loaded, read-only)
  const [transcript, setTranscript] = useState<string | null>(episode.transcript || null);
  const [loadingTranscript, setLoadingTranscript] = useState(false);

  // Sync local state when parent episode changes
  useEffect(() => {
    setSummary(episode.modified_summary_content || episode.summary_content || '');
    setInsights(episode.key_insights ?? []);
    setTickers(episode.related_tickers ?? []);
    setTags(episode.tags ?? []);
    if (episode.transcript) setTranscript(episode.transcript);
  }, [episode]);

  const toggle = (s: SectionId) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  };

  // Lazy-load transcript
  useEffect(() => {
    if (!openSections.has('transcript') || transcript) return;
    let alive = true;
    setLoadingTranscript(true);
    getEpisodeHeavy(episode.podcast_name, episode.id)
      .then((ep) => { if (alive) setTranscript(ep.transcript || '（無逐字稿）'); })
      .catch(() => { if (alive) setTranscript('載入失敗'); })
      .finally(() => { if (alive) setLoadingTranscript(false); });
    return () => { alive = false; };
  }, [openSections, transcript, episode.podcast_name, episode.id]);

  const save = useCallback(async (section: SectionId) => {
    setSaving(section);
    setStatus(null);
    try {
      const payload: Record<string, unknown> = {};
      if (section === 'summary') payload.summary_content = summary;
      if (section === 'insights') payload.key_insights = insights;
      if (section === 'tickers') payload.related_tickers = tickers;
      if (section === 'tags') payload.tags = tags;
      const updated = await patchEpisode(episode.podcast_name, episode.id, payload as any);
      onUpdated(updated);
      setStatus(`${section} 已儲存`);
    } catch (e: any) {
      setStatus(`儲存失敗: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setSaving(null);
    }
  }, [episode, summary, insights, tickers, tags, onUpdated]);

  return (
    <section className="bg-card border-2 border-dashed border-yellow-500/60 rounded-md p-4 mb-3.5">
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-yellow-600 dark:text-yellow-400 mb-3">
        Debug Editor (dev only)
      </h3>
      {status && (
        <div className="text-[12px] mb-2 px-2 py-1 rounded bg-muted text-muted-foreground">{status}</div>
      )}
      <div className="space-y-2">
        <Section id="transcript" label="逐字稿（唯讀）" open={openSections.has('transcript')} onToggle={() => toggle('transcript')}>
          {loadingTranscript ? (
            <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 size={14} className="animate-spin" /> 載入中…</div>
          ) : (
            <pre className="text-[11px] leading-relaxed whitespace-pre-wrap max-h-[400px] overflow-y-auto bg-muted/30 rounded p-3">{transcript || '（無逐字稿）'}</pre>
          )}
        </Section>

        <Section id="summary" label="摘要" open={openSections.has('summary')} onToggle={() => toggle('summary')} saving={saving === 'summary'} onSave={() => save('summary')}>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={12}
            className="w-full px-3 py-2 border border-border rounded text-[12px] leading-relaxed bg-background font-mono resize-y"
          />
        </Section>

        <Section id="insights" label={`重點 (${insights.length})`} open={openSections.has('insights')} onToggle={() => toggle('insights')} saving={saving === 'insights'} onSave={() => save('insights')}>
          <InsightEditor values={insights} onChange={setInsights} />
        </Section>

        <Section id="tickers" label={`提及股票 (${tickers.length})`} open={openSections.has('tickers')} onToggle={() => toggle('tickers')} saving={saving === 'tickers'} onSave={() => save('tickers')}>
          <TagEditor values={tickers} onChange={setTickers} />
        </Section>

        <Section id="tags" label={`標籤 (${tags.length})`} open={openSections.has('tags')} onToggle={() => toggle('tags')} saving={saving === 'tags'} onSave={() => save('tags')}>
          <TagEditor values={tags} onChange={setTags} />
        </Section>
      </div>
    </section>
  );
};
