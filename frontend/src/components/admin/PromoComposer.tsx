/**
 * Admin → Social → Promo: compose a free-form post (operator writes everything),
 * attach images/videos, and cross-post to Threads + Facebook in one click.
 *
 * Platform media rules differ and are surfaced before publish:
 *   - Threads: text, one image/video, or a 2–20 item carousel (images + videos may mix).
 *   - Facebook: photos OR one video, never both. A mixed promo is blocked on FB (the
 *     backend skips FB and still posts Threads); we warn up front so it's no surprise.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Image as ImageIcon, Film, Send, Eye, Trash2, Upload, AlertTriangle, MessageSquare, Plus, Save, FilePlus2, ChevronLeft, ChevronRight, X, Clock } from 'lucide-react';
import {
  uploadPromoMedia,
  publishPromo,
  listPromoDrafts,
  getPromoDraft,
  savePromoDraft,
  deletePromoDraft,
  type PromoMedia,
  type PromoDraftMeta,
  type PromoPublishResult,
} from '@/services/api/adminPromo';
import { schedulePost } from '@/services/api/adminSocial';

const THREADS_MAX_CHARS = 500;
const THREADS_MAX_MEDIA = 20;
const FB_MAX_ALBUM = 10;

const card = 'rounded-xl border border-border bg-card';
const labelCls = 'text-xs font-semibold uppercase tracking-wide text-muted-foreground';

const PLATFORM_LABELS: Record<string, string> = { threads: 'Threads', facebook: 'Facebook' };

/** Mirror of the backend Facebook rule — returns a zh-TW reason or null if FB is fine. */
function facebookBlockReason(media: PromoMedia[]): string | null {
  const imgs = media.filter((m) => m.type === 'image').length;
  const vids = media.filter((m) => m.type === 'video').length;
  if (imgs && vids) return 'Facebook 不支援同則貼文混合圖片與影片（將略過 FB）';
  if (vids > 1) return 'Facebook 單則貼文只能放一支影片（將略過 FB）';
  if (imgs > FB_MAX_ALBUM) return `Facebook 相簿最多 ${FB_MAX_ALBUM} 張圖片（將略過 FB）`;
  return null;
}

function summarize(result: PromoPublishResult): string {
  return Object.entries(result.platforms)
    .map(([name, r]) => {
      const label = PLATFORM_LABELS[name] || name;
      const cc = r.comment_count ? `，含 ${r.comment_count} 則留言` : '';
      if (r.error) return `${label}：錯誤（${r.error}）`;
      if (r.posted) {
        const got = r.posted_comments ?? 0;
        let s = `${label}：✅ 已發佈${got ? `（+${got} 則留言）` : ''}`;
        if (r.comment_error === 'insufficient_permission') s += '（留言未發出：權限不足，FB 需 pages_manage_engagement）';
        else if (r.comment_error === 'token_expired') s += '（留言未發出：token 已過期）';
        else if (r.comment_error) s += '（留言未發出）';
        return s;
      }
      if (r.dry_run && r.configured === false) return `${label}：未發佈（尚未設定金鑰）`;
      if (r.reason === 'dry_run') return `${label}：預覽 OK（${r.plan}${cc}）`;
      if (r.reason === 'comment_too_long') return `${label}：留言超過 ${THREADS_MAX_CHARS} 字`;
      if (r.reason === 'threads_token_expired') return `${label}：未發佈（token 已過期，請重新產生長期 token）`;
      if (r.reason === 'fb_token_expired') return `${label}：未發佈（token 已過期，請重新產生）`;
      if (r.reason === 'fb_mixed_media') return `${label}：略過（圖片＋影片不可混合）`;
      if (r.reason === 'fb_multiple_videos') return `${label}：略過（只能一支影片）`;
      if (r.reason === 'empty') return `${label}：略過（沒有內容）`;
      return `${label}：未發佈（${r.reason || '未知'}）`;
    })
    .join('　');
}

export interface PromoComposerProps {
  onScheduled?: () => void;
}

export const PromoComposer: React.FC<PromoComposerProps> = ({ onScheduled }) => {
  const [text, setText] = useState('');
  const [media, setMedia] = useState<PromoMedia[]>([]);
  const [comments, setComments] = useState<string[]>([]);
  const [toThreads, setToThreads] = useState(true);
  const [toFacebook, setToFacebook] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [drafts, setDrafts] = useState<PromoDraftMeta[]>([]);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [draftName, setDraftName] = useState('');
  const [savingDraft, setSavingDraft] = useState(false);
  const [preview, setPreview] = useState<PromoMedia | null>(null);

  const [scheduling, setScheduling] = useState(false);
  const [scheduleTime, setScheduleTime] = useState('');

  const handleSchedule = useCallback(async () => {
    if (!scheduleTime) return;
    setScheduling(true);
    setMsg(null);
    try {
      const targetTime = new Date(scheduleTime).toISOString();
      const selectedPlatforms = [toThreads && 'threads', toFacebook && 'facebook'].filter(Boolean) as string[];
      await schedulePost({
        post_type: 'promo',
        text,
        media,
        comments,
        platforms: selectedPlatforms,
        scheduled_for: targetTime,
      });
      alert('排程成功！');
      setScheduleTime('');
      if (onScheduled) {
        onScheduled();
      }
    } catch (e) {
      console.error('[promo] schedule failed', e);
      alert('排程失敗，請看 console');
    } finally {
      setScheduling(false);
    }
  }, [text, media, comments, toThreads, toFacebook, scheduleTime, onScheduled]);

  const refreshDrafts = useCallback(async () => {
    try {
      setDrafts(await listPromoDrafts());
    } catch (e) {
      console.error('[promo] drafts list failed', e);
    }
  }, []);
  useEffect(() => { refreshDrafts(); }, [refreshDrafts]);

  const newDraft = useCallback(() => {
    setDraftId(null);
    setDraftName('');
    setText('');
    setMedia([]);
    setComments([]);
    setToThreads(true);
    setToFacebook(true);
    setMsg(null);
  }, []);

  const loadDraft = useCallback(async (id: number) => {
    try {
      const d = await getPromoDraft(id);
      setText(d.text);
      setMedia(d.media.filter((m) => !!m.url)); // drop any media that failed to re-sign
      setComments(d.comments);
      setToThreads(d.platforms.includes('threads'));
      setToFacebook(d.platforms.includes('facebook'));
      setDraftId(d.id);
      setDraftName(d.name);
      setMsg(null);
    } catch (e) {
      console.error('[promo] load draft failed', e);
      setMsg('載入草稿失敗，請看 console');
    }
  }, []);

  const saveDraft = useCallback(async () => {
    setSavingDraft(true);
    try {
      const platforms = [toThreads && 'threads', toFacebook && 'facebook'].filter(Boolean) as string[];
      const saved = await savePromoDraft(
        { name: draftName.trim() || '未命名草稿', text, media, comments, platforms },
        draftId ?? undefined,
      );
      setDraftId(saved.id);
      setDraftName(saved.name);
      await refreshDrafts();
      setMsg('草稿已儲存');
    } catch (e) {
      console.error('[promo] save draft failed', e);
      setMsg('儲存草稿失敗，請看 console');
    } finally {
      setSavingDraft(false);
    }
  }, [draftName, text, media, comments, toThreads, toFacebook, draftId, refreshDrafts]);

  const removeDraft = useCallback(async () => {
    if (!draftId || !window.confirm('刪除這份草稿？')) return;
    try {
      await deletePromoDraft(draftId);
      await refreshDrafts();
      newDraft();
    } catch (e) {
      console.error('[promo] delete draft failed', e);
      setMsg('刪除草稿失敗，請看 console');
    }
  }, [draftId, refreshDrafts, newDraft]);

  const platforms = [toThreads && 'threads', toFacebook && 'facebook'].filter(Boolean) as string[];
  const fbBlock = toFacebook ? facebookBlockReason(media) : null;
  const threadsTooLong = toThreads && text.length > THREADS_MAX_CHARS;
  const commentTooLong = toThreads && comments.some((c) => c.length > THREADS_MAX_CHARS);
  const tooManyMedia = media.length > THREADS_MAX_MEDIA;
  const canSubmit = platforms.length > 0 && (text.trim() || media.length) && !busy && !uploading && !tooManyMedia && !threadsTooLong && !commentTooLong;

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setMsg(null);
    try {
      for (const file of Array.from(files)) {
        try {
          const item = await uploadPromoMedia(file);
          setMedia((prev) => [...prev, item]);
        } catch (e) {
          console.error('[promo] upload failed', file.name, e);
          setMsg(`「${file.name}」上傳失敗，請看 console`);
        }
      }
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }, []);

  const removeMedia = (url: string) => setMedia((prev) => prev.filter((m) => m.url !== url));

  const swapMedia = (i: number, j: number) =>
    setMedia((prev) => {
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const run = useCallback(async (dryRun: boolean) => {
    if (!dryRun && !window.confirm(`確定發佈到 ${platforms.map((p) => PLATFORM_LABELS[p]).join(' + ')}？`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const result = await publishPromo({ text, media, comments, platforms, dryRun });
      setMsg(summarize(result));
    } catch (e) {
      console.error('[promo] publish failed', e);
      setMsg('發佈失敗，請看 console');
    } finally {
      setBusy(false);
    }
  }, [text, media, comments, platforms]);

  return (
    <div className="max-w-2xl space-y-6">
      {/* Drafts */}
      <div className={`${card} p-4`}>
        <div className={`${labelCls} mb-3`}>草稿 Drafts</div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={draftId ?? ''}
            onChange={(e) => (e.target.value ? loadDraft(Number(e.target.value)) : newDraft())}
            className="rounded-lg border border-input bg-card px-3 py-2 text-base text-foreground focus:border-accent-info focus:outline-none"
          >
            <option value="">— 載入草稿 —</option>
            {drafts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}（{d.media_count} 媒體・{d.comment_count} 留言）
              </option>
            ))}
          </select>
          <input
            type="text"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            placeholder="草稿名稱…"
            className="min-w-[8rem] flex-1 rounded-lg border border-input bg-card px-3 py-2 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none"
          />
          <button
            onClick={saveDraft}
            disabled={savingDraft || uploading}
            title={draftId ? '更新這份草稿' : '另存為新草稿'}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-semibold text-foreground hover:bg-muted disabled:opacity-60"
          >
            <Save className={`h-4 w-4 ${savingDraft ? 'animate-pulse' : ''}`} />
            {savingDraft ? '儲存中…' : draftId ? '更新草稿' : '儲存草稿'}
          </button>
          <button
            onClick={newDraft}
            title="清空，開新草稿"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-medium text-foreground hover:bg-muted"
          >
            <FilePlus2 className="h-4 w-4" /> 新草稿
          </button>
          {draftId && (
            <button
              onClick={removeDraft}
              title="刪除這份草稿"
              className="inline-flex items-center gap-2 rounded-lg border border-sentiment-bear/40 px-3 py-2 text-base font-medium text-sentiment-bear hover:bg-sentiment-bear-soft"
            >
              <Trash2 className="h-4 w-4" /> 刪除
            </button>
          )}
        </div>
      </div>

      {/* Text */}
      <div className={`${card} p-4`}>
        <div className={`${labelCls} mb-2`}>貼文內容 Post</div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder="寫下你的宣傳貼文…（Threads 上限 500 字，Facebook 無實際限制）"
          className="w-full resize-y rounded-lg border border-input bg-card p-3 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
        />
        <div className={`mt-1 text-right text-xs ${threadsTooLong ? 'text-sentiment-bear' : 'text-muted-foreground'}`}>
          {text.length} 字{threadsTooLong ? `（超過 Threads ${THREADS_MAX_CHARS} 字上限）` : ''}
        </div>
      </div>

      {/* Media */}
      <div className={`${card} p-4`}>
        <div className="mb-3 flex items-center justify-between">
          <div className={labelCls}>媒體 Media（圖片／影片）</div>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-base font-medium text-foreground hover:bg-muted disabled:opacity-60"
          >
            <Upload className={`h-4 w-4 ${uploading ? 'animate-pulse' : ''}`} />
            {uploading ? '上傳中…' : '新增媒體'}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,video/*"
            multiple
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {media.length === 0 ? (
          <div className="text-base text-muted-foreground">尚未加入任何媒體（純文字貼文也可以）</div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {media.map((m, i) => (
              <div key={m.url} className="relative overflow-hidden rounded-lg border border-border bg-muted">
                <button
                  type="button"
                  onClick={() => setPreview(m)}
                  title="點擊放大檢視"
                  className="block w-full"
                >
                  {m.type === 'image' ? (
                    <img src={m.url} alt={m.filename || ''} className="h-28 w-full object-cover" />
                  ) : (
                    <video src={m.url} className="h-28 w-full object-cover" muted />
                  )}
                </button>
                <div className="absolute left-1 top-1 inline-flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-2xs font-medium text-white">
                  {m.type === 'image' ? <ImageIcon className="h-3 w-3" /> : <Film className="h-3 w-3" />}
                  {i + 1}
                </div>
                <button
                  onClick={() => removeMedia(m.url)}
                  title="移除"
                  className="absolute right-1 top-1 rounded bg-black/60 p-1 text-white hover:bg-black/80"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
                <div className="absolute inset-x-1 bottom-1 flex justify-between">
                  <button
                    onClick={() => swapMedia(i, i - 1)}
                    disabled={i === 0}
                    title="往前移"
                    className="rounded bg-black/60 p-1 text-white hover:bg-black/80 disabled:opacity-30"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => swapMedia(i, i + 1)}
                    disabled={i === media.length - 1}
                    title="往後移"
                    className="rounded bg-black/60 p-1 text-white hover:bg-black/80 disabled:opacity-30"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {tooManyMedia && (
          <div className="mt-2 text-xs text-sentiment-bear">Threads 最多 {THREADS_MAX_MEDIA} 個媒體，請移除多餘的。</div>
        )}
      </div>

      {/* Comments — text-only follow-ups (Threads reply chain / FB comments) */}
      <div className={`${card} p-4`}>
        <div className="mb-3 flex items-center justify-between">
          <div className={`${labelCls} flex items-center gap-1.5`}>
            <MessageSquare className="h-3.5 w-3.5" /> 留言 Comments（純文字，依序串接在貼文下）
          </div>
          <button
            onClick={() => setComments((prev) => [...prev, ''])}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-base font-medium text-foreground hover:bg-muted"
          >
            <Plus className="h-4 w-4" /> 新增留言
          </button>
        </div>
        {comments.length === 0 ? (
          <div className="text-base text-muted-foreground">沒有留言（可留空）</div>
        ) : (
          <div className="space-y-3">
            {comments.map((c, i) => {
              const over = toThreads && c.length > THREADS_MAX_CHARS;
              return (
                <div key={i} className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{i + 1}</span>
                    <button
                      onClick={() => setComments((prev) => prev.filter((_, idx) => idx !== i))}
                      title="移除留言"
                      className="text-muted-foreground hover:text-sentiment-bear"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <textarea
                    value={c}
                    onChange={(e) => setComments((prev) => prev.map((v, idx) => (idx === i ? e.target.value : v)))}
                    rows={2}
                    placeholder="這則留言的內容…"
                    className="w-full resize-y rounded-lg border border-input bg-card p-3 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
                  />
                  <div className={`mt-1 text-right text-xs ${over ? 'text-sentiment-bear' : 'text-muted-foreground'}`}>
                    {c.length} 字{over ? `（超過 Threads ${THREADS_MAX_CHARS} 字上限）` : ''}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Platforms */}
      <div className={`${card} p-4`}>
        <div className={`${labelCls} mb-3`}>發佈到</div>
        <div className="flex flex-wrap gap-4">
          <label className="inline-flex items-center gap-2 text-base text-foreground">
            <input type="checkbox" checked={toThreads} onChange={(e) => setToThreads(e.target.checked)} className="h-4 w-4" />
            Threads
          </label>
          <label className="inline-flex items-center gap-2 text-base text-foreground">
            <input type="checkbox" checked={toFacebook} onChange={(e) => setToFacebook(e.target.checked)} className="h-4 w-4" />
            Facebook
          </label>
        </div>
        {fbBlock && (
          <div className="mt-3 inline-flex items-start gap-2 rounded-lg border border-sentiment-bear/40 bg-sentiment-bear-soft px-3 py-2 text-base text-sentiment-bear">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{fbBlock} — Threads 仍會照常發佈。</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => run(true)}
            disabled={!canSubmit || busy || scheduling}
            title="不實際發佈，只檢查每個平台會怎麼貼"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-base font-semibold text-foreground hover:bg-muted disabled:opacity-60"
          >
            <Eye className="h-4 w-4" /> 預覽
          </button>
          <button
            onClick={() => run(false)}
            disabled={!canSubmit || busy || scheduling}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-base font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            <Send className={`h-4 w-4 ${busy ? 'animate-pulse' : ''}`} />
            {busy ? '處理中…' : '發佈'}
          </button>
        </div>

        {/* Scheduling Controls */}
        <div className="flex items-center gap-2 border-l border-border pl-4">
          <input
            type="datetime-local"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            className="rounded-lg border border-input bg-card px-2 py-1.5 text-base text-foreground focus:border-accent-info focus:outline-none"
          />
          <button
            onClick={handleSchedule}
            disabled={!canSubmit || !scheduleTime || scheduling || busy}
            title="設定日期時間後排程發佈"
            className="inline-flex items-center gap-1.5 rounded-lg border border-primary px-3 py-2 text-base font-semibold text-primary hover:bg-primary/10 disabled:opacity-60"
          >
            <Clock className="h-4 w-4" />
            {scheduling ? '排程中…' : '排程發佈'}
          </button>
        </div>
      </div>

      {msg && (
        <div className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-base text-foreground">
          {msg}
        </div>
      )}

      {/* Click-to-enlarge lightbox */}
      {preview && (
        <div
          onClick={() => setPreview(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        >
          <button
            onClick={() => setPreview(null)}
            title="關閉"
            className="absolute right-4 top-4 rounded-full bg-black/60 p-2 text-white hover:bg-black/80"
          >
            <X className="h-5 w-5" />
          </button>
          {preview.type === 'image' ? (
            <img onClick={(e) => e.stopPropagation()} src={preview.url} alt={preview.filename || ''} className="max-h-full max-w-full rounded-lg object-contain" />
          ) : (
            <video onClick={(e) => e.stopPropagation()} src={preview.url} controls autoPlay className="max-h-full max-w-full rounded-lg" />
          )}
        </div>
      )}
    </div>
  );
};
