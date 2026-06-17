/**
 * Admin → Social: review and edit the human-tone Threads copy (a grand-summary
 * post + one comment per slide) and preview the marp card images that go with it.
 * Threads credentials are wired up separately; this page only gets the copy +
 * images ready and editable.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Save, Check, MessageSquare, Image as ImageIcon, Eye } from 'lucide-react';
import { SlideViewer } from '@/components/common/SlideViewer';
import {
  listSocialEpisodes,
  getSocialEpisode,
  saveSocialEpisode,
  type SocialEpisodeListItem,
  type SocialEpisodeBundle,
  type SocialComment,
} from '@/services/api/adminSocial';

function fmtDate(ms: number): string {
  if (!ms) return '';
  const d = new Date(ms);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

const card = 'rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800';
const label = 'text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400';

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
  const [showComposed, setShowComposed] = useState(false);

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

  const updateComment = (i: number, text: string) => {
    setComments((prev) => prev.map((c, idx) => (idx === i ? { ...c, text } : c)));
    setSaved(false);
  };

  return (
    <div className="p-4 lg:p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Social</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Threads 貼文與每則留言的文案 — 編輯、預覽卡片圖，存檔後等接上 Threads 金鑰即可發佈。
          </p>
        </div>
        <button
          onClick={fetchList}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
        >
          <RefreshCw className={`h-4 w-4 ${loadingList ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Episode list */}
        <div className={`${card} h-fit max-h-[80vh] overflow-y-auto`}>
          {episodes.map((ep) => (
            <button
              key={ep.episode_id}
              onClick={() => selectEpisode(ep.episode_id)}
              className={`flex w-full flex-col gap-1 border-b border-gray-100 p-3 text-left last:border-0 dark:border-gray-700/60 ${
                selectedId === ep.episode_id ? 'bg-amber-50 dark:bg-amber-500/10' : 'hover:bg-gray-50 dark:hover:bg-gray-700/40'
              }`}
            >
              <div className="line-clamp-1 text-sm font-medium text-gray-900 dark:text-white">
                {ep.episode_title || ep.episode_id}
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{ep.podcast_name}</span>
                <span>·</span>
                <span>{fmtDate(ep.released_at_ms)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Badge ok={ep.has_copy} icon={<MessageSquare className="h-3 w-3" />}>
                  {ep.has_copy ? `${ep.comment_count}/${ep.theme_card_count} 文案` : '尚無文案'}
                </Badge>
                <Badge ok={ep.has_images} icon={<ImageIcon className="h-3 w-3" />}>
                  {ep.has_images ? '有圖' : '無圖'}
                </Badge>
              </div>
            </button>
          ))}
          {!episodes.length && !loadingList && (
            <div className="p-4 text-sm text-gray-500">沒有節目</div>
          )}
        </div>

        {/* Editor */}
        <div className="min-w-0">
          {!bundle && (
            <div className={`${card} p-10 text-center text-sm text-gray-500`}>
              {loadingBundle ? '載入中…' : '從左邊選一集來編輯'}
            </div>
          )}

          {bundle && (
            <div className="space-y-6">
              <div className="flex items-center justify-between gap-3">
                <h2 className="line-clamp-1 text-lg font-semibold text-gray-900 dark:text-white">
                  {bundle.episode_title || bundle.episode_id}
                </h2>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-gray-900 hover:bg-amber-400 disabled:opacity-60"
                >
                  {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                  {saving ? '儲存中…' : saved ? '已儲存' : '儲存'}
                </button>
              </div>

              {/* Card image preview */}
              <div className={`${card} p-4`}>
                <div className={`${label} mb-2 flex items-center gap-1.5`}>
                  <ImageIcon className="h-3.5 w-3.5" /> 卡片圖（Marp）
                </div>
                {bundle.marp_markdown
                  ? <SlideViewer content={bundle.marp_markdown} />
                  : <div className="text-sm text-gray-500">這集還沒有 marp 投影片</div>}
              </div>

              {/* Post */}
              <div className={`${card} p-4`}>
                <div className={`${label} mb-2`}>主貼文 Post</div>
                <textarea
                  value={post}
                  onChange={(e) => { setPost(e.target.value); setSaved(false); }}
                  rows={4}
                  placeholder="整集的總結，口語一點，最後引導大家看留言…"
                  className="w-full resize-y rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900 focus:border-amber-500 focus:outline-none dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                />
                <div className="mt-1 text-right text-xs text-gray-400">{post.length} 字</div>
              </div>

              {/* Comments */}
              <div className="space-y-3">
                <div className={label}>留言 Comments（每張主題卡片一則）</div>
                {comments.map((c, i) => (
                  <div key={i} className={`${card} p-4`}>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-xs font-bold text-gray-900">{i + 1}</span>
                      {c.heading || bundle.theme_cards[i]?.heading || `留言 ${i + 1}`}
                    </div>
                    {bundle.theme_cards[i]?.bullets?.length ? (
                      <ul className="mb-2 space-y-0.5 text-xs text-gray-400">
                        {bundle.theme_cards[i].bullets.map((b, bi) => <li key={bi}>· {b}</li>)}
                      </ul>
                    ) : null}
                    <textarea
                      value={c.text}
                      onChange={(e) => updateComment(i, e.target.value)}
                      rows={3}
                      placeholder="這段的人話重點…"
                      className="w-full resize-y rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900 focus:border-amber-500 focus:outline-none dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                    />
                    <div className="mt-1 text-right text-xs text-gray-400">{c.text.length} 字</div>
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
                    <pre className="whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-300">{bundle.composed.main_text}</pre>
                    {bundle.composed.replies.map((r, i) => (
                      <pre key={i} className="whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-300">↳ {r.text}</pre>
                    ))}
                    <p className="text-xs text-gray-400">註：以上為目前存檔內容組出的貼文；編輯後請先儲存再看預覽。</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

function Badge({ ok, icon, children }: { ok: boolean; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
      ok ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
         : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
    }`}>
      {icon}{children}
    </span>
  );
}
