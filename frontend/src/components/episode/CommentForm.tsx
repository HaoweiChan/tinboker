import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const MAX_CHARS = 500;

interface CommentFormProps {
  onSubmit: (content: string) => Promise<void>;
  onCancel?: () => void;
  placeholder?: string;
  autoFocus?: boolean;
}

export const CommentForm: React.FC<CommentFormProps> = ({
  onSubmit,
  onCancel,
  placeholder = '留下你的想法…',
  autoFocus = false,
}) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const trimmed = content.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= MAX_CHARS && !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setContent('');
    } catch {
      toast.error('留言失敗，請稍後再試。');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={placeholder}
        rows={3}
        maxLength={MAX_CHARS}
        autoFocus={autoFocus}
        className={cn(
          'w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground',
          'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
        disabled={submitting}
      />
      <div className="flex items-center justify-between">
        <span className={cn('text-2xs text-muted-foreground', trimmed.length > MAX_CHARS && 'text-destructive')}>
          {content.length} / {MAX_CHARS}
        </span>
        <div className="flex gap-2">
          {onCancel && (
            <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={submitting}>
              取消
            </Button>
          )}
          <Button type="submit" size="sm" disabled={!canSubmit}>
            {submitting ? '送出中…' : '送出留言'}
          </Button>
        </div>
      </div>
    </form>
  );
};
