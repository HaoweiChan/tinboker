import React, { useState } from 'react';
import { PodMark, type PodMarkKind } from './PodMark';

interface PodAvatarProps {
  /** Cover art URL. Missing — or failing to load — falls back to PodMark. */
  src?: string | null;
  /** Show name; its first character is the fallback mark. */
  name?: string | null;
  kind?: PodMarkKind;
  /** Square side in px — sizes the fallback mark. */
  size?: number;
  /** Classes for the <img> (sizing, radius, object-fit). */
  className?: string;
}

/** Podcaster avatar: cover art when it loads, initial mark when it doesn't.
 *  Every list used a bare <img>, so one 403 from the media host left a hole in
 *  all of them. onError is what turns that into a legible fallback. */
export const PodAvatar: React.FC<PodAvatarProps> = ({ src, name, kind = 'mute', size = 28, className }) => {
  // Keyed by URL, not a bare boolean, so a re-render with a different src retries.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (!src || failedSrc === src) return <PodMark label={(name || '?').charAt(0)} kind={kind} size={size} />;
  return <img src={src} alt="" loading="lazy" onError={() => setFailedSrc(src)} className={className} />;
};
