import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { SpotifyEmbedRef } from '@/components/podcast/SpotifyEmbed';

interface AudioEmbedProps {
  src: string;
  onPlayerReady?: () => void;
  onPlaybackUpdate?: (state: {
    position: number;
    duration: number;
    isPaused: boolean;
    isBuffering: boolean;
  }) => void;
}

/**
 * HTML5 audio engine for episodes without a Spotify URI (plays the GCS-hosted MP3).
 * Exposes the same imperative interface as SpotifyEmbed so GlobalPlayer can drive
 * either engine through one ref.
 */
export const AudioEmbed = forwardRef<SpotifyEmbedRef, AudioEmbedProps>(({ src, onPlayerReady, onPlaybackUpdate }, ref) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isBufferingRef = useRef(false);
  // Callers pass inline callbacks; keep them in refs so the listener effect only
  // re-runs on src change (its cleanup pauses playback).
  const onPlayerReadyRef = useRef(onPlayerReady);
  const onPlaybackUpdateRef = useRef(onPlaybackUpdate);
  onPlayerReadyRef.current = onPlayerReady;
  onPlaybackUpdateRef.current = onPlaybackUpdate;

  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      const audio = audioRef.current;
      if (!audio) return;
      audio.currentTime = seconds;
      audio.play().catch(() => { /* blocked until user gesture */ });
    },
    play: () => {
      audioRef.current?.play().catch(() => { /* blocked until user gesture */ });
    },
    pause: () => {
      audioRef.current?.pause();
    },
    togglePlay: () => {
      const audio = audioRef.current;
      if (!audio) return;
      if (audio.paused) {
        audio.play().catch(() => { /* blocked until user gesture */ });
      } else {
        audio.pause();
      }
    },
  }), []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const emit = () => {
      onPlaybackUpdateRef.current?.({
        position: Math.floor(audio.currentTime),
        duration: Number.isFinite(audio.duration) ? Math.floor(audio.duration) : 0,
        isPaused: audio.paused,
        isBuffering: isBufferingRef.current,
      });
    };
    const onWaiting = () => { isBufferingRef.current = true; emit(); };
    const onPlaying = () => { isBufferingRef.current = false; emit(); };
    const onLoadedMetadata = () => {
      emit();
      onPlayerReadyRef.current?.();
      // Mirrors SpotifyEmbed's auto-play attempt; succeeds while the opening
      // click's user activation is still fresh, otherwise stays paused.
      audio.play().catch(() => { /* blocked until user gesture */ });
    };

    audio.addEventListener('timeupdate', emit);
    audio.addEventListener('durationchange', emit);
    audio.addEventListener('play', emit);
    audio.addEventListener('pause', emit);
    audio.addEventListener('ended', emit);
    audio.addEventListener('waiting', onWaiting);
    audio.addEventListener('playing', onPlaying);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    return () => {
      audio.removeEventListener('timeupdate', emit);
      audio.removeEventListener('durationchange', emit);
      audio.removeEventListener('play', emit);
      audio.removeEventListener('pause', emit);
      audio.removeEventListener('ended', emit);
      audio.removeEventListener('waiting', onWaiting);
      audio.removeEventListener('playing', onPlaying);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.pause();
    };
  }, [src]);

  return <audio ref={audioRef} src={src} preload="metadata" />;
});

AudioEmbed.displayName = 'AudioEmbed';
