import React from 'react';
import { Check, Plus } from 'lucide-react';
import { useAppStore, useTagSubscriptions } from '@/store/useAppStore';
import { cn } from '@/lib/utils';

interface TopicFollowButtonProps {
  /** The subscription key — a sector's display_name or a tag's cleaned name. */
  topic: string;
  /** 'pill' for page headers, 'icon' for the board cards where a label doesn't fit. */
  variant?: 'pill' | 'icon';
  className?: string;
}

/**
 * 追蹤話題 toggle. Sectors and tags share one subscription list, so the same
 * button serves /sector, /topics/:tag and the board cards on /topics.
 *
 * Older subscriptions were stored with a leading '#', so membership accepts both.
 */
export const TopicFollowButton: React.FC<TopicFollowButtonProps> = ({ topic, variant = 'pill', className }) => {
  const toggleTagSubscription = useAppStore((s) => s.toggleTagSubscription);
  const tagSubs = useTagSubscriptions();
  const isSubscribed = tagSubs.includes(topic) || tagSubs.includes(`#${topic}`);
  const label = isSubscribed ? '已追蹤' : '追蹤話題';

  // The board cards wrap their header in a <Link>, so the button stops the click
  // from also navigating into the topic.
  const onClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void toggleTagSubscription(topic);
  };

  if (variant === 'icon') {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-pressed={isSubscribed}
        aria-label={label}
        title={label}
        className={cn(
          'inline-grid place-items-center h-7 w-7 shrink-0 rounded-md border transition-colors',
          isSubscribed
            ? 'border-transparent bg-foreground text-background'
            : 'border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground',
          className,
        )}
      >
        {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isSubscribed}
      className={cn(
        'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0',
        isSubscribed ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
        className,
      )}
    >
      {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
      {label}
    </button>
  );
};
