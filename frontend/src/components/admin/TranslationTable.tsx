/**
 * Translation table with inline editing.
 */

import React, { useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import type { Translation, TranslationStatus } from '@/types/translation';

interface TranslationTableProps {
  translations: Translation[];
  loading: boolean;
  onUpdate: (id: number, nameZhTw?: string, nameEn?: string, status?: TranslationStatus, brandColor?: string | null) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

interface EditingCell {
  id: number;
  field: 'name_zh_tw' | 'name_en';
  value: string;
}

const STATUS_BADGES: Record<TranslationStatus, { label: string; className: string }> = {
  pending: {
    label: 'Pending',
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  approved: {
    label: 'Approved',
    className: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  },
  auto: {
    label: 'Auto',
    className: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  },
};

export const TranslationTable: React.FC<TranslationTableProps> = ({
  translations,
  loading,
  onUpdate,
  onDelete,
}) => {
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const handleCellClick = (id: number, field: 'name_zh_tw' | 'name_en', currentValue: string | null) => {
    setEditingCell({ id, field, value: currentValue || '' });
  };

  const handleCellBlur = async () => {
    if (!editingCell) return;
    const translation = translations.find((t) => t.id === editingCell.id);
    if (!translation) return;
    const currentFieldValue = editingCell.field === 'name_zh_tw' ? translation.name_zh_tw : translation.name_en;
    // Only save if value changed
    if (editingCell.value !== (currentFieldValue || '')) {
      setSaving(editingCell.id);
      try {
        if (editingCell.field === 'name_zh_tw') {
          // Editing Chinese name: pass the new value, keep English as undefined
          await onUpdate(editingCell.id, editingCell.value, undefined, 'approved');
        } else {
          // Editing English name: keep Chinese as undefined, pass the new English value
          await onUpdate(editingCell.id, undefined, editingCell.value, undefined);
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
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (translations.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
        No translations found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Ticker
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Market
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              English Name
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Chinese Name
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Color
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
          {translations.map((translation) => {
            const isEditing = editingCell?.id === translation.id;
            const isSaving = saving === translation.id;
            const isDeleting = deleting === translation.id;
            const statusBadge = STATUS_BADGES[translation.translation_status as TranslationStatus] || STATUS_BADGES.pending;
            return (
              <tr
                key={translation.id}
                className="hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <td className="whitespace-nowrap px-4 py-3 font-mono text-sm font-medium text-gray-900 dark:text-white">
                  {translation.ticker}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                  {translation.market}
                </td>
                <td className="px-4 py-3">
                  {isEditing && editingCell?.field === 'name_en' ? (
                    <input
                      type="text"
                      value={editingCell.value}
                      onChange={(e) =>
                        setEditingCell({ ...editingCell, value: e.target.value })
                      }
                      onBlur={handleCellBlur}
                      onKeyDown={handleKeyDown}
                      className="w-full rounded border border-blue-500 bg-white px-2 py-1 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white"
                      autoFocus
                    />
                  ) : (
                    <div
                      onClick={() =>
                        handleCellClick(translation.id, 'name_en', translation.name_en)
                      }
                      className={`max-w-xs cursor-pointer truncate rounded px-2 py-1 text-sm ${translation.name_en
                          ? 'text-gray-600 dark:text-gray-300'
                          : 'italic text-gray-400'
                        } hover:bg-gray-100 dark:hover:bg-gray-700`}
                    >
                      {isSaving && editingCell?.field === 'name_en' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        translation.name_en || 'Click to edit...'
                      )}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  {isEditing && editingCell?.field === 'name_zh_tw' ? (
                    <input
                      type="text"
                      value={editingCell.value}
                      onChange={(e) =>
                        setEditingCell({ ...editingCell, value: e.target.value })
                      }
                      onBlur={handleCellBlur}
                      onKeyDown={handleKeyDown}
                      className="w-full rounded border border-blue-500 bg-white px-2 py-1 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white"
                      autoFocus
                    />
                  ) : (
                    <div
                      onClick={() =>
                        handleCellClick(translation.id, 'name_zh_tw', translation.name_zh_tw)
                      }
                      className={`cursor-pointer rounded px-2 py-1 text-sm ${translation.name_zh_tw
                          ? 'text-gray-900 dark:text-white'
                          : 'italic text-gray-400'
                        } hover:bg-gray-100 dark:hover:bg-gray-700`}
                    >
                      {isSaving && editingCell?.field === 'name_zh_tw' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        translation.name_zh_tw || 'Click to edit...'
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
                        setSaving(translation.id);
                        try {
                          await onUpdate(translation.id, undefined, undefined, undefined, e.target.value);
                        } finally {
                          setSaving(null);
                        }
                      }}
                    />
                  </label>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${statusBadge.className}`}
                  >
                    {statusBadge.label}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <button
                    onClick={() => handleDelete(translation.id)}
                    disabled={isDeleting}
                    className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-900/20"
                  >
                    {isDeleting ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
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
