import React from 'react';
import { Link } from 'react-router-dom';
import { normalizeCjkMarkerSpacing } from '@/utils/summaryParser';

/** Inline link markers the agents pipeline emits inside summaries / insights:
 *    [label](#ticker:SYMBOL) -> stock page link
 *    [label](#tag:ID)        -> topic page link
 *  Any other `[label](target)` (other scheme, bare anchor, external URL) renders as
 *  its plain label, so raw markdown never leaks into the prose. */
const MARKDOWN_LINK = /\[([^\]]+)\]\(([^)]+)\)/g;

const LINK_CLASS = 'text-accent-info hover:underline font-medium';

export const MentionText: React.FC<{ text: string }> = ({ text }) => {
  if (!text) return null;
  text = normalizeCjkMarkerSpacing(text);
  const parts: React.ReactNode[] = [];
  const re = new RegExp(MARKDOWN_LINK);
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const label = m[1];
    const target = m[2].trim();
    if (target.startsWith('#ticker:')) {
      const symbol = target.slice('#ticker:'.length).trim().toUpperCase();
      parts.push(<Link key={key++} to={`/stock/${encodeURIComponent(symbol)}`} className={LINK_CLASS}>{label}</Link>);
    } else if (target.startsWith('#tag:')) {
      const id = target.slice('#tag:'.length).trim();
      parts.push(<Link key={key++} to={`/topics/${encodeURIComponent(id)}`} className={LINK_CLASS}>{label}</Link>);
    } else {
      // Unknown target — drop the markup, keep the readable label.
      parts.push(label);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
};
