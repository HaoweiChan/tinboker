/**
 * /article/:slug — Public article detail page.
 */

import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, Clock, Eye, Calendar } from 'lucide-react';
import { PageContent } from '@/components/layout/PageContent';
import { ArticleBody } from '@/components/article/ArticleBody';
import { getArticleBySlug } from '@/services/articleService';
import type { Article } from '@/validation/schemas';

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric' });
}

export const ArticleDetail: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getArticleBySlug(slug)
      .then(setArticle)
      .catch(() => setError('找不到此文章'))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <PageContent>
        <div className="flex items-center justify-center py-20 text-muted-foreground">載入中...</div>
      </PageContent>
    );
  }
  if (error || !article) {
    return (
      <PageContent>
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <p className="text-muted-foreground">{error || '找不到此文章'}</p>
          <Link to="/" className="text-accent-info hover:underline text-sm">返回首頁</Link>
        </div>
      </PageContent>
    );
  }

  const rightRail = (
    <div className="flex flex-col gap-4">
      {/* Tags */}
      {article.tags && article.tags.length > 0 && (
        <div className="bg-card border border-border rounded-[var(--radius-md)] p-4">
          <h4 className="text-[13px] font-semibold text-muted-foreground mb-3">標籤</h4>
          <div className="flex flex-wrap gap-1.5">
            {article.tags.map((tag) => (
              <Link
                key={tag}
                to={`/topics/${encodeURIComponent(tag)}`}
                className="text-[12px] px-2.5 py-1 rounded-full bg-muted text-muted-foreground hover:bg-accent-info-soft hover:text-accent-info transition-colors"
              >
                #{tag}
              </Link>
            ))}
          </div>
        </div>
      )}
      {/* Tickers */}
      {article.tickers && article.tickers.length > 0 && (
        <div className="bg-card border border-border rounded-[var(--radius-md)] p-4">
          <h4 className="text-[13px] font-semibold text-muted-foreground mb-3">提及個股</h4>
          <div className="flex flex-col gap-1.5">
            {article.tickers.map((ticker) => (
              <Link
                key={ticker}
                to={`/stock/${encodeURIComponent(ticker)}`}
                className="text-[13px] font-medium text-accent-info hover:underline"
              >
                {ticker}
              </Link>
            ))}
          </div>
        </div>
      )}
      {/* Key points */}
      {article.key_points && article.key_points.length > 0 && (
        <div className="bg-card border border-border rounded-[var(--radius-md)] p-4">
          <h4 className="text-[13px] font-semibold text-muted-foreground mb-3">重點摘要</h4>
          <ul className="flex flex-col gap-2">
            {article.key_points.map((point, i) => (
              <li key={i} className="grid grid-cols-[10px_1fr] gap-2 text-[13px] leading-[1.5]">
                <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-emerald-500/90 shrink-0" />
                <span className="text-muted-foreground">{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  return (
    <PageContent rail={rightRail}>
      {/* Back link */}
      <Link
        to="/articles"
        className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground transition-colors mb-5"
      >
        <ChevronLeft className="h-4 w-4" />
        所有文章
      </Link>

      {/* Cover image */}
      {article.cover_image_url && (
        <img
          src={article.cover_image_url}
          alt={article.title}
          className="w-full rounded-lg object-cover max-h-[400px] mb-6"
        />
      )}

      {/* Header */}
      <header className="mb-8">
        <h1 className="text-[28px] sm:text-[32px] font-bold tracking-[-0.02em] leading-[1.25] mb-3">
          {article.title}
        </h1>
        {article.subtitle && (
          <p className="text-[17px] text-muted-foreground leading-[1.5] mb-4">{article.subtitle}</p>
        )}
        <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
          <span className="font-medium text-foreground">{article.author_name}</span>
          {article.published_at && (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                {formatDate(article.published_at)}
              </span>
            </>
          )}
          {article.read_minutes && (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {article.read_minutes} 分鐘閱讀
              </span>
            </>
          )}
          {article.view_count > 0 && (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1">
                <Eye className="h-3.5 w-3.5" />
                {article.view_count} 次瀏覽
              </span>
            </>
          )}
        </div>
      </header>

      {/* Body */}
      <ArticleBody content={article.body_content} />
    </PageContent>
  );
};
