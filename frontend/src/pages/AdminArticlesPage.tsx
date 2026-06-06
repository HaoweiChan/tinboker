/**
 * /admin/articles — Admin article management: list, create, edit, publish.
 */

import { useCallback, useEffect, useState } from 'react';
import { Eye, FileText, Pencil, Plus, Send, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '@/store/useAppStore';
import { ArticleBody } from '@/components/article/ArticleBody';
import {
  adminListArticles,
  adminGetArticle,
  adminCreateArticle,
  adminUpdateArticle,
  adminPublishArticle,
  adminDeleteArticle,
} from '@/services/articleService';
import type { Article, ArticleListItem } from '@/validation/schemas';

type View = 'list' | 'editor';

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  published: '已發布',
  pending_review: '待審核',
  archived: '已封存',
};

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  published: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  pending_review: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

// ── Editor ───────────────────────────────────────────────────────────────────

interface EditorState {
  id: number | null;
  title: string;
  subtitle: string;
  slug: string;
  body_content: string;
  cover_image_url: string;
  key_points: string;
  tags: string;
  tickers: string;
}

const EMPTY_EDITOR: EditorState = {
  id: null,
  title: '',
  subtitle: '',
  slug: '',
  body_content: '',
  cover_image_url: '',
  key_points: '',
  tags: '',
  tickers: '',
};

function editorFromArticle(a: Article): EditorState {
  return {
    id: a.id,
    title: a.title,
    subtitle: a.subtitle || '',
    slug: a.slug,
    body_content: a.body_content,
    cover_image_url: a.cover_image_url || '',
    key_points: (a.key_points || []).join('\n'),
    tags: (a.tags || []).join(', '),
    tickers: (a.tickers || []).join(', '),
  };
}

function parseList(s: string, separator: string = ','): string[] {
  return s.split(separator).map((v) => v.trim()).filter(Boolean);
}

// ── Component ────────────────────────────────────────────────────────────────

export const AdminArticlesPage: React.FC = () => {
  const token = useAppStore((s) => s.token) || '';
  const [view, setView] = useState<View>('list');
  const [articles, setArticles] = useState<ArticleListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<EditorState>(EMPTY_EDITOR);
  const [saving, setSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const list = await adminListArticles(token);
      setArticles(list);
    } catch {
      toast.error('載入文章列表失敗');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadList(); }, [loadList]);

  const handleNew = () => {
    setEditor(EMPTY_EDITOR);
    setShowPreview(false);
    setView('editor');
  };

  const handleEdit = async (id: number) => {
    try {
      const article = await adminGetArticle(token, id);
      setEditor(editorFromArticle(article));
      setShowPreview(false);
      setView('editor');
    } catch {
      toast.error('載入文章失敗');
    }
  };

  const handleSave = async (publish = false) => {
    if (!editor.title.trim()) {
      toast.error('請輸入文章標題');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: editor.title,
        subtitle: editor.subtitle || undefined,
        slug: editor.slug || undefined,
        body_content: editor.body_content,
        cover_image_url: editor.cover_image_url || undefined,
        key_points: parseList(editor.key_points, '\n'),
        tags: parseList(editor.tags),
        tickers: parseList(editor.tickers),
        status: publish ? 'published' : 'draft',
      };

      if (editor.id) {
        const updated = await adminUpdateArticle(token, editor.id, payload);
        if (publish) {
          await adminPublishArticle(token, editor.id);
        }
        setEditor(editorFromArticle(updated));
        toast.success(publish ? '文章已發布' : '文章已儲存');
      } else {
        const created = await adminCreateArticle(token, payload as any);
        if (publish) {
          await adminPublishArticle(token, created.id);
        }
        setEditor(editorFromArticle(created));
        toast.success(publish ? '文章已建立並發布' : '草稿已建立');
      }
      await loadList();
    } catch (e: any) {
      toast.error(`儲存失敗: ${e.message || '未知錯誤'}`);
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async (id: number) => {
    try {
      await adminPublishArticle(token, id);
      toast.success('文章已發布');
      await loadList();
    } catch {
      toast.error('發布失敗');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('確定要刪除此文章？')) return;
    try {
      await adminDeleteArticle(token, id);
      toast.success('文章已刪除');
      await loadList();
    } catch {
      toast.error('刪除失敗');
    }
  };

  const setField = (field: keyof EditorState, value: string) => {
    setEditor((prev) => ({ ...prev, [field]: value }));
  };

  // ── List view ──────────────────────────────────────────────────────────────

  if (view === 'list') {
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">文章管理</h2>
          <button
            onClick={handleNew}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            新增文章
          </button>
        </div>

        {loading ? (
          <p className="text-gray-500 py-10 text-center">載入中...</p>
        ) : articles.length === 0 ? (
          <div className="flex flex-col items-center py-16 gap-3 text-gray-400">
            <FileText className="h-10 w-10 opacity-40" />
            <p>尚無文章，點擊「新增文章」開始撰寫</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-800 text-left">
                  <th className="px-4 py-3 font-medium text-gray-600 dark:text-gray-300">標題</th>
                  <th className="px-4 py-3 font-medium text-gray-600 dark:text-gray-300 w-24">狀態</th>
                  <th className="px-4 py-3 font-medium text-gray-600 dark:text-gray-300 w-32">更新時間</th>
                  <th className="px-4 py-3 font-medium text-gray-600 dark:text-gray-300 w-32">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {articles.map((a) => (
                  <tr key={a.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900 dark:text-white line-clamp-1">{a.title}</div>
                      {a.subtitle && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 mt-0.5">{a.subtitle}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[a.status] || STATUS_COLORS.draft}`}>
                        {STATUS_LABELS[a.status] || a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                      {a.created_at ? new Date(a.created_at).toLocaleDateString('zh-TW') : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <button onClick={() => handleEdit(a.id)} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700" title="編輯">
                          <Pencil className="h-4 w-4 text-gray-500" />
                        </button>
                        {a.status === 'draft' && (
                          <button onClick={() => handlePublish(a.id)} className="p-1.5 rounded hover:bg-green-100 dark:hover:bg-green-900/30" title="發布">
                            <Send className="h-4 w-4 text-green-600" />
                          </button>
                        )}
                        <button onClick={() => handleDelete(a.id)} className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30" title="刪除">
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // ── Editor view ────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5">
        <button
          onClick={() => setView('list')}
          className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        >
          &larr; 返回列表
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPreview((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <Eye className="h-4 w-4" />
            {showPreview ? '隱藏預覽' : '預覽'}
          </button>
          <button
            onClick={() => handleSave(false)}
            disabled={saving}
            className="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-1.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
          >
            儲存草稿
          </button>
          <button
            onClick={() => handleSave(true)}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            發布
          </button>
        </div>
      </div>

      <div className={`grid gap-5 ${showPreview ? 'lg:grid-cols-2' : ''}`}>
        {/* Form */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">標題 *</label>
            <input
              type="text"
              value={editor.title}
              onChange={(e) => setField('title', e.target.value)}
              placeholder="文章標題"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">副標題</label>
            <input
              type="text"
              value={editor.subtitle}
              onChange={(e) => setField('subtitle', e.target.value)}
              placeholder="選填"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Slug</label>
              <input
                type="text"
                value={editor.slug}
                onChange={(e) => setField('slug', e.target.value)}
                placeholder="自動產生"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">封面圖片 URL</label>
              <input
                type="text"
                value={editor.cover_image_url}
                onChange={(e) => setField('cover_image_url', e.target.value)}
                placeholder="https://..."
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              內容（Markdown） *
            </label>
            <textarea
              value={editor.body_content}
              onChange={(e) => setField('body_content', e.target.value)}
              placeholder="使用 Markdown 撰寫文章內容...&#10;&#10;支援語法：&#10;  [台積電](#ticker:2330) — 個股連結&#10;  [AI晶片](#tag:ai-chips) — 標籤連結&#10;  ![描述](https://...) — 圖片"
              rows={20}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm font-mono leading-relaxed focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-y"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                標籤（逗號分隔）
              </label>
              <input
                type="text"
                value={editor.tags}
                onChange={(e) => setField('tags', e.target.value)}
                placeholder="ai-chips, semiconductor"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                提及個股（逗號分隔）
              </label>
              <input
                type="text"
                value={editor.tickers}
                onChange={(e) => setField('tickers', e.target.value)}
                placeholder="NVDA, TSMC"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              重點摘要（每行一點）
            </label>
            <textarea
              value={editor.key_points}
              onChange={(e) => setField('key_points', e.target.value)}
              placeholder="每行一個重點..."
              rows={4}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-y"
            />
          </div>
        </div>

        {/* Live preview */}
        {showPreview && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-5 bg-white dark:bg-gray-900 overflow-y-auto max-h-[80vh]">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">預覽</h2>
            {editor.cover_image_url && (
              <img
                src={editor.cover_image_url}
                alt="cover"
                className="w-full rounded-lg object-cover max-h-[300px] mb-4"
              />
            )}
            <h1 className="text-[24px] font-bold tracking-[-0.02em] leading-[1.25] mb-2">
              {editor.title || '（無標題）'}
            </h1>
            {editor.subtitle && (
              <p className="text-[15px] text-gray-500 mb-4">{editor.subtitle}</p>
            )}
            <hr className="my-4 border-gray-200 dark:border-gray-700" />
            <ArticleBody content={editor.body_content} />
          </div>
        )}
      </div>
    </div>
  );
};
