/**
 * Admin → Social: review and edit the human-tone Threads copy (a grand-summary
 * post + one comment per slide) and preview the marp card images that go with it.
 * Threads credentials are wired up separately; this page only gets the copy +
 * images ready and editable.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Save, Check, MessageSquare, Image as ImageIcon, Eye, Wand2, Send, AlertCircle, ExternalLink } from 'lucide-react';
import { SlideViewer } from '@/components/common/SlideViewer';
import { PromoComposer } from '@/components/admin/PromoComposer';
import {
  listSocialEpisodes,
  getSocialEpisode,
  saveSocialEpisode,
  generateSocialEpisode,
  publishSocialEpisode,
  type SocialEpisodeListItem,
  type SocialEpisodeBundle,
  type SocialComment,
  type PublishResult,
  type PublishPlatformResult,
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
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [showComposed, setShowComposed] = useState(false);
  const [tab, setTab] = useState<'episodes' | 'promo'>('episodes');

  const fetchList = useCallback(async () => {
    setLoadingList(true);
    try {
      setEpisodes(await listSocialEpisodes(40));
    } catch (e) {
      console.error('[social] list failed', e);
    } finally {
      setLoadingList(false);
    }
  }, []);

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

      {tab === 'promo' && <PromoComposer />}

      {tab === 'episodes' && (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Episode list */}
        <div className={`${card} h-fit max-h-[80vh] overflow-y-auto`}>
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
                    disabled={generating || saving || publishing}
                    title="用 AI 從卡片＋摘要生成文案（會覆蓋目前內容）"
                    className="inline-flex items-center gap-2 rounded-lg border border-primary px-3 py-2 text-base font-semibold text-primary hover:bg-primary/10 disabled:opacity-60"
                  >
                    <Wand2 className={`h-4 w-4 ${generating ? 'animate-pulse' : ''}`} />
                    {generating ? '生成中…' : bundle.has_copy ? '重新生成' : '生成文案'}
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saving || generating || publishing}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-base font-semibold text-foreground hover:bg-muted disabled:opacity-60"
                  >
                    {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                    {saving ? '儲存中…' : saved ? '已儲存草稿' : '儲存草稿'}
                  </button>
                  <button
                    onClick={handlePublish}
                    disabled={publishing || generating || saving}
                    title="儲存目前文案並發佈到 Threads + Facebook"
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-base font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                  >
                    <Send className={`h-4 w-4 ${publishing ? 'animate-pulse' : ''}`} />
                    {publishing ? '發佈中…' : '發佈'}
                  </button>
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
                <div className={label}>留言 Comments（每張主題卡片一則）</div>
                {comments.map((c, i) => (
                  <div key={i} className={`${card} p-4`}>
                    <div className="mb-2 flex items-center gap-2 text-base font-medium text-foreground">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{i + 1}</span>
                      {c.heading || bundle.theme_cards[i]?.heading || `留言 ${i + 1}`}
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
