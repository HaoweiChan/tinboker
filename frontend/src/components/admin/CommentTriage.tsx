/**
 * Admin → Social → 留言: the replies people leave on our Threads posts, triaged.
 *
 * Rules live on the backend, not here: bots and replies aimed at another commenter
 * never arrive; hostile/noise/promo arrive already marked 略過. There is no hide action —
 * a comment is answered or it is ignored. What lands in 待處理
 * is what someone judged worth answering, with a draft to edit. Only plain praise is
 * ever answered unattended — anything carrying a factual claim, a question, or a
 * position waits for this screen, because a wrong number from a finance account is
 * worse than a slow reply.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Send, X, ExternalLink, Check } from 'lucide-react';
import {
  listThreadsComments,
  syncThreadsComments,
  replyToComment,
  skipComment,
  type ThreadsCommentItem,
  type CommentStatus,
} from '@/services/api/adminSocial';

const card = 'rounded-xl border border-border bg-card';

const CATEGORY_LABELS: Record<string, string> = {
  praise: '稱讚',
  question: '提問',
  substantive: '論點',
  hostile: '敵意',
  noise: '情緒',
  promo: '業配',
  bot: '機器人',
};

const CATEGORY_TONE: Record<string, string> = {
  praise: 'bg-emerald-500/10 text-emerald-600',
  question: 'bg-sky-500/10 text-sky-600',
  substantive: 'bg-primary/10 text-primary',
  hostile: 'bg-destructive/10 text-destructive',
  noise: 'bg-muted text-muted-foreground',
  promo: 'bg-muted text-muted-foreground',
  bot: 'bg-muted text-muted-foreground',
};

const TABS: [CommentStatus | 'all', string][] = [
  ['pending', '待處理'],
  ['replied', '已回覆'],
  ['ignored', '已略過'],
  ['all', '全部'],
];

export const CommentTriage: React.FC = () => {
  const [status, setStatus] = useState<CommentStatus | 'all'>('pending');
  const [items, setItems] = useState<ThreadsCommentItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listThreadsComments(status);
      setItems(list);
      setDrafts(Object.fromEntries(list.map((c) => [c.id, c.draft])));
    } catch (e) {
      setNote(e instanceof Error ? e.message : '讀取失敗');
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { void fetchList(); }, [fetchList]);

  const runSync = async () => {
    setLoading(true);
    setNote(null);
    try {
      const r = await syncThreadsComments();
      setNote(r.configured
        ? `掃了 ${r.scanned} 篇貼文，新留言 ${r.new} 則（自動回覆 ${r.auto_replied}、待處理 ${r.needs_review}、略過 ${r.ignored}）`
        : 'Threads 未設定，無法抓留言');
      await fetchList();
    } catch (e) {
      setNote(e instanceof Error ? e.message : '同步失敗');
    } finally {
      setLoading(false);
    }
  };

  const act = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusyId(id);
    setNote(null);
    try {
      await fn();
      setNote(ok);
      await fetchList();
    } catch (e) {
      setNote(e instanceof Error ? e.message : '操作失敗');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setStatus(key)}
              className={`rounded-lg px-3 py-1.5 text-base font-medium ${
                status === key ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={runSync}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-medium text-foreground hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> 抓新留言
        </button>
      </div>

      {note && (
        <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-base text-muted-foreground">
          {note}
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className={`${card} p-8 text-center text-base text-muted-foreground`}>
          沒有留言。
        </div>
      )}

      <div className="space-y-3">
        {items.map((c) => (
          <div key={c.id} className={`${card} p-4`}>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">@{c.username ?? '—'}</span>
              {c.category && (
                <span className={`rounded px-1.5 py-0.5 font-medium ${CATEGORY_TONE[c.category] ?? 'bg-muted'}`}>
                  {CATEGORY_LABELS[c.category] ?? c.category}
                </span>
              )}
              {c.auto && (
                <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-medium text-emerald-600">
                  自動回覆
                </span>
              )}
              {c.posted_at && <span>{c.posted_at.slice(0, 16).replace('T', ' ')}</span>}
              <a
                href={c.permalink}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                原貼文 <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            <p className="whitespace-pre-wrap text-base text-foreground">{c.text}</p>
            {c.reason && <p className="mt-1 text-sm text-muted-foreground">判斷：{c.reason}</p>}

            {c.status === 'replied' ? (
              <p className="mt-3 flex items-start gap-2 rounded-lg bg-muted/40 p-3 text-base text-muted-foreground">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                <span className="whitespace-pre-wrap">{c.draft}</span>
              </p>
            ) : (
              <>
                <textarea
                  value={drafts[c.id] ?? ''}
                  onChange={(e) => setDrafts((d) => ({ ...d, [c.id]: e.target.value }))}
                  rows={3}
                  placeholder="沒有草稿 — 這則值得回但模型沒有東西可補充，自己寫一句"
                  className="mt-3 w-full rounded-lg border border-border bg-background p-3 text-base text-foreground"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => act(c.id, () => replyToComment(c.id, drafts[c.id] ?? ''), '已回覆')}
                    disabled={busyId === c.id || !(drafts[c.id] ?? '').trim()}
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-base font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" /> 送出回覆
                  </button>
                  <button
                    onClick={() => act(c.id, () => skipComment(c.id), '已略過')}
                    disabled={busyId === c.id}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base text-foreground hover:bg-muted disabled:opacity-50"
                  >
                    <X className="h-4 w-4" /> 略過
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
