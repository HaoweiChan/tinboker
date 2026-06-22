import { MessageSquareText } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { CommentSection } from '@/components/episode/CommentSection';

/**
 * Site-wide feedback board. Reuses the episode comment infrastructure with a
 * sentinel key, so threaded (hierarchical) comments work with no backend change.
 * `podcast_name` + `episode_id` are just the storage partition — they don't need
 * to map to a real episode.
 */
const FEEDBACK_PODCAST = '__site_feedback__';
const FEEDBACK_THREAD = 'general';

export const ReportPage: React.FC = () => (
  <>
    <SEO
      title="意見回饋 · TinBoker"
      description="TinBoker 仍在早期開發階段，歡迎登入後留言，告訴我們哪裡需要改進。"
    />
    <PageContent className="max-w-3xl">
      <div className="flex items-center gap-2.5 mb-2 pt-2">
        <MessageSquareText size={24} className="text-foreground" />
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">意見回饋</h1>
      </div>
      <p className="text-base text-muted-foreground mb-6 leading-[1.65]">
        TinBoker 還在很早期的階段，一定有很多不完美的地方。
        歡迎登入後在這裡留言 —— 不論是 bug 回報、功能許願，還是任何想法，我們都會看。
        留言可以互相回覆，一起把這個平台變得更好。
      </p>

      <CommentSection podcastName={FEEDBACK_PODCAST} episodeId={FEEDBACK_THREAD} allowPrivate />
    </PageContent>
  </>
);
