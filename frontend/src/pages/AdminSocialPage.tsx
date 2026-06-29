/**
 * Admin → Social: review and edit the human-tone Threads copy (a grand-summary
 * post + one comment per slide) and preview the marp card images that go with it.
 * Threads credentials are wired up separately; this page only gets the copy +
 * images ready and editable.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Save, Check, MessageSquare, Image as ImageIcon, Eye, Wand2, Send, AlertCircle, ExternalLink, Plus, Trash2, Clock, Play } from 'lucide-react';
import { SlideViewer } from '@/components/common/SlideViewer';
import { PromoComposer } from '@/components/admin/PromoComposer';
import {
  listSocialEpisodes,
  getSocialEpisode,
  saveSocialEpisode,
  generateSocialEpisode,
  renderSocialCards,
  publishSocialEpisode,
  schedulePost,
  listScheduledPosts,
  deleteScheduledPost,
  publishScheduledPostNow,
  type SocialEpisodeListItem,
  type SocialEpisodeBundle,
  type SocialComment,
  type PublishResult,
  type PublishPlatformResult,
  type ScheduledPost,
} from '@/services/api/adminSocial';

const PLATFORM_LABELS: Record<string, string> = { threads: 'Threads', facebook: 'Facebook' };

/** Map a raw backend reason/error to an actionable zh-TW hint. */
function friendlyReason(raw?: string): string {
  const s = raw || '未知錯誤';
  if (/svg|media|download|requirements|不符/i.test(s))
    return '圖片格式不支援（卡片為 SVG，平台只接受 PNG/JPEG）— 改以純文字發佈';
  if (/190|session has expired|token|expired/i.test(s)) return '存取權杖失效，請更新金鑰';
  if (/#?200|permission|publish_actions/i.test(s)) return '權限不足（需要粉專貼文／留言權限）';
  return s;
}

/** Human-readable one-liner for a single platform's publish outcome. */
function platformStatusText(r: PublishPlatformResult): string {
  if (r.posted) {
    const n = r.reply_count ?? r.comment_count;
    return n != null ? `已發佈（含 ${n} 則留言）` : '已發佈';
  }
  if (r.reason === 'already_posted') return '先前已發佈過，略過';
  if (r.reason === 'no_postable_content') return '沒有可發佈內容';
  if (r.dry_run && r.configured === false) return '尚未設定金鑰，未發佈';
  return `發佈失敗：${friendlyReason(r.reason || r.error)}`;
}

/** Public URL of the live post, when the platform returned an id we can link to. */
function platformPostUrl(name: string, r: PublishPlatformResult): string | null {
  if (!r.posted) return null;
  const fbId = r.post_id || r.root_post_id;
  if (name === 'facebook' && fbId) return `https://www.facebook.com/${fbId}`;
  // Threads exposes only a media id (no public permalink without an extra API call) — skip.
  return null;
}

function fmtDate(ms: number): string {
  if (!ms) return '';
  const d = new Date(ms);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

const card = 'rounded-xl border border-border bg-card';
const label = 'text-xs font-semibold uppercase tracking-wide text-muted-foreground';

export const AdminSocialPage: React.FC = () => {
  const [episodes, setEpisodes] = useState<SocialEpisodeListItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bundle, setBundle] = useState<SocialEpisodeBundle | null>(null);
  const [loadingBundle, setLoadingBundle] = useState(false);
  const [post, setPost] = useState('');
  const [comments, setComments] = useState<SocialComment[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [showComposed, setShowComposed] = useState(false);
  const [tab, setTab] = useState<'episodes' | 'promo'>('episodes');

  const [scheduledPosts, setScheduledPosts] = useState<ScheduledPost[]>([]);
  const [scheduling, setScheduling] = useState(false);
  const [scheduleTime, setScheduleTime] = useState('');

  const fetchScheduled = useCallback(async () => {
    try {
      setScheduledPosts(await listScheduledPosts());
    } catch (e) {
      console.error('[social] list scheduled failed', e);
    }
  }, []);

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
      // Refetch list to update badges
      setEpisodes(await listSocialEpisodes(40));
    } catch (e) {
      console.error('[social] publish now failed', e);
      alert('立即發佈失敗，請看 console');
    }
  }, [fetchScheduled]);

  const handleSchedule = useCallback(async () => {
    if (!selectedId || !scheduleTime) return;
    setScheduling(true);
    try {
      await saveSocialEpisode(selectedId, { post, comments });
      setSaved(true);

      const targetTime = new Date(scheduleTime).toISOString();
      await schedulePost({
        post_type: 'episode',
        episode_id: selectedId,
        platforms: ['threads', 'facebook'],
        scheduled_for: targetTime,
      });

      alert('排程成功！');
      setScheduleTime('');
      fetchScheduled();
    } catch (e) {
      console.error('[social] schedule failed', e);
      alert('排程失敗，請看 console');
    } finally {
      setScheduling(false);
    }
  }, [selectedId, post, comments, scheduleTime, fetchScheduled]);

  const fetchList = useCallback(async () => {
    setLoadingList(true);
    try {
      setEpisodes(await listSocialEpisodes(40));
      fetchScheduled();
    } catch (e) {
      console.error('[social] list failed', e);
    } finally {
      setLoadingList(false);
    }
  }, [fetchScheduled]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const selectEpisode = useCallback(async (id: string) => {
    setSelectedId(id);
    setLoadingBundle(true);
    setSaved(false);
    setPublishResult(null);
    setPublishError(null);
    try {
      const b = await getSocialEpisode(id);
      setBundle(b);
      setPost(b.post);
      setComments(b.comments.length ? b.comments : b.theme_cards.map((c) => ({ heading: c.heading, text: '' })));
    } catch (e) {
      console.error('[social] bundle failed', e);
    } finally {
      setLoadingBundle(false);
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!selectedId) return;
    setSaving(true);
    setSaved(false);
    try {
      await saveSocialEpisode(selectedId, { post, comments });
      setSaved(true);
      setEpisodes((prev) => prev.map((e) =>
        e.episode_id === selectedId
          ? { ...e, has_copy: !!post.trim(), comment_count: comments.filter((c) => c.text.trim()).length }
          : e));
    } catch (e) {
      console.error('[social] save failed', e);
      alert('儲存失敗，請看 console');
    } finally {
      setSaving(false);
    }
  }, [selectedId, post, comments]);

  const handleGenerate = useCallback(async () => {
    if (!selectedId) return;
    if (bundle?.has_copy && !window.confirm('重新生成會覆蓋目前文案，確定嗎？')) return;
    setGenerating(true);
    setSaved(false);
    setPublishResult(null);
    setPublishError(null);
    try {
      const { post: newPost, comments: newComments } = await generateSocialEpisode(selectedId);
      // Re-read the bundle so the editor + 發佈預覽 reflect the freshly persisted copy.
      await selectEpisode(selectedId);
      setEpisodes((prev) => prev.map((e) =>
        e.episode_id === selectedId
          ? { ...e, has_copy: !!newPost.trim(), comment_count: newComments.filter((c) => c.text.trim()).length }
          : e));
    } catch (e) {
      console.error('[social] generate failed', e);
      alert('生成失敗，請看 console');
    } finally {
      setGenerating(false);
    }
  }, [selectedId, bundle, selectEpisode]);

  const handleRenderCards = useCallback(async () => {
    if (!selectedId) return;
    setRendering(true);
    try {
      await renderSocialCards(selectedId);
      await selectEpisode(selectedId); // re-read so the PNG grid shows the fresh cards
      setEpisodes((prev) => prev.map((e) =>
        e.episode_id === selectedId ? { ...e, has_images: true } : e));
    } catch (e) {
      console.error('[social] render cards failed', e);
      alert('產生卡片圖失敗，請看 console');
    } finally {
      setRendering(false);
    }
  }, [selectedId, selectEpisode]);

  const handlePublish = useCallback(async () => {
    if (!selectedId) return;
    if (!window.confirm('確定發佈到 Threads + Facebook？\n（會先儲存目前文案，再實際貼文）')) return;
    setPublishing(true);
    setPublishResult(null);
    setPublishError(null);
    try {
      // Publish posts the SERVER-stored copy, so persist the editor first to avoid
      // posting stale text.
      await saveSocialEpisode(selectedId, { post, comments });
      setSaved(true);
      const result = await publishSocialEpisode(selectedId, { dryRun: false, platforms: 'threads,facebook' });
      setPublishResult(result);
      // Reflect freshly-posted status in the list + editor badges.
      await selectEpisode(selectedId);
      setEpisodes((prev) => prev.map((e) =>
        e.episode_id === selectedId
          ? { ...e, posted: { threads: !!result.platforms.threads?.posted || e.posted.threads,
                              facebook: !!result.platforms.facebook?.posted || e.posted.facebook } }
          : e));
    } catch (e) {
      console.error('[social] publish failed', e);
      setPublishError('發佈請求失敗（網路或伺服器錯誤），請看 console。');
    } finally {
      setPublishing(false);
    }
  }, [selectedId, post, comments, selectEpisode]);

  const updateComment = (i: number, text: string) => {
    setComments((prev) => prev.map((c, idx) => (idx === i ? { ...c, text } : c)));
    setSaved(false);
  };

  const removeComment = (i: number) => {
    setComments((prev) => prev.filter((_, idx) => idx !== i));
    setSaved(false);
  };

  const addComment = () => {
    setComments((prev) => [...prev, { heading: '', text: '' }]);
    setSaved(false);
  };

  return (
    <div className="p-4 lg:p-8">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Social</h1>
          <p className="text-base text-muted-foreground">
            {tab === 'episodes'
              ? '自動生成 Threads／Facebook 文案 — 可編輯、預覽卡片圖，按「發佈」即同步貼到兩個平台。'
              : '自己寫一則宣傳貼文，附圖片／影片，一鍵同步貼到 Threads + Facebook。'}
          </p>
        </div>
        {tab === 'episodes' && (
          <button
            onClick={fetchList}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-medium text-foreground hover:bg-muted"
          >
            <RefreshCw className={`h-4 w-4 ${loadingList ? 'animate-spin' : ''}`} /> Refresh
          </button>
        )}
      </div>

      {/* Tabs: episode social copy vs. free-form promo composer */}
      <div className="mb-6 flex gap-1 border-b border-border">
        {([['episodes', '節目文案'], ['promo', '宣傳貼文']] as const).map(([key, txt]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
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

      {tab === 'promo' && <PromoComposer onScheduled={fetchScheduled} />}

      {tab === 'episodes' && (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Left Column: Episode list & Scheduled Queue */}
        <div className="space-y-6">
          <div className={`${card} h-fit max-h-[50vh] overflow-y-auto`}>
            {episodes.map((ep) => (
              <button
                key={ep.episode_id}
                onClick={() => selectEpisode(ep.episode_id)}
                className={`flex w-full flex-col gap-1 border-b border-border p-3 text-left last:border-0 ${
                  selectedId === ep.episode_id ? 'bg-primary/10' : 'hover:bg-muted'
                }`}
              >
                <div className="line-clamp-1 text-base font-medium text-foreground">
                  {ep.episode_title || ep.episode_id}
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{ep.podcast_name}</span>
                  <span>·</span>
                  <span>{fmtDate(ep.released_at_ms)}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge ok={ep.has_copy} icon={<MessageSquare className="h-3 w-3" />}>
                    {ep.has_copy ? `${ep.comment_count}/${ep.theme_card_count} 文案` : '尚無文案'}
                  </Badge>
                  <Badge ok={ep.has_images} icon={<ImageIcon className="h-3 w-3" />}>
                    {ep.has_images ? '有圖' : '無圖'}
                  </Badge>
                  {(ep.posted?.threads || ep.posted?.facebook) && (
                    <PostedPill>
                      已發佈{ep.posted?.threads && ep.posted?.facebook ? '' : ep.posted?.threads ? '· TH' : '· FB'}
                    </PostedPill>
                  )}
                </div>
              </button>
            ))}
            {!episodes.length && !loadingList && (
              <div className="p-4 text-base text-muted-foreground">沒有節目</div>
            )}
          </div>

          {/* Scheduled posts list */}
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
                    {post.post_type === 'episode'
                      ? (episodes.find(e => e.episode_id === post.episode_id)?.episode_title || post.episode_id)
                      : post.text}
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

        {/* Editor */}
        <div className="min-w-0">
          {!bundle && (
            <div className={`${card} p-10 text-center text-base text-muted-foreground`}>
              {loadingBundle ? '載入中…' : '從左邊選一集來編輯'}
            </div>
          )}

          {bundle && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <h2 className="line-clamp-1 text-xl font-semibold text-foreground">
                    {bundle.episode_title || bundle.episode_id}
                  </h2>
                  {bundle.posted.threads && <PostedPill>Threads 已發佈</PostedPill>}
                  {bundle.posted.facebook && <PostedPill>FB 已發佈</PostedPill>}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    onClick={handleGenerate}
                    disabled={generating || saving || publishing || scheduling}
                    title="用 AI 從卡片＋摘要生成文案（會覆蓋目前內容）"
                    className="inline-flex items-center gap-2 rounded-lg border border-primary px-3 py-2 text-base font-semibold text-primary hover:bg-primary/10 disabled:opacity-60"
                  >
                    <Wand2 className={`h-4 w-4 ${generating ? 'animate-pulse' : ''}`} />
                    {generating ? '生成中…' : bundle.has_copy ? '重新生成' : '生成文案'}
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saving || generating || publishing || scheduling}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-semibold text-foreground hover:bg-muted disabled:opacity-60"
                  >
                    {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                    {saving ? '儲存中…' : saved ? '已儲存草稿' : '儲存草稿'}
                  </button>
                  <button
                    onClick={handlePublish}
                    disabled={publishing || generating || saving || scheduling}
                    title="儲存目前文案並發佈到 Threads + Facebook"
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-base font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                  >
                    <Send className={`h-4 w-4 ${publishing ? 'animate-pulse' : ''}`} />
                    {publishing ? '發佈中…' : '發佈'}
                  </button>

                  {/* Scheduling UI */}
                  <div className="flex items-center gap-2 border-l border-border pl-2">
                    <input
                      type="datetime-local"
                      value={scheduleTime}
                      onChange={(e) => setScheduleTime(e.target.value)}
                      className="rounded-lg border border-input bg-card px-2 py-1.5 text-base text-foreground focus:border-accent-info focus:outline-none"
                    />
                    <button
                      onClick={handleSchedule}
                      disabled={!scheduleTime || scheduling || saving || publishing}
                      title="設定日期時間後排程發佈"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-primary px-3 py-2 text-base font-semibold text-primary hover:bg-primary/10 disabled:opacity-60"
                    >
                      <Clock className="h-4 w-4" />
                      {scheduling ? '排程中…' : '排程'}
                    </button>
                  </div>
                </div>
              </div>

              {publishError && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-base text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <span>{publishError}</span>
                </div>
              )}

              {publishResult && (
                <div className="space-y-2 rounded-lg border border-border bg-card px-4 py-3">
                  <div className={label}>發佈結果</div>
                  {Object.entries(publishResult.platforms).map(([name, r]) => {
                    const ok = !!r.posted;
                    const postUrl = platformPostUrl(name, r);
                    return (
                      <div key={name} className="flex items-start gap-2 text-base">
                        {ok ? (
                          <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-sentiment-bull" />
                        ) : (
                          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
                        )}
                        <span className="font-semibold text-foreground">
                          {PLATFORM_LABELS[name] || name}
                        </span>
                        <span className={ok ? 'text-sentiment-bull' : 'text-destructive'}>
                          {platformStatusText(r)}
                        </span>
                        {postUrl && (
                          <a
                            href={postUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-accent-info hover:underline"
                          >
                            查看貼文 <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Card image preview */}
              <div className={`${card} p-4`}>
                <div className={`${label} mb-2 flex items-center gap-1.5`}>
                  <ImageIcon className="h-3.5 w-3.5" /> 卡片圖（Marp）
                </div>
                {bundle.marp_markdown
                  ? <SlideViewer content={bundle.marp_markdown} />
                  : <div className="text-base text-muted-foreground">這集還沒有 marp 投影片</div>}
              </div>

              {/* Actual PNGs that will be posted (rendered by the pipeline, stored in GCS).
                  Empty for older episodes processed before card rendering — they post text-only. */}
              <div className={`${card} p-4`}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className={`${label} flex items-center gap-1.5`}>
                    <ImageIcon className="h-3.5 w-3.5" /> 卡片圖 PNG（實際發佈）
                  </div>
                  <button
                    onClick={handleRenderCards}
                    disabled={rendering || generating || saving || publishing}
                    title="從卡片圖（Marp）渲染 PNG 並儲存（發佈時也會自動產生）"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-base font-medium text-foreground hover:bg-muted disabled:opacity-60"
                  >
                    <ImageIcon className={`h-4 w-4 ${rendering ? 'animate-pulse' : ''}`} />
                    {rendering ? '產生中…' : bundle.composed.image_urls.length ? '重新產生卡片圖' : '產生卡片圖'}
                  </button>
                </div>
                {bundle.composed.image_urls.length ? (
                  <>
                    <p className="mb-3 text-xs text-muted-foreground">
                      {bundle.composed.image_urls.length} 張 — 這就是發佈時會帶上的輪播圖。點圖可開啟原圖下載。
                    </p>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {bundle.composed.image_urls.map((url, i) => (
                        <a
                          key={i}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          download
                          className="group relative block overflow-hidden rounded-lg border border-border hover:border-accent-info"
                          title={`卡片 ${i + 1} — 點擊開啟原圖`}
                        >
                          <img src={url} alt={`card ${i + 1}`} loading="lazy" className="aspect-square w-full bg-muted object-cover" />
                          <span className="absolute bottom-1 right-1 rounded bg-background/80 px-1.5 py-0.5 text-xs text-foreground">
                            {i + 1}
                          </span>
                        </a>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="text-base text-muted-foreground">
                    還沒產生卡片圖 PNG。按上方「產生卡片圖」即可從卡片圖（Marp）渲染並儲存；發佈時也會自動產生。
                  </div>
                )}
              </div>

              {/* Post */}
              <div className={`${card} p-4`}>
                <div className={`${label} mb-2`}>主貼文 Post</div>
                <textarea
                  value={post}
                  onChange={(e) => { setPost(e.target.value); setSaved(false); }}
                  rows={4}
                  placeholder="整集的總結，口語一點，最後引導大家看留言…"
                  className="w-full resize-y rounded-lg border border-input bg-card p-3 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
                />
                <div className="mt-1 text-right text-xs text-muted-foreground">{post.length} 字</div>
              </div>

              {/* Comments */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className={label}>留言 Comments（每張主題卡片一則）</div>
                  <button
                    onClick={addComment}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-base font-medium text-foreground hover:bg-muted"
                  >
                    <Plus className="h-4 w-4" /> 新增留言
                  </button>
                </div>
                {comments.map((c, i) => (
                  <div key={i} className={`${card} p-4`}>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2 text-base font-medium text-foreground">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{i + 1}</span>
                        <span className="line-clamp-1">{c.heading || bundle.theme_cards[i]?.heading || `留言 ${i + 1}`}</span>
                      </div>
                      <button
                        onClick={() => removeComment(i)}
                        title="刪除留言"
                        className="shrink-0 text-muted-foreground hover:text-sentiment-bear"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    {bundle.theme_cards[i]?.bullets?.length ? (
                      <ul className="mb-2 space-y-0.5 text-xs text-muted-foreground">
                        {bundle.theme_cards[i].bullets.map((b, bi) => <li key={bi}>· {b}</li>)}
                      </ul>
                    ) : null}
                    <textarea
                      value={c.text}
                      onChange={(e) => updateComment(i, e.target.value)}
                      rows={3}
                      placeholder="這段的人話重點…"
                      className="w-full resize-y rounded-lg border border-input bg-card p-3 text-base text-foreground placeholder:text-muted-foreground focus:border-accent-info focus:outline-none focus:ring-1 focus:ring-accent-info"
                    />
                    <div className="mt-1 text-right text-xs text-muted-foreground">{c.text.length} 字</div>
                  </div>
                ))}
              </div>

              {/* Composed preview */}
              <div className={`${card} p-4`}>
                <button
                  onClick={() => setShowComposed((v) => !v)}
                  className={`${label} flex items-center gap-1.5`}
                >
                  <Eye className="h-3.5 w-3.5" /> 實際發佈內容預覽 {showComposed ? '▲' : '▼'}
                </button>
                {showComposed && (
                  <div className="mt-3 space-y-3">
                    <pre className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs text-foreground">{bundle.composed.main_text}</pre>
                    {bundle.composed.replies.map((r, i) => (
                      <pre key={i} className="whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs text-foreground">↳ {r.text}</pre>
                    ))}
                    <p className="text-xs text-muted-foreground">註：以上為目前存檔內容組出的貼文；編輯後請先儲存再看預覽。</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
};

function Badge({ ok, icon, children }: { ok: boolean; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium ${
      ok ? 'bg-sentiment-bull-soft text-sentiment-bull'
         : 'bg-muted text-muted-foreground'
    }`}>
      {icon}{children}
    </span>
  );
}

function PostedPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-2xs font-semibold text-primary">
      <Send className="h-3 w-3" />{children}
    </span>
  );
}
