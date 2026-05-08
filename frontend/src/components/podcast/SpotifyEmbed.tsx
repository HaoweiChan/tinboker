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

declare global {
  interface Window {
    onSpotifyIframeApiReady?: (IFrameAPI: any) => void;
    Spotify?: any;
  }
}

export const SpotifyEmbed = forwardRef<SpotifyEmbedRef, SpotifyEmbedProps>(({ uri, className = '', height = 352, onPlayerReady, onPlaybackUpdate }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isReady, setIsReady] = useState(false);
  const embedControllerRef = useRef<any>(null);
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
        window.onSpotifyIframeApiReady = (IFrameAPI: any) => {
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
    window.onSpotifyIframeApiReady = (IFrameAPI: any) => {
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
      if (embedControllerRef.current) {
        try {
          const controller = embedControllerRef.current;

          if (typeof controller.seek !== 'function') {
            console.warn('Seek function not available on controller');
            return;
          }

          // Always use play-then-seek strategy for reliability
          // The Spotify API is unreliable when seeking on an already-playing embed
          // Calling play() first ensures the player is in a known state
          // Start playback first (this is idempotent if already playing)
          if (typeof controller.play === 'function') {
            controller.play();
          } else if (typeof controller.togglePlay === 'function') {
            controller.togglePlay();
          }

          // Seek after a short delay to ensure playback is active
          setTimeout(() => {
            if (embedControllerRef.current && typeof embedControllerRef.current.seek === 'function') {
              try {
                embedControllerRef.current.seek(seconds);
              } catch (seekError) {
                console.warn('[SpotifyEmbed] First seek attempt failed, retrying:', seekError);
                // Retry after a longer delay
                setTimeout(() => {
                  if (embedControllerRef.current && typeof embedControllerRef.current.seek === 'function') {
                    try {
                      embedControllerRef.current.seek(seconds);
                    } catch (retryError) {
                      console.error('[SpotifyEmbed] Retry seek failed:', retryError);
                    }
                  }
                }, 500);
              }
            }
          }, 150);
        } catch (error) {
          console.error('[SpotifyEmbed] Failed to seek:', error);
        }
      } else {
        console.warn('[SpotifyEmbed] Controller not ready, deferring seek');
        // Defer seek until controller is ready
        setTimeout(() => {
          if (embedControllerRef.current && typeof embedControllerRef.current.seek === 'function') {
            try {
              embedControllerRef.current.seek(seconds);
            } catch (retryError) {
              console.error('[SpotifyEmbed] Deferred seek failed:', retryError);
            }
          }
        }, 300);
      }
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

    const callback = (EmbedController: any) => {
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
        EmbedController.addListener('playback_update', (e: any) => {
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
