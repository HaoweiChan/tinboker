import React, { useCallback, useRef, useState, useEffect } from 'react';
import { MoreHorizontal, Share2, Bookmark, Link, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ShareMenuProps {
  /** Full URL to share. Falls back to current page URL. */
  shareUrl?: string;
  /** Title used in the Web Share API dialog. */
  shareTitle?: string;
  /** Whether the item is currently bookmarked. */
  isBookmarked?: boolean;
  /** Called when the user taps "收藏". */
  onBookmark?: () => void;
  /** Extra CSS on the trigger button. */
  className?: string;
}

export const ShareMenu: React.FC<ShareMenuProps> = ({
  shareUrl,
  shareTitle,
  isBookmarked = false,
  onBookmark,
  className,
}) => {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    document.addEventListener('touchstart', handler);
    return () => {
      document.removeEventListener('mousedown', handler);
      document.removeEventListener('touchstart', handler);
    };
  }, [open]);

  const url = shareUrl || window.location.href;

  const copyToClipboard = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard API unavailable */ }
  }, [url]);

  const handleShare = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (navigator.share) {
      try {
        await navigator.share({ title: shareTitle, url });
        setOpen(false);
        return;
      } catch { /* user cancelled — fall through to clipboard */ }
    }
    await copyToClipboard();
    setOpen(false);
  }, [shareTitle, url, copyToClipboard]);

  const handleCopyLink = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    await copyToClipboard();
    setOpen(false);
  }, [copyToClipboard]);

  const handleBookmark = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onBookmark?.();
    setOpen(false);
  }, [onBookmark]);

  const toggleMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setOpen((v) => !v);
  }, []);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={toggleMenu}
        className={cn(
          'inline-flex items-center justify-center w-7 h-7 rounded-full',
          'text-muted-foreground hover:bg-muted hover:text-foreground transition-colors',
          className,
        )}
        aria-label="更多選項"
      >
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[140px] bg-popover border border-border rounded-[var(--radius-md)] shadow-lg py-1 animate-in fade-in-0 zoom-in-95">
          <button
            type="button"
            onClick={handleShare}
            className="flex items-center gap-2 w-full px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
          >
            <Share2 size={14} />
            分享
          </button>
          {onBookmark && (
            <button
              type="button"
              onClick={handleBookmark}
              className="flex items-center gap-2 w-full px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
            >
              <Bookmark size={14} className={isBookmarked ? 'fill-current text-accent-info' : ''} />
              {isBookmarked ? '取消收藏' : '收藏'}
            </button>
          )}
          <button
            type="button"
            onClick={handleCopyLink}
            className="flex items-center gap-2 w-full px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
          >
            {copied ? <Check size={14} className="text-emerald-500" /> : <Link size={14} />}
            {copied ? '已複製' : '複製連結'}
          </button>
        </div>
      )}
    </div>
  );
};
