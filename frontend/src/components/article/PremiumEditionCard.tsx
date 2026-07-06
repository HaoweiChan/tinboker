/**
 * PremiumEditionCard — states what the subscriber gets in the paid full edition
 * (issue #425, acceptance criterion #2).
 *
 * Renders only when the article carries a premium pitch or an includes list, so
 * plain public posts are unaffected.
 */

import { Check, Crown } from 'lucide-react';
import { SubscribeCTA } from './SubscribeCTA';
import type { Article } from '@/validation/schemas';

interface PremiumEditionCardProps {
  article: Pick<Article, 'premium_pitch' | 'premium_includes' | 'subscribe_url'>;
}

export const PremiumEditionCard: React.FC<PremiumEditionCardProps> = ({ article }) => {
  const includes = (article.premium_includes || []).filter(Boolean);
  const pitch = article.premium_pitch?.trim();

  if (!pitch && includes.length === 0) return null;

  return (
    <section
      aria-label="完整版內容"
      className="rounded-[var(--radius-md)] border border-primary/25 bg-gradient-to-b from-primary/[0.06] to-transparent p-5"
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-primary/15 text-primary">
          <Crown className="h-4 w-4" />
        </span>
        <h3 className="text-base font-semibold text-foreground">完整版收錄</h3>
        <span className="ml-auto rounded-full bg-primary/15 px-2 py-0.5 text-2xs font-medium text-primary">
          付費版
        </span>
      </div>

      {pitch && <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{pitch}</p>}

      {includes.length > 0 && (
        <ul className="mt-3 grid gap-2">
          {includes.map((item, i) => (
            <li key={i} className="grid grid-cols-[18px_1fr] gap-2 text-sm leading-[1.5]">
              <Check className="mt-[3px] h-4 w-4 shrink-0 text-primary" />
              <span className="text-foreground">{item}</span>
            </li>
          ))}
        </ul>
      )}

      <SubscribeCTA
        subscribeUrl={article.subscribe_url}
        title="解鎖完整版"
        description="訂閱後可閱讀完整分析與後續更新。"
        cta="訂閱 Substack"
        className="mt-4"
      />
    </section>
  );
};
