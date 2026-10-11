/**
 * Admin → Social: the free-form promo composer (drafts, including the news drafts the
 * pipeline stages), the scheduled-post queue, and comment triage. Episode posts are
 * written and published by the pipeline; there is no manual episode-copy tab.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw, Trash2, Clock, Play } from 'lucide-react';
import { PromoComposer } from '@/components/admin/PromoComposer';
import { CommentTriage } from '@/components/admin/CommentTriage';
import {
  listScheduledPosts,
  deleteScheduledPost,
  publishScheduledPostNow,
  type ScheduledPost,
} from '@/services/api/adminSocial';

const PLATFORM_LABELS: Record<string, string> = { threads: 'Threads', facebook: 'Facebook' };

const card = 'rounded-xl border border-border bg-card';

export const AdminSocialPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') === 'comments' ? 'comments' : 'promo';

  const [scheduledPosts, setScheduledPosts] = useState<ScheduledPost[]>([]);

  const fetchScheduled = useCallback(async () => {
    try {
      setScheduledPosts(await listScheduledPosts());
    } catch (e) {
      console.error('[social] list scheduled failed', e);
    }
  }, []);

  useEffect(() => {
    fetchScheduled();
  }, [fetchScheduled]);

  const handleCancelSchedule = useCallback(async (id: number) => {
    if (!window.confirm('確定要取消此排程發佈嗎？')) return;
    try {
      await deleteScheduledPost(id);
      await fetchScheduled();
    } catch (e) {
      console.error('[social] cancel schedule failed', e);
      alert('取消排程失敗，請看 console');
    }
  }, [fetchScheduled]);

  const handlePublishNow = useCallback(async (id: number) => {
    if (!window.confirm('確定要立即發佈此排程貼文嗎？')) return;
    try {
      await publishScheduledPostNow(id);
      alert('已成功立即發佈！');
      await fetchScheduled();
    } catch (e) {
      console.error('[social] publish now failed', e);
      alert('立即發佈失敗，請看 console');
    }
  }, [fetchScheduled]);

  return (
    <div className={`p-4 lg:p-8 ${tab === 'promo' ? 'max-sm:-mx-4 max-sm:px-0' : ''}`}>
      <div className={`mb-4 ${tab === 'promo' ? 'max-sm:px-3' : ''}`}>
        <h1 className="text-2xl font-bold text-foreground">Social</h1>
        <p className="text-base text-muted-foreground">
          {tab === 'promo'
            ? '自己寫一則宣傳貼文，附圖片／影片，一鍵同步貼到 Threads + Facebook。'
            : '別人在我們貼文下的留言。機器人和回給其他留言者的已自動排除，敵意與情緒留言標為略過。'}
        </p>
      </div>

      <div className={`mb-6 flex gap-1 border-b border-border ${tab === 'promo' ? 'max-sm:px-3' : ''}`}>
        {([['promo', '宣傳貼文'], ['comments', '留言']] as const).map(([key, txt]) => (
          <button
            key={key}
            onClick={() => setSearchParams({ tab: key })}
            className={`-mb-px border-b-2 px-4 py-2 text-base font-semibold ${
              tab === key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {txt}
          </button>
        ))}
      </div>

      {tab === 'promo' && (
        <div className="space-y-6">
          <PromoComposer onScheduled={fetchScheduled} />
          <div className={`${card} p-4 space-y-3 h-fit max-h-[40vh] overflow-y-auto`}>
            <div className="flex items-center justify-between border-b border-border pb-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                <Clock className="h-4 w-4" /> 排程貼文 Queue
              </h3>
              <button
                onClick={fetchScheduled}
                className="text-muted-foreground hover:text-foreground text-xs"
                title="重新整理排程"
              >
                <RefreshCw className="h-3 w-3" />
              </button>
            </div>
            <div className="space-y-2">
              {scheduledPosts.map((post) => (
                <div key={post.id} className="text-xs border border-border rounded-lg p-2.5 space-y-1.5 bg-muted/20">
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-semibold text-foreground capitalize">
                      {post.post_type === 'episode' ? '節目' : '宣傳'} · {post.platforms.map(p => PLATFORM_LABELS[p] || p).join('/')}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase ${
                      post.status === 'pending' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' :
                      post.status === 'processing' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 animate-pulse' :
                      post.status === 'posted' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300' :
                      'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300'
                    }`}>
                      {post.status === 'pending' ? '排程中' :
                       post.status === 'processing' ? '發佈中' :
                       post.status === 'posted' ? '已發佈' : '失敗'}
                    </span>
                  </div>

                  <div className="text-muted-foreground line-clamp-2">
                    {post.post_type === 'episode' ? post.episode_id : post.text}
                  </div>

                  <div className="text-[10px] text-muted-foreground flex items-center justify-between gap-2 pt-1 border-t border-border/40">
                    <span>
                      {new Date(post.scheduled_for).toLocaleString('zh-TW', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                    
                    {post.status === 'pending' && (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handlePublishNow(post.id)}
                          className="text-accent-info hover:underline flex items-center gap-0.5 font-medium"
                          title="立即發佈"
                        >
                          <Play className="h-3 w-3" /> 立即
                        </button>
                        <button
                          onClick={() => handleCancelSchedule(post.id)}
                          className="text-sentiment-bear hover:underline flex items-center gap-0.5 font-medium"
                          title="取消排程"
                        >
                          <Trash2 className="h-3 w-3" /> 取消
                        </button>
                      </div>
                    )}
                  </div>
                  {post.error_message && (
                    <div className="text-[10px] text-destructive break-words pt-1">
                      {post.error_message}
                    </div>
                  )}
                </div>
              ))}
              {!scheduledPosts.length && (
                <div className="text-xs text-muted-foreground text-center py-4">目前無排程貼文</div>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'comments' && <CommentTriage />}
    </div>
  );
};
