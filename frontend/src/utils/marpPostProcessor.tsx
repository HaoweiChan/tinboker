import React, { useEffect, useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { StockHoverCard } from '@/components/stock/StockHoverCard';
import { useNavigate } from 'react-router-dom';
import { usePlayerStore } from '@/store/usePlayerStore';
import { Play } from 'lucide-react';

interface PostProcessedSlideProps {
  html: string;
  onTickerClick?: (symbol: string) => void;
  onTagClick?: (tag: string) => void;
  episodeId?: string;
  episodeTitle?: string;
  episodeSource?: string;
  spotifyUri?: string;
  timestampedSections?: any[];
}

/**
 * Component that renders Marp HTML and post-processes it to inject React components
 */
export const PostProcessedSlide: React.FC<PostProcessedSlideProps> = ({
  html,
  onTickerClick,
  onTagClick,
  episodeId,
  episodeTitle,
  episodeSource,
  spotifyUri,
  timestampedSections,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rootsRef = useRef<Map<Element, Root>>(new Map());
  const navigate = useNavigate();
  const { playEpisode, requestSeek } = usePlayerStore();

  useEffect(() => {
    if (!containerRef.current) return;

    // Cleanup previous roots
    rootsRef.current.forEach((root) => {
      root.unmount();
    });
    rootsRef.current.clear();

    // Find all links that need to be replaced
    const links = containerRef.current.querySelectorAll('a[href]');
    
    links.forEach((link) => {
      const href = link.getAttribute('href');
      if (!href) return;

      // Handle ticker links
      if (href.startsWith('#ticker:')) {
        const symbol = href.replace('#ticker:', '');
        const textContent = link.textContent || symbol;
        
        // Create a container for the React component
        const reactContainer = document.createElement('span');
        reactContainer.className = 'marp-ticker-link';
        link.parentNode?.replaceChild(reactContainer, link);

        // Render React component
        const root = createRoot(reactContainer);
        rootsRef.current.set(reactContainer, root);
        root.render(
          <StockHoverCard
            symbol={symbol}
            onClick={(e) => {
              e.stopPropagation();
              if (onTickerClick) {
                onTickerClick(symbol);
              } else {
                navigate(`/stock/${symbol}`);
              }
            }}
            className="inline text-primary font-medium cursor-pointer hover:underline transition-all"
          >
            {textContent}
          </StockHoverCard>
        );
      }
      // Handle tag links
      else if (href.startsWith('#tag:')) {
        const tag = href.replace('#tag:', '');
        const textContent = link.textContent || tag;
        
        const reactContainer = document.createElement('span');
        reactContainer.className = 'marp-tag-link';
        link.parentNode?.replaceChild(reactContainer, link);

        const root = createRoot(reactContainer);
        rootsRef.current.set(reactContainer, root);
        root.render(
          <span
            onClick={(e) => {
              e.stopPropagation();
              if (onTagClick) {
                onTagClick(tag);
              } else {
                navigate(`/tag/${encodeURIComponent(tag)}`);
              }
            }}
            className="inline-flex mx-1 px-2 py-0.5 rounded-full bg-accent-info-soft text-accent-info text-xs font-semibold cursor-pointer hover:bg-accent-info/25 transition-colors border border-accent-info/30 align-middle"
          >
            {textContent}
          </span>
        );
      }
      // Handle time links
      else if (href.startsWith('#time:')) {
        const seconds = parseInt(href.replace('#time:', ''), 10);
        const textContent = link.textContent || `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
        
        const reactContainer = document.createElement('span');
        reactContainer.className = 'marp-time-link';
        link.parentNode?.replaceChild(reactContainer, link);

        const root = createRoot(reactContainer);
        rootsRef.current.set(reactContainer, root);
        root.render(
          <button
            onClick={() => {
              if (episodeId) {
                const isCurrentEpisode = usePlayerStore.getState().player.currentEpisodeId === episodeId;
                
                if (isCurrentEpisode) {
                  requestSeek(seconds);
                } else if (episodeTitle && episodeSource) {
                  const episodeData = {
                    id: episodeId,
                    title: episodeTitle,
                    showName: episodeSource,
                    coverUrl: undefined,
                    spotifyUri: spotifyUri || undefined,
                    timestampedSections: timestampedSections || [],
                  };
                  playEpisode(episodeData, { seekTo: seconds });
                }
              }
            }}
            className="inline-flex mx-1 ml-2 px-2.5 py-0.5 rounded-full border border-border text-muted-foreground text-xs font-financial cursor-pointer hover:bg-muted hover:text-foreground transition-colors items-center gap-1 align-middle translate-y-[-3px]"
            title={`跳轉至 ${textContent}`}
          >
            <Play size={10} className="fill-current" />
            {textContent}
          </button>
        );
      }
    });

    // Cleanup function
    return () => {
      rootsRef.current.forEach((root) => {
        root.unmount();
      });
      rootsRef.current.clear();
    };
  }, [html, onTickerClick, onTagClick, episodeId, episodeTitle, episodeSource, spotifyUri, timestampedSections, navigate, playEpisode, requestSeek]);

  return (
    <div
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: html }}
      className="marp-slide-content"
    />
  );
};
