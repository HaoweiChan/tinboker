/**
 * Translation table with inline editing.
 */

import React, { useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import type { NamePreference, Translation, TranslationStatus, TranslationUpdate } from '@/types/translation';

const PREFERENCE_OPTIONS: { value: NamePreference; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'zh_tw', label: '中文' },
  { value: 'en', label: 'English' },
];

interface TranslationTableProps {
  translations: Translation[];
  loading: boolean;
  onUpdate: (id: number, data: TranslationUpdate) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

type EditableField = 'name_zh_tw' | 'name_en' | 'aliases';

interface EditingCell {
  id: number;
  field: EditableField;
  value: string;
}

const STATUS_BADGES: Record<TranslationStatus, { label: string; className: string }> = {
  pending: {
    label: 'Pending',
    className: 'bg-primary/10 text-primary',
  },
  approved: {
    label: 'Approved',
    className: 'bg-sentiment-bull-soft text-sentiment-bull',
  },
  auto: {
    label: 'Auto',
    className: 'bg-muted text-muted-foreground',
  },
};

const inputCls =
  'w-full rounded border border-accent-info bg-card px-2 py-1 text-base text-foreground focus:outline-none focus:ring-2 focus:ring-accent-info';
const thCls =
  'px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground';

export const TranslationTable: React.FC<TranslationTableProps> = ({
  translations,
  loading,
  onUpdate,
  onDelete,
}) => {
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const currentValueFor = (t: Translation, field: EditableField): string => {
    if (field === 'name_zh_tw') return t.name_zh_tw || '';
    if (field === 'name_en') return t.name_en || '';
    return (t.aliases || []).join(', ');
  };

  const handleCellClick = (t: Translation, field: EditableField) => {
    setEditingCell({ id: t.id, field, value: currentValueFor(t, field) });
  };

  const handleCellBlur = async () => {
    if (!editingCell) return;
    const translation = translations.find((t) => t.id === editingCell.id);
    if (!translation) {
      setEditingCell(null);
      return;
    }
    if (editingCell.value !== currentValueFor(translation, editingCell.field)) {
      setSaving(editingCell.id);
      try {
        if (editingCell.field === 'name_zh_tw') {
          // Editing the Chinese name marks the row approved.
          await onUpdate(editingCell.id, { name_zh_tw: editingCell.value, translation_status: 'approved' });
        } else if (editingCell.field === 'name_en') {
          await onUpdate(editingCell.id, { name_en: editingCell.value });
        } else {
          const aliases = editingCell.value.split(',').map((s) => s.trim()).filter(Boolean);
          await onUpdate(editingCell.id, { aliases });
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
      handleCellBlur();
    } else if (e.key === 'Escape') {
      setEditingCell(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this translation?')) return;
    setDeleting(id);
    try {
      await onDelete(id);
    } finally {
      setDeleting(null);
    }
  };

  if (loading && translations.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (translations.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        No translations found
      </div>
    );
  }

  const renderTextCell = (t: Translation, field: 'name_en' | 'name_zh_tw') => {
    const isEditing = editingCell?.id === t.id && editingCell.field === field;
    const isSaving = saving === t.id && editingCell?.field === field;
    const value = field === 'name_en' ? t.name_en : t.name_zh_tw;
    const emptyCls = field === 'name_en' ? 'max-w-xs truncate' : '';
    const filledCls = field === 'name_en' ? 'text-muted-foreground' : 'text-foreground';
    if (isEditing) {
      return (
        <input
          type="text"
          value={editingCell!.value}
          onChange={(e) => setEditingCell({ ...editingCell!, value: e.target.value })}
          onBlur={handleCellBlur}
          onKeyDown={handleKeyDown}
          className={inputCls}
          autoFocus
        />
      );
    }
    return (
      <div
        onClick={() => handleCellClick(t, field)}
        className={`${emptyCls} cursor-pointer rounded px-2 py-1 text-base ${value ? filledCls : 'italic text-muted-foreground'} hover:bg-muted`}
      >
        {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : value || 'Click to edit...'}
      </div>
    );
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-muted">
          <tr>
            <th className={thCls}>Ticker</th>
            <th className={thCls}>Market</th>
            <th className={thCls}>English Name</th>
            <th className={thCls}>Chinese Name</th>
            <th className={thCls} title="Alternate names/symbols that resolve to this ticker in search">
              Aliases
            </th>
            <th className={thCls}>Color</th>
            <th className={thCls} title="Display preference: Auto shows the Chinese name when present; English forces the English name even if a Chinese name exists">
              Preference
            </th>
            <th className={thCls}>Status</th>
            <th className={thCls}>Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-card">
          {translations.map((translation) => {
            const isDeleting = deleting === translation.id;
            const statusBadge =
              STATUS_BADGES[translation.translation_status as TranslationStatus] || STATUS_BADGES.pending;
            const editingAliases =
              editingCell?.id === translation.id && editingCell.field === 'aliases';
            const aliases = translation.aliases || [];
            return (
              <tr key={translation.id} className="hover:bg-muted/50">
                <td className="whitespace-nowrap px-4 py-3 font-mono text-base font-medium text-foreground">
                  {translation.ticker}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-base text-muted-foreground">
                  {translation.market}
                </td>
                <td className="px-4 py-3">{renderTextCell(translation, 'name_en')}</td>
                <td className="px-4 py-3">{renderTextCell(translation, 'name_zh_tw')}</td>
                {/* Aliases — comma-separated inline edit, rendered as chips */}
                <td className="px-4 py-3">
                  {editingAliases ? (
                    <input
                      type="text"
                      value={editingCell!.value}
                      onChange={(e) => setEditingCell({ ...editingCell!, value: e.target.value })}
                      onBlur={handleCellBlur}
                      onKeyDown={handleKeyDown}
                      className={`${inputCls} min-w-[12rem]`}
                      placeholder="alias one, alias two"
                      autoFocus
                    />
                  ) : (
                    <div
                      onClick={() => handleCellClick(translation, 'aliases')}
                      className="flex max-w-xs cursor-pointer flex-wrap gap-1 rounded px-2 py-1 hover:bg-muted"
                      title="Click to edit (comma-separated)"
                    >
                      {saving === translation.id && editingCell?.field === 'aliases' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : aliases.length > 0 ? (
                        aliases.map((a, i) => (
                          <span
                            key={`${a}-${i}`}
                            className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground"
                          >
                            {a}
                          </span>
                        ))
                      ) : (
                        <span className="text-base italic text-muted-foreground">Click to edit...</span>
                      )}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <label
                    className="relative flex h-6 w-6 cursor-pointer items-center justify-center rounded"
                    title={translation.brand_color ?? 'No brand color set'}
                    style={{ backgroundColor: translation.brand_color ?? '#e5e7eb' }}
                  >
                    <input
                      type="color"
                      className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                      value={translation.brand_color ?? '#000000'}
                      onChange={async (e) => {
                        const color = e.target.value;
                        setSaving(translation.id);
                        try {
                          await onUpdate(translation.id, { brand_color: color });
                        } finally {
                          setSaving(null);
                        }
                      }}
                    />
                  </label>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <select
                    value={translation.name_preference ?? 'auto'}
                    onChange={async (e) => {
                      const pref = e.target.value as NamePreference;
                      setSaving(translation.id);
                      try {
                        await onUpdate(translation.id, { name_preference: pref });
                      } finally {
                        setSaving(null);
                      }
                    }}
                    disabled={saving === translation.id}
                    title="Auto: show the Chinese name when present. English: force the English name even if a Chinese name exists."
                    className="rounded border border-input bg-card px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-accent-info disabled:opacity-50"
                  >
                    {PREFERENCE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${statusBadge.className}`}>
                    {statusBadge.label}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <button
                    onClick={() => handleDelete(translation.id)}
                    disabled={isDeleting}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                  >
                    {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
