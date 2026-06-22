/**
 * Content-source table with inline editing, active toggle, and row actions.
 */

import React, { useState } from 'react';
import { Loader2, Trash2, Pencil, ExternalLink } from 'lucide-react';
import type { ContentSource, ContentSourceUpdate, SourceRunStatus } from '@/types/contentSource';
import { formatDateTime } from '@/lib/date';

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

interface SourceTableProps {
  sources: ContentSource[];
  loading: boolean;
  onUpdate: (id: number, data: ContentSourceUpdate) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onEdit: (source: ContentSource) => void;
  runStatus?: Map<string, SourceRunStatus>;
}

interface EditingCell {
  id: number;
  field: 'name' | 'lookback_days';
  value: string;
}

export const SourceTable: React.FC<SourceTableProps> = ({
  sources,
  loading,
  onUpdate,
  onDelete,
  onEdit,
  runStatus,
}) => {
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const startEdit = (id: number, field: 'name' | 'lookback_days', current: string | number | null) => {
    setEditingCell({ id, field, value: current == null ? '' : String(current) });
  };

  const commitEdit = async () => {
    if (!editingCell) return;
    const source = sources.find((s) => s.id === editingCell.id);
    if (!source) {
      setEditingCell(null);
      return;
    }
    const current = editingCell.field === 'name' ? source.name : source.lookback_days;
    const currentStr = current == null ? '' : String(current);
    if (editingCell.value !== currentStr) {
      setSaving(editingCell.id);
      try {
        if (editingCell.field === 'name') {
          if (editingCell.value.trim()) {
            await onUpdate(editingCell.id, { name: editingCell.value.trim() });
          }
        } else {
          const n = parseInt(editingCell.value, 10);
          await onUpdate(editingCell.id, { lookback_days: Number.isFinite(n) ? n : null });
        }
      } finally {
        setSaving(null);
      }
    }
    setEditingCell(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitEdit();
    } else if (e.key === 'Escape') {
      setEditingCell(null);
    }
  };

  const toggleActive = async (source: ContentSource) => {
    setSaving(source.id);
    try {
      await onUpdate(source.id, { active: !source.active });
    } finally {
      setSaving(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this source?')) return;
    setDeleting(id);
    try {
      await onDelete(id);
    } finally {
      setDeleting(null);
    }
  };

  if (loading && sources.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        No sources found
      </div>
    );
  }

  const inputCls =
    'w-full rounded border border-accent-info bg-card px-2 py-1 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-accent-info';
  const thCls =
    'px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground';

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-muted">
          <tr>
            <th className={thCls}>Name</th>
            <th className={thCls}>Locale</th>
            <th className={thCls}>Feed</th>
            <th className={thCls} title="Only ingest items published within this many days (optional ≤ cap)">
              Window
            </th>
            <th className={thCls} title="Most recent episode ingested (Firestore-derived; podcasts only)">
              Last ingested
            </th>
            <th className={thCls}>Active</th>
            <th className={thCls}>Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-card">
          {sources.map((source) => {
            const isSaving = saving === source.id;
            const isDeleting = deleting === source.id;
            const editingName = editingCell?.id === source.id && editingCell.field === 'name';
            const editingWindow = editingCell?.id === source.id && editingCell.field === 'lookback_days';
            const locale = source.source_type === 'news' ? source.region : source.language;
            const rs = runStatus?.get(source.name);
            return (
              <tr key={source.id} className="hover:bg-muted/50">
                {/* Name */}
                <td className="px-4 py-3">
                  {editingName ? (
                    <input
                      type="text"
                      value={editingCell!.value}
                      onChange={(e) => setEditingCell({ ...editingCell!, value: e.target.value })}
                      onBlur={commitEdit}
                      onKeyDown={handleKeyDown}
                      className={inputCls}
                      autoFocus
                    />
                  ) : (
                    <div
                      onClick={() => startEdit(source.id, 'name', source.name)}
                      className="cursor-pointer rounded px-2 py-1 text-base font-medium text-foreground hover:bg-muted"
                    >
                      {isSaving && !editingCell ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        source.name
                      )}
                    </div>
                  )}
                </td>
                {/* Locale */}
                <td className="whitespace-nowrap px-4 py-3 text-base text-muted-foreground">
                  {locale || <span className="italic text-muted-foreground/60">—</span>}
                </td>
                {/* Feed */}
                <td className="px-4 py-3">
                  <a
                    href={source.feed_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex max-w-xs items-center gap-1 truncate text-base text-accent-info hover:underline"
                    title={source.feed_url}
                  >
                    <span className="truncate">{source.feed_url}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                </td>
                {/* Ingest window (days) — applies to both podcasts and news */}
                <td className="px-4 py-3">
                  {editingWindow ? (
                    <input
                      type="number"
                      min={1}
                      value={editingCell!.value}
                      onChange={(e) => setEditingCell({ ...editingCell!, value: e.target.value })}
                      onBlur={commitEdit}
                      onKeyDown={handleKeyDown}
                      className={`${inputCls} w-20`}
                      autoFocus
                    />
                  ) : (
                    <div
                      onClick={() => startEdit(source.id, 'lookback_days', source.lookback_days)}
                      className="flex cursor-pointer items-baseline gap-1 rounded px-2 py-1 text-base text-muted-foreground hover:bg-muted"
                      title={
                        source.max_episodes != null
                          ? `Last ${source.lookback_days ?? '?'} days, capped at ${source.max_episodes} items/run`
                          : 'Only ingest items newer than this many days'
                      }
                    >
                      {source.lookback_days != null ? (
                        <span>{source.lookback_days}d</span>
                      ) : (
                        <span className="italic text-muted-foreground/60">Click…</span>
                      )}
                      {source.max_episodes != null && (
                        <span className="text-xs text-muted-foreground/60">≤{source.max_episodes}</span>
                      )}
                    </div>
                  )}
                </td>
                {/* Last episode ingested (Firestore-derived; podcasts only) */}
                <td className="whitespace-nowrap px-4 py-3 text-base">
                  {rs && rs.last_ingested_at ? (
                    <span
                      className="text-muted-foreground"
                      title={`${rs.episode_count} episode(s) · ${formatDateTime(rs.last_ingested_at)}`}
                    >
                      {timeAgo(rs.last_ingested_at)}
                      <span className="ml-1 text-xs text-muted-foreground/60">· {rs.episode_count}</span>
                    </span>
                  ) : (
                    <span className="italic text-muted-foreground/60">—</span>
                  )}
                </td>
                {/* Active toggle */}
                <td className="whitespace-nowrap px-4 py-3">
                  <button
                    onClick={() => toggleActive(source)}
                    disabled={isSaving}
                    role="switch"
                    aria-checked={source.active}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                      source.active ? 'bg-sentiment-bull' : 'bg-muted-foreground/40'
                    }`}
                    title={source.active ? 'Active — click to disable' : 'Inactive — click to enable'}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-card transition-transform ${
                        source.active ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </td>
                {/* Actions */}
                <td className="whitespace-nowrap px-4 py-3">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onEdit(source)}
                      className="rounded p-1 text-muted-foreground hover:bg-accent-info-soft hover:text-accent-info"
                      title="Edit source"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(source.id)}
                      disabled={isDeleting}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                      title="Delete source"
                    >
                      {isDeleting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
