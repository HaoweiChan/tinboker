import { Link } from 'react-router-dom';
import type { Body } from '../../../shared/sitePages.js';

/** Renders a shared-copy body (shared/sitePages.js): plain text, in-site links and
 *  external links. The crawler middleware renders the same data as HTML. */
export function Rich({ body }: { body: Body }) {
  if (typeof body === 'string') return <>{body}</>;
  return (
    <>
      {body.map((seg, i) => {
        if (typeof seg === 'string') return <span key={i}>{seg}</span>;
        if ('to' in seg) return <Link key={i} to={seg.to} className="text-accent-info hover:underline">{seg.text}</Link>;
        const external = !seg.href.startsWith('mailto:');
        return (
          <a key={i} href={seg.href} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})} className="text-accent-info hover:underline">
            {seg.text}
          </a>
        );
      })}
    </>
  );
}
