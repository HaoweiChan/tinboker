import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';

interface SpotifyEmbedProps {
  uri: string;
  className?: string;
  height?: number;
  onPlayerReady?: () => void;
  onPlaybackUpdate?: (state: {
    position: number;
    duration: number;
    isPaused: boolean;
    isBuffering: boolean;
  }) => void;
}

export interface SpotifyEmbedRef {
  seekTo: (seconds: number) => void;
  play: () => void;
  pause: () => void;
  togglePlay: () => void;
}

/** The slice of Spotify's iframe API this component uses (it ships no types). */
interface SpotifyPlaybackUpdate {
  data: { position?: number; duration?: number; isPaused?: boolean; isBuffering?: boolean };
}
interface SpotifyEmbedController {
  play?: () => void;
  pause?: () => void;
  togglePlay?: () => void;
  resume?: () => void;
  seek?: (seconds: number) => void;
  destroy?: () => void;
  addListener?: (event: 'playback_update', cb: (e: SpotifyPlaybackUpdate) => void) => void;
}
interface SpotifyIFrameAPI {
  createController: (
    element: HTMLElement,
    options: { uri: string; width: string; height: string },
    callback: (controller: SpotifyEmbedController) => void,
  ) => void;
}

declare global {
  interface Window {
    onSpotifyIframeApiReady?: (IFrameAPI: SpotifyIFrameAPI) => void;
    Spotify?: SpotifyIFrameAPI;
  }
}

export const SpotifyEmbed = forwardRef<SpotifyEmbedRef, SpotifyEmbedProps>(({ uri, className = '', height = 352, onPlayerReady, onPlaybackUpdate }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isReady, setIsReady] = useState(false);
  const embedControllerRef = useRef<SpotifyEmbedController | null>(null);
  // From playback_update: has this episode started, and is it paused right now.
  const playStateRef = useRef({ started: false, paused: true });
  const scriptLoadedRef = useRef(false);

  useEffect(() => {
    // Check if API is already loaded
    if (window.Spotify) {
      setIsReady(true);
      return;
    }

    // Check if script is already in the DOM
    const existingScript = document.querySelector('script[src*="open.spotify.com/embed/iframe-api"]');

    if (existingScript) {
      // Script exists, wait for callback or check if already loaded
      if (window.Spotify) {
        setIsReady(true);
      } else {
        // Set up callback in case it hasn't fired
        const originalCallback = window.onSpotifyIframeApiReady;
        window.onSpotifyIframeApiReady = (IFrameAPI: SpotifyIFrameAPI) => {
          window.Spotify = IFrameAPI;
          setIsReady(true);
          if (originalCallback) {
            originalCallback(IFrameAPI);
          }
        };
      }
      return;
    }

    // Script doesn't exist, load it
    if (scriptLoadedRef.current) {
      return;
    }
    scriptLoadedRef.current = true;

    // Set up callback BEFORE loading script (required by Spotify API)
    const originalCallback = window.onSpotifyIframeApiReady;
    window.onSpotifyIframeApiReady = (IFrameAPI: SpotifyIFrameAPI) => {
      window.Spotify = IFrameAPI;
      setIsReady(true);
      // Call original if it existed
      if (originalCallback && originalCallback !== window.onSpotifyIframeApiReady) {
        originalCallback(IFrameAPI);
      }
    };

    // Load the script
    const script = document.createElement('script');
    script.src = 'https://open.spotify.com/embed/iframe-api/v1';
    script.async = true;
    script.onerror = () => {
      console.error('Failed to load Spotify iframe API');
      scriptLoadedRef.current = false;
    };
    document.head.appendChild(script);
  }, []);

  // Expose seekTo method via ref
  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      const controller = embedControllerRef.current;
      if (!controller || typeof controller.seek !== 'function') {
        // Controller not ready yet: try once more shortly.
        setTimeout(() => embedControllerRef.current?.seek?.(seconds), 300);
        return;
      }
      // controller.play() RESTARTS the episode from 0 — measured 2026-10-15 in the
      // embed, both while playing and while paused; resume() continues. The old
      // play-then-seek-150ms-later raced that restart, so a skip or timestamp tap
      // sometimes landed back near the start. Seek directly once playback has begun
      // (seek works on a playing embed: 0:12 -> seek(30) -> 0:32), resume if paused,
      // and only use play() for the very first start, when a restart costs nothing.
      if (playStateRef.current.started) {
        controller.seek(seconds);
        if (playStateRef.current.paused) controller.resume?.();
        return;
      }
      controller.play?.();
      setTimeout(() => embedControllerRef.current?.seek?.(seconds), 150);
    },
    play: () => {
      if (embedControllerRef.current && typeof embedControllerRef.current.play === 'function') {
        embedControllerRef.current.play();
      }
    },
    pause: () => {
      if (embedControllerRef.current && typeof embedControllerRef.current.pause === 'function') {
        embedControllerRef.current.pause();
      }
    },
    togglePlay: () => {
      if (embedControllerRef.current && typeof embedControllerRef.current.togglePlay === 'function') {
        embedControllerRef.current.togglePlay();
      }
    }
  }), []);

  useEffect(() => {
    if (!isReady || !containerRef.current || !window.Spotify || !uri) {
      return;
    }

    const element = containerRef.current;
    if (!element) return;

    // Clear existing content
    element.innerHTML = '';

    const options = {
      uri: uri,
      width: '100%',
      height: String(height),
    };

    const callback = (EmbedController: SpotifyEmbedController) => {
      embedControllerRef.current = EmbedController;

      // Auto-play when embed is ready (if supported by Spotify API and user has interacted)
      if (EmbedController && typeof EmbedController.play === 'function') {
        try {
          // Short delay to ensure embed is fully ready
          setTimeout(() => {
            if (embedControllerRef.current && typeof embedControllerRef.current.play === 'function') {
              embedControllerRef.current.play();
            }
          }, 100);
        } catch (error) {
          console.warn('Auto-play failed (might require user interaction first):', error);
        }
      }

      // Add playback_update event listener
      if (EmbedController && typeof EmbedController.addListener === 'function') {
        EmbedController.addListener('playback_update', (e: SpotifyPlaybackUpdate) => {
          const paused = e.data.isPaused || false;
          playStateRef.current = {
            started: playStateRef.current.started || !paused || (e.data.position || 0) > 0,
            paused,
          };
          if (onPlaybackUpdate) {
            onPlaybackUpdate({
              position: e.data.position ? Math.floor(e.data.position / 1000) : 0,
              duration: e.data.duration ? Math.floor(e.data.duration / 1000) : 0,
              isPaused: e.data.isPaused || false,
              isBuffering: e.data.isBuffering || false
            });
          }
        });
      }

      if (onPlayerReady) {
        onPlayerReady();
      }
    };

    try {
      window.Spotify.createController(element, options, callback);
    } catch (error) {
      console.error('Failed to create Spotify embed:', error);
    }

    // Cleanup
    return () => {
      if (embedControllerRef.current && typeof embedControllerRef.current.destroy === 'function') {
        try {
          embedControllerRef.current.destroy();
        } catch (error) {
          console.error('Error destroying embed:', error);
        }
        embedControllerRef.current = null;
      }
    };
  }, [isReady, uri, height]);

  if (!uri) {
    return null;
  }

  return (
    <div className={className} style={{ width: '100%' }}>
      {!isReady && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: `${height}px`,
          color: '#999',
          fontSize: '14px',
          border: '1px dashed #ccc',
          borderRadius: '4px'
        }}>
          載入 Spotify 播放器...
        </div>
      )}
      <div
        ref={containerRef}
        style={{
          height: `${height}px`,
          width: '100%',
          overflow: 'hidden',
          display: isReady ? 'block' : 'none'
        }}
      />
    </div>
  );
});

SpotifyEmbed.displayName = 'SpotifyEmbed';
