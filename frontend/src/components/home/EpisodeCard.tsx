import React, { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bookmark, Lightbulb, Share2, PlayCircle } from 'lucide-react';
import type { Episode } from '@/data/mockData';
import { Skeleton } from '@/components/ui/Skeleton';
import { StockHoverCard } from '@/components/stock/StockHoverCard';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import { useAppStore } from '@/store/useAppStore';
import { usePlayerStore } from '@/store/usePlayerStore';
import { userApi } from '@/services/api/user';
import { extractSections } from '@/utils/markdownParser';
import { parseTimestampedSections } from '@/utils/parseTimestampedSections';

import { handleNavigation } from '@/utils/navigation';

interface EpisodeCardProps {
  episode?: Episode; // Make episode optional for loading state
  loading?: boolean; // Add loading prop
  onPodcasterClick?: (name: string) => void;
  onTickerClick?: (symbol: string) => void;
  onTagClick?: (tag: string) => void;
  isBookmarked?: boolean;
  onBookmarkToggle?: () => void | Promise<void>; // Reserved for parent component callback
  variant?: 'full' | 'compact';
}

const EpisodeCard: React.FC<EpisodeCardProps> = ({
  episode,
  loading = false,
  onPodcasterClick,
  onTickerClick,
  onTagClick,
  isBookmarked: isBookmarkedProp,
  onBookmarkToggle: _onBookmarkToggle,
  variant = 'full'
}) => {
  const navigate = useNavigate();
  const { token, toggleEpisodeBookmark } = useAppStore();
  const { playEpisode, player } = usePlayerStore();
  const [isBookmarked, setIsBookmarked] = useState(isBookmarkedProp ?? false);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);

  if (loading || !episode) {
    return (
      <div className={cn(
        "rounded-xl shadow-sm overflow-hidden",
        "glass-card",
        variant === 'compact' ? "p-4" : "p-6"
      )}>
        <div className={cn("flex justify-between items-start", variant === 'compact' ? "mb-2" : "mb-4")}>
          <div className="flex gap-4 w-full">
            <Skeleton className="w-12 h-12 rounded-lg shrink-0" />
            <div className="space-y-2 w-full">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          </div>
        </div>
        {variant === 'full' && (
          <div className="space-y-4 mb-6 pl-16">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
        )}
        <div className="pl-16 pt-2 flex gap-2">
          <Skeleton className="h-8 w-20 rounded-md" />
          <Skeleton className="h-8 w-20 rounded-md" />
        </div>
      </div>
    );
  }

  // Memoize formatted episode ID to prevent unnecessary re-renders
  const formattedEpisodeId = useMemo(
    () => `${episode.showName}_${episode.id}`,
    [episode.showName, episode.id]
  );

  // Update local state when prop changes
  useEffect(() => {
    if (isBookmarkedProp !== undefined) {
      setIsBookmarked(isBookmarkedProp);
    }
  }, [isBookmarkedProp]);

  // Only check bookmark status if not provided as prop (for single episode views like NewsPage)
  useEffect(() => {
    // Skip if bookmark status is provided as prop (parent handles fetching)
    if (isBookmarkedProp !== undefined || !token) {
      if (!token) setIsBookmarked(false);
      return;
    }

    const checkBookmarkStatus = async () => {
      try {
        const bookmarks = await userApi.getEpisodeBookmarks();
        setIsBookmarked(bookmarks.includes(formattedEpisodeId));
      } catch (error) {
        console.error('Failed to check bookmark status:', error);
        setIsBookmarked(false);
      }
    };

    checkBookmarkStatus();
  }, [token, formattedEpisodeId, isBookmarkedProp]);

  const handleBookmarkClick = async (e: React.MouseEvent) => {
    e.stopPropagation();

    // If not logged in, the store will show a toast prompt
    if (!token) {
      await toggleEpisodeBookmark(episode.showName, episode.id);
      return;
    }

    setBookmarkLoading(true);
    // Optimistic update
    setIsBookmarked(!isBookmarked);
    try {
      await toggleEpisodeBookmark(episode.showName, episode.id);
      // Call parent callback if provided to refresh bookmark list
      if (_onBookmarkToggle) {
        await _onBookmarkToggle();
      }
    } catch (error) {
      console.error('Failed to toggle bookmark:', error);
      // Revert on error
      setIsBookmarked(isBookmarked);
    } finally {
      setBookmarkLoading(false);
    }
  };

  const handleCardClick = (e?: React.MouseEvent) => {
    const url = `/news/${episode.id}?podcast=${encodeURIComponent(episode.showName)}`;
    if (e) {
      handleNavigation(e, url, navigate);
    } else {
      navigate(url);
    }
  };

  const handlePodcasterClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onPodcasterClick) {
      onPodcasterClick(episode.showName);
    } else {
      navigate(`/podcaster/${encodeURIComponent(episode.showName)}`);
    }
  };

  const handleTagClick = (tag: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const cleanTag = tag.replace('#', '');
    if (onTagClick) {
      onTagClick(cleanTag);
    } else {
      navigate(`/tag/${encodeURIComponent(cleanTag)}`);
    }
  };

  const handleTickerClick = (symbol: string) => {
    if (onTickerClick) {
      onTickerClick(symbol);
    } else {
      navigate(`/stock/${symbol}`);
    }
  };

  // Convert structured summary to markdown
  // Use extractSections to parse markdown content if available, or fall back to summary content
  const parsedSections = useMemo(() => {
    // Construct a markdown-like string from summary points to parse with our new parser
    // This is a bridge because we are modifying the "View" logic but data source is MockEpisode.
    const fullMarkdown = episode.summary.map(s => s.text).join('\n\n');
    return extractSections(fullMarkdown);
  }, [episode.summary]); // Re-run only when episode.summary changes

  // Helper to render text with highlights support (simplified for sections)
  const renderTextWithHighlights = (text: string, isHeadLine: boolean = false) => {
    if (!text) return null;

    // Clean raw regex codes for preview (e.g. (#time:...), (#tag:...))
    const cleanText = text.replace(/\(#time:\d+\)/g, '').replace(/\(#tag:[^)]+\)/g, '');
    let markdownText = cleanText;

    // Collect all highlights from all summary points
    const allHighlights = episode.summary.flatMap(s => s.highlights || []);

    // Deduplicate by text
    const uniqueHighlights = Array.from(new Map(allHighlights.map(h => [h.text, h])).values());

    // Sort by length desc
    const sortedHighlights = uniqueHighlights.sort((a, b) => b.text.length - a.text.length);

    sortedHighlights.forEach(h => {
      if (h.type === 'stock' && h.symbol && markdownText.includes(h.text)) {
        // Only replace if not already linked (simple check)
        if (!markdownText.match(new RegExp(`\\[${h.text}\\]`))) {
          const escapedText = h.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          markdownText = markdownText.replace(new RegExp(escapedText, 'g'), `[${h.text}](#ticker:${h.symbol})`);
        }
      }
    });

    return (
      <ReactMarkdown components={{
        ...MarkdownComponents,
        p: ({ children }: any) => (
          <div
            data-testid={isHeadLine ? "summary-headline" : "summary-text"}
            className={cn(
              "mb-2 text-sm leading-relaxed",
              isHeadLine
                ? "font-bold text-slate-900 dark:text-slate-100 mb-1"
                : "text-slate-600 dark:text-slate-300"
            )}>
            {children}
          </div>
        )
      }}>
        {markdownText}
      </ReactMarkdown>
    );
  };

  // Custom Markdown Components
  const MarkdownComponents = {
    a: ({ href, children, ...props }: any) => {
      if (href && href.startsWith('#ticker:')) {
        const symbol = href.replace('#ticker:', '');
        return (
          <StockHoverCard
            symbol={symbol}
            onClick={(e) => {
              e.stopPropagation();
              handleTickerClick(symbol);
            }}
            className="inline text-amber-600 dark:text-amber-400 font-medium cursor-pointer hover:underline transition-all"
          >
            {children}
          </StockHoverCard>
        );
      }
      if (href && href.startsWith('#tag:')) {
        const tag = href.replace('#tag:', '');
        return (
          <span
            onClick={(e) => handleTagClick(tag, e)}
            className="inline-flex mx-1 px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 text-xs font-semibold cursor-pointer hover:bg-indigo-200 dark:hover:bg-indigo-500/30 transition-colors border border-indigo-200 dark:border-indigo-500/30 align-middle"
          >
            {children}
          </span>
        );
      }
      return <a href={href} {...props}>{children}</a>;
    },
    p: ({ children }: any) => <div className="mb-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{children}</div>,
    ul: ({ children }: any) => <ul className="list-disc pl-6 mb-4 space-y-2">{children}</ul>,
    li: ({ children }: any) => <li className="pl-1 text-slate-600 dark:text-slate-300 leading-relaxed text-sm">{children}</li>,
  };


  const handlePlayClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (episode.spotifyUri) {
      // Extract timestamped sections from full markdown text using the robust parser
      // This ensures consistency with NewsPage logic
      const fullMarkdown = episode.summary.map(s => s.text).join('\n\n');
      const timestampedSections = parseTimestampedSections(fullMarkdown);

      playEpisode({
        id: episode.id,
        title: episode.title,
        showName: episode.showName,
        coverUrl: episode.imageUrl,
        spotifyUri: episode.spotifyUri,
        timestampedSections: timestampedSections.length > 0 ? timestampedSections : undefined
      });
    } else {
      // Fallback or external link
      window.open(`https://open.spotify.com/search/${encodeURIComponent(episode.title)}`, '_blank');
    }
  };

  const isPlayingThis = player?.currentEpisodeId === episode.id && player?.isPlaying;

  return (
    <article
      onClick={handleCardClick}
      className={cn(
        "rounded-xl overflow-hidden transition-all duration-300 cursor-pointer relative group isolate",
        // Light Mode
        "bg-white border border-slate-200 shadow-sm",
        // Dark Mode
        "dark:bg-slate-900/80 dark:border-0 dark:backdrop-blur-md",

        // Hover Scale & Shadow
        "hover:shadow-md hover:-translate-y-0.5 dark:hover:shadow-amber-900/10 hover:border-amber-500/30 dark:hover:border-amber-500/50",

        variant === 'full' ? [
          // Full card specific styles
          "dark:[background-image:radial-gradient(ellipse_at_top_right,rgba(30,41,59,0.9),rgba(15,23,42,0.95),rgba(2,6,23,0.95))]",
          "dark:border-t-2 dark:border-t-amber-500/30",
        ] : [
          // Compact card specific styles
          "dark:bg-slate-900/70 dark:border dark:border-white/10",
        ]
      )}
    >
      <div className={variant === 'compact' ? "p-4" : "p-8"}>
        {/* Header Section */}
        <div className={cn("flex justify-between items-start", variant === 'compact' ? "mb-3" : "mb-4")}>
          <div className="flex gap-4">
            {/* Podcast Avatar/Image */}
            <div className="shrink-0">
              {episode.imageUrl ? (
                <button
                  onClick={handlePodcasterClick}
                  className={cn(
                    "rounded-xl overflow-hidden block hover:opacity-80 transition-opacity ring-1 ring-slate-100 dark:ring-white/10",
                    variant === 'full' ? "w-16 h-16" : "w-12 h-12"
                  )}
                >
                  <img
                    src={episode.imageUrl}
                    alt={episode.showName}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.style.display = 'none';
                      const parent = target.parentElement;
                      if (parent) {
                        parent.innerHTML = `<span class="w-full h-full flex items-center justify-center font-bold text-sm ${episode.showColorClass}">${episode.showAvatar}</span>`;
                      }
                    }}
                  />
                </button>
              ) : (
                <button
                  onClick={handlePodcasterClick}
                  className={cn(
                    "rounded-xl flex items-center justify-center font-bold block hover:opacity-80 transition-opacity",
                    episode.showColorClass,
                    variant === 'full' ? "w-16 h-16 text-lg" : "w-12 h-12 text-sm"
                  )}
                >
                  {episode.showAvatar}
                </button>
              )}
            </div>

            {/* Title & Meta */}
            <div>
              <h3 className={cn(
                "font-bold leading-snug mb-1 transition-colors duration-300",
                "text-slate-900 dark:text-slate-50",
                "group-hover:text-amber-600 dark:group-hover:text-amber-400", // Title color change on hover
                variant === 'compact' ? "text-base" : "text-2xl"
              )}>
                {episode.title}
              </h3>
              <div className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400/90">
                <button
                  onClick={handlePodcasterClick}
                  className="font-bold hover:text-amber-600 dark:hover:text-amber-500 cursor-pointer transition-colors"
                >
                  {episode.showName}
                </button>
                <span>•</span>
                <span>{episode.timeAgo}</span>
              </div>
            </div>
          </div>
        </div>


        {/* Key Insights Section - Only if available */}
        {variant === 'full' && episode.keyInsights && episode.keyInsights.length > 0 && (
          <div className="mb-6 pl-20" data-testid="key-insights-section">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb size={20} className="text-emerald-500" />
              <h4 className="font-bold text-slate-800 dark:text-slate-200">關鍵洞察</h4>
            </div>
            <ul className="space-y-2">
              {episode.keyInsights.map((insight, idx) => (
                <li key={idx} className="flex gap-2 text-slate-600 dark:text-slate-300 text-sm leading-relaxed">
                  <span className="text-emerald-500 font-bold">•</span>
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Content Section */}
        {variant === 'full' && (!episode.keyInsights || episode.keyInsights.length === 0) && (
          <div className="space-y-6 mb-6 pl-20">
            {parsedSections.length > 0 ? (
              // Limit to first section for "Teaser" look
              parsedSections.slice(0, 1).map((section, idx) => (
                <div key={idx} className="group/content">
                  <h4 className="text-lg font-bold text-amber-600 dark:text-amber-500 mb-2 leading-tight">
                    {renderTextWithHighlights(section.title)}
                  </h4>
                  {section.content && (
                    <div className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed line-clamp-3">
                      {/* Add line-clamp-3 for '...' at the end */}
                      {renderTextWithHighlights(section.content)}
                    </div>
                  )}
                </div>
              ))
            ) : (
              // Fallback for episodes without sections
              <div className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed line-clamp-3">
                {episode.summary.map((s, i) => (
                  <span key={i} className={cn("block", i === 0 && "mb-1")}>
                    {renderTextWithHighlights(s.text, i === 0)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Compact Mode Content */}
        {variant === 'compact' && (
          <div className="pl-16 mb-3 space-y-3">
            {episode.keyInsights && episode.keyInsights.length > 0 ? (
              <ul className="space-y-1">
                {episode.keyInsights.slice(0, 2).map((insight, idx) => (
                  <li key={idx} className="flex gap-2 text-slate-600 dark:text-slate-300 text-sm leading-relaxed line-clamp-1">
                    <span className="text-emerald-500 font-bold shrink-0">•</span>
                    <span>{insight}</span>
                  </li>
                ))}
                {episode.keyInsights.length > 2 && (
                  <div className="text-xs text-slate-400 mt-1 font-medium pl-3">
                    +{episode.keyInsights.length - 2} 更多重點
                  </div>
                )}
              </ul>
            ) : parsedSections.length > 0 ? (
              <>
                {parsedSections.slice(0, 3).map((section, idx) => (
                  <div key={idx} className="block">
                    <h4 className="text-lg font-bold text-slate-700 dark:text-slate-300 leading-tight line-clamp-2">
                      {renderTextWithHighlights(section.title)}
                    </h4>
                  </div>
                ))}
              </>
            ) : null}
          </div>
        )}


        {/* Footer Actions - Flexible layout: side-by-side if fits, wraps if not */}
        <div className={cn("flex flex-wrap justify-between items-center mt-4 gap-y-3", variant === 'full' ? "pl-20" : "pl-16")}>
          {/* Tags - Limited on mobile (max 4), all visible on desktop */}
          <div className="flex gap-2 flex-wrap items-center">
            {episode.tags.length > 0 && episode.tags.slice(0, 4).map(tag => (
              <button
                key={tag}
                onClick={(e) => handleTagClick(tag, e)}
                className="text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-3 py-1 rounded-full hover:bg-amber-100 dark:hover:bg-amber-900/30 hover:text-amber-700 dark:hover:text-amber-400 transition-colors cursor-pointer"
              >
                {tag}
              </button>
            ))}
            {/* Show remaining tags only on desktop */}
            {episode.tags.length > 4 && episode.tags.slice(4).map(tag => (
              <button
                key={tag}
                onClick={(e) => handleTagClick(tag, e)}
                className="hidden md:inline-flex text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-3 py-1 rounded-full hover:bg-amber-100 dark:hover:bg-amber-900/30 hover:text-amber-700 dark:hover:text-amber-400 transition-colors cursor-pointer"
              >
                {tag}
              </button>
            ))}
            {/* "+N more" indicator on mobile when tags > 4 */}
            {episode.tags.length > 4 && (
              <span className="md:hidden text-xs text-slate-400 dark:text-slate-500 px-3 py-1 self-center">
                +{episode.tags.length - 4} 更多
              </span>
            )}
          </div>

          {/* Actions - Auto width, pushed to right */}
          <div className="flex items-center gap-2 ml-auto">
            {/* Play Button */}
            <button
              onClick={handlePlayClick}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-300 whitespace-nowrap",
                isPlayingThis
                  ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white hover:shadow-[0_0_15px_rgba(251,191,36,0.1)]"
              )}
            >
              <PlayCircle size={18} className={isPlayingThis ? "fill-current" : ""} />
              {isPlayingThis ? "播放中" : "播放"}
            </button>

            {/* Share Button */}
            <button
              onClick={async (e) => {
                e.stopPropagation();
                const episodeUrl = `${window.location.origin}/news/${episode.id}?podcast=${encodeURIComponent(episode.showName)}`;
                const shareData = {
                  title: episode.title,
                  text: `${episode.showName} - ${episode.title}`,
                  url: episodeUrl,
                };
                try {
                  if (navigator.share) {
                    await navigator.share(shareData);
                  } else {
                    await navigator.clipboard.writeText(episodeUrl);
                    alert('連結已複製到剪貼簿');
                  }
                } catch (err) {
                  console.error('Error sharing:', err);
                }
              }}
              className="p-2 rounded-full text-slate-400 dark:text-slate-500 hover:text-amber-600 dark:hover:text-amber-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="分享"
            >
              <Share2 size={18} />
            </button>

            {/* Bookmark/Save Button */}
            <button
              onClick={handleBookmarkClick}
              disabled={bookmarkLoading}
              className={cn(
                "p-2 rounded-full transition-colors",
                isBookmarked
                  ? "text-amber-600 dark:text-amber-500 bg-amber-50 dark:bg-amber-900/20"
                  : "text-slate-400 dark:text-slate-500 hover:text-amber-600 dark:hover:text-amber-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
              title={isBookmarked ? "取消收藏" : "收藏"}
            >
              <Bookmark size={18} fill={isBookmarked ? "currentColor" : "none"} />
            </button>
          </div>
        </div>

      </div>
    </article>
  );
};

export default EpisodeCard;
