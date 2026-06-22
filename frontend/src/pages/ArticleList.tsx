/**
 * /articles — Public article listing page.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock, FileText } from 'lucide-react';
import { PageContent } from '@/components/layout/PageContent';
import { getPublishedArticles } from '@/services/articleService';
import type { ArticleListItem } from '@/validation/schemas';
import { formatDate } from '@/lib/date';

const ArticleCard: React.FC<{ article: ArticleListItem }> = ({ article }) => (
  <Link
    to={`/article/${article.slug}`}
    className="block bg-card border border-border rounded-[var(--radius-md)] p-4 transition-colors hover:border-foreground/25"
  >
    {article.cover_image_url && (
      <img
        src={article.cover_image_url}
        alt={article.title}
        className="w-full rounded-md object-cover h-[180px] mb-3"
        loading="lazy"
      />
    )}
    <h3 className="text-lg font-medium leading-[1.35] tracking-[-0.005em] mb-2 text-foreground line-clamp-2">
      {article.title}
    </h3>
    {article.subtitle && (
      <p className="text-sm text-muted-foreground mb-2 line-clamp-2">{article.subtitle}</p>
    )}
    {article.key_points && article.key_points.length > 0 && (
      <ul className="grid gap-1 text-sm leading-[1.5] text-muted-foreground mb-3">
        {article.key_points.slice(0, 2).map((point, i) => (
          <li key={i} className="grid grid-cols-[10px_1fr] gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-accent-info shrink-0" />
            <span className="line-clamp-1">{point}</span>
          </li>
        ))}
      </ul>
    )}
    {article.tags && article.tags.length > 0 && (
      <div className="flex gap-1.5 flex-wrap mb-3">
        {article.tags.slice(0, 4).map((tag) => (
          <span key={tag} className="text-2xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
            #{tag}
          </span>
        ))}
      </div>
    )}
    <div className="flex items-center gap-2.5 pt-2.5 border-t border-border text-xs text-muted-foreground">
      <span>{article.author_name}</span>
      {article.published_at && (
        <>
          <span aria-hidden>·</span>
          <span>{formatDate(article.published_at)}</span>
        </>
      )}
      {article.read_minutes && (
        <>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {article.read_minutes} 分鐘
          </span>
        </>
      )}
    </div>
  </Link>
);

export const ArticleList: React.FC = () => {
  const [articles, setArticles] = useState<ArticleListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPublishedArticles(50, 0)
      .then(setArticles)
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageContent>
      <header className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-[-0.02em]">文章</h1>
        <p className="text-base text-muted-foreground mt-1">深度分析與市場觀察</p>
      </header>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">載入中...</div>
      ) : articles.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
          <FileText className="h-10 w-10 opacity-40" />
          <p>尚無文章</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((a) => (
            <ArticleCard key={a.id} article={a} />
          ))}
        </div>
      )}
    </PageContent>
  );
};
