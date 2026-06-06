/**
 * ArticleBody — Markdown renderer for articles.
 *
 * Extends the SummaryMarkdown component map with:
 *   - img/figure renderer (responsive, lazy-loading, caption from title)
 *   - Same #ticker: / #tag: marker grammar
 *   - rehype-raw stays OFF (no HTML sanitizer needed)
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';

interface ArticleBodyProps {
  content: string;
}

const FigureImage: React.FC<{
  src?: string;
  alt?: string;
  title?: string;
}> = ({ src, alt, title }) => {
  const [errored, setErrored] = useState(false);
  if (!src || errored) return null;
  return (
    <figure className="my-6">
      <img
        src={src}
        alt={alt || ''}
        title={title || undefined}
        loading="lazy"
        onError={() => setErrored(true)}
        className="w-full rounded-lg object-cover max-h-[520px]"
      />
      {title && (
        <figcaption className="mt-2 text-center text-[13px] text-muted-foreground">
          {title}
        </figcaption>
      )}
    </figure>
  );
};

export const ArticleBody: React.FC<ArticleBodyProps> = ({ content }) => {
  if (!content?.trim()) return null;

  return (
    <div className="prose-article text-[15px] leading-[1.8] text-foreground/90">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h2 className="text-[24px] sm:text-[26px] font-bold tracking-[-0.02em] leading-[1.3] mt-10 first:mt-0 mb-4">
              {children}
            </h2>
          ),
          h2: ({ children }) => (
            <h3 className="text-[20px] sm:text-[22px] font-semibold tracking-[-0.01em] leading-[1.35] mt-8 mb-3">
              {children}
            </h3>
          ),
          h3: ({ children }) => (
            <h4 className="text-[17px] font-semibold text-foreground/95 mt-6 mb-2">
              {children}
            </h4>
          ),
          h4: ({ children }) => (
            <h5 className="text-[15px] font-semibold text-foreground/90 mt-5 mb-1.5">
              {children}
            </h5>
          ),
          p: ({ children, node }) => {
            const child = node?.children?.[0];
            if (
              node?.children?.length === 1 &&
              child &&
              'tagName' in child &&
              child.tagName === 'img'
            ) {
              return <>{children}</>;
            }
            return <p className="mb-4 last:mb-0">{children}</p>;
          },
          img: ({ src, alt, title }) => (
            <FigureImage src={src} alt={alt} title={title} />
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 mb-4 flex flex-col gap-1.5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 mb-4 flex flex-col gap-1.5">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-[1.7] pl-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-3 border-primary/40 pl-4 my-5 text-muted-foreground italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-8 border-border" />,
          code: ({ children, className }) => {
            const isBlock = className?.includes('language-');
            if (isBlock) {
              return (
                <code className={`${className} block bg-muted/50 rounded-md p-4 text-[13px] overflow-x-auto`}>
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-muted/60 text-[13px] px-1.5 py-0.5 rounded font-mono">
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="mb-4">{children}</pre>,
          a: ({ href, children }) => {
            const h = (href || '').trim();
            if (h.startsWith('#ticker:')) {
              const symbol = h.slice('#ticker:'.length).trim().toUpperCase();
              return (
                <Link
                  to={`/stock/${encodeURIComponent(symbol)}`}
                  className="text-accent-info hover:underline font-medium"
                >
                  {children}
                </Link>
              );
            }
            if (h.startsWith('#tag:')) {
              const id = h.slice('#tag:'.length).trim();
              return (
                <Link
                  to={`/topics/${encodeURIComponent(id)}`}
                  className="hover:text-accent-info hover:underline transition-colors"
                >
                  {children}
                </Link>
              );
            }
            return (
              <a
                href={h}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-info hover:underline"
              >
                {children}
              </a>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto mb-4">
              <table className="w-full border-collapse text-[14px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-border bg-muted/40 px-3 py-2 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-3 py-2">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
