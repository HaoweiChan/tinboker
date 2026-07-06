/**
 * NextBestActions — the "where do I go next" section on article pages
 * (issue #425, acceptance criterion #3).
 *
 * Points readers deeper into the intelligence product: related articles,
 * related tickers/topics, and the subscription CTA.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Compass } from 'lucide-react';
import { SubscribeCTA } from './SubscribeCTA';
import { getRelatedArticles } from '@/services/articleService';
import type { Article, ArticleListItem } from '@/validation/schemas';

interface NextBestActionsProps {
  article: Article;
}

export const NextBestActions: React.FC<NextBestActionsProps> = ({ article }) => {
  const [related, setRelated] = useState<ArticleListItem[]>([]);

  useEffect(() => {
    let active = true;
    getRelatedArticles(article, 3)
      .then((items) => {
        if (active) setRelated(items);
      })
      .catch(() => {
        if (active) setRelated([]);
      });
    return () => {
      active = false;
    };
  }, [article]);

  const tags = (article.tags || []).slice(0, 6);
  const tickers = (article.tickers || []).slice(0, 6);
  const hasTopics = tags.length > 0 || tickers.length > 0;

  return (
    <section aria-label="下一步" className="mt-10 border-t border-border pt-8">
      <div className="mb-4 flex items-center gap-2">
        <Compass className="h-5 w-5 text-accent-info" />
        <h2 className="text-lg font-semibold text-foreground">接下來</h2>
      </div>

      <div className="grid gap-4">
        {/* Related articles */}
        {related.length > 0 && (
          <div className="rounded-[var(--radius-md)] border border-border bg-card p-4">
            <h4 className="mb-3 text-sm font-semibold text-muted-foreground">延伸閱讀</h4>
            <ul className="flex flex-col divide-y divide-border">
              {related.map((a) => (
                <li key={a.id}>
                  <Link
                    to={`/article/${a.slug}`}
                    className="group flex items-center justify-between gap-3 py-2.5"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-foreground group-hover:text-accent-info">
                        {a.title}
                      </span>
                      {a.subtitle && (
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {a.subtitle}
                        </span>
                      )}
                    </span>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-accent-info" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Related tickers / topics */}
        {hasTopics && (
          <div className="rounded-[var(--radius-md)] border border-border bg-card p-4">
            <h4 className="mb-3 text-sm font-semibold text-muted-foreground">相關個股與主題</h4>
            <div className="flex flex-wrap gap-1.5">
              {tickers.map((ticker) => (
                <Link
                  key={`t-${ticker}`}
                  to={`/stock/${encodeURIComponent(ticker)}`}
                  className="rounded-full bg-accent-info-soft px-2.5 py-1 text-xs font-medium text-accent-info hover:bg-accent-info/20"
                >
                  {ticker}
                </Link>
              ))}
              {tags.map((tag) => (
                <Link
                  key={`g-${tag}`}
                  to={`/topics/${encodeURIComponent(tag)}`}
                  className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent-info-soft hover:text-accent-info"
                >
                  #{tag}
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Subscription CTA */}
        <SubscribeCTA subscribeUrl={article.subscribe_url} />
      </div>
    </section>
  );
};
