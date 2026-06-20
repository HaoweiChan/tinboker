/**
 * /admin/articles — Admin article management: list, create, edit, publish.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Eye,
  FileText,
  Hash,
  Image,
  Link2,
  Pencil,
  Plus,
  Save,
  Send,
  Trash2,
  Type,
  Undo2,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '@/store/useAppStore';
import { ArticleBody } from '@/components/article/ArticleBody';
import {
  adminListArticles,
  adminGetArticle,
  adminCreateArticle,
  adminUpdateArticle,
  adminPublishArticle,
  adminUnpublishArticle,
  adminDeleteArticle,
  type ArticleCreatePayload,
} from '@/services/articleService';
import type { Article, ArticleListItem, ArticleStatus } from '@/validation/schemas';

type View = 'list' | 'editor';

const STATUS_LABELS: Record<ArticleStatus, string> = {
  draft: '草稿',
  published: '已發布',
  pending_review: '待審核',
  archived: '已封存',
};

const STATUS_COLORS: Record<ArticleStatus, string> = {
  draft: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  pending_review: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

interface EditorState {
  id: number | null;
  status: ArticleStatus;
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
  status: 'draft',
  title: '',
  subtitle: '',
  slug: '',
  body_content: '',
  cover_image_url: '',
  key_points: '',
  tags: '',
  tickers: '',
};

const SNIPPETS = [
  {
    label: '小標',
    icon: Type,
    text: '\n\n## 小標題\n\n',
  },
  {
    label: '股票',
    icon: Link2,
    text: '[公司名稱](#ticker:SYMBOL)',
  },
  {
    label: '標籤',
    icon: Hash,
    text: '[主題名稱](#tag:topic-slug)',
  },
  {
    label: '圖片',
    icon: Image,
    text: '![圖片描述](https://example.com/image.webp "圖說")',
  },
];

function editorFromArticle(a: Article): EditorState {
  return {
    id: a.id,
    status: (a.status as ArticleStatus) || 'draft',
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

function parseList(s: string, separator = ','): string[] {
  return s.split(separator).map((v) => v.trim()).filter(Boolean);
}

function estimateReadMinutes(text: string): number {
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return Math.max(1, Math.ceil((cjk + words) / 400));
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status as ArticleStatus] || status;
}

function statusColor(status: string): string {
  return STATUS_COLORS[status as ArticleStatus] || STATUS_COLORS.draft;
}

export const AdminArticlesPage: React.FC = () => {
  const token = useAppStore((s) => s.token) || '';
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);
  const [view, setView] = useState<View>('list');
  const [articles, setArticles] = useState<ArticleListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<EditorState>(EMPTY_EDITOR);
  const [saving, setSaving] = useState(false);

  const publishedCount = useMemo(
    () => articles.filter((article) => article.status === 'published').length,
    [articles],
  );

  const draftCount = useMemo(
    () => articles.filter((article) => article.status === 'draft').length,
    [articles],
  );

  const writingStats = useMemo(() => {
    const cjk = (editor.body_content.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
    const words = editor.body_content.trim() ? editor.body_content.trim().split(/\s+/).length : 0;
    return {
      chars: editor.body_content.length,
      units: cjk + words,
      readMinutes: estimateReadMinutes(editor.body_content),
      keyPoints: parseList(editor.key_points, '\n').length,
      tags: parseList(editor.tags).length,
      tickers: parseList(editor.tickers).length,
    };
  }, [editor.body_content, editor.key_points, editor.tags, editor.tickers]);

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

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const setField = (field: keyof EditorState, value: string) => {
    setEditor((prev) => ({ ...prev, [field]: value }));
  };

  const handleNew = () => {
    setEditor(EMPTY_EDITOR);
    setView('editor');
  };

  const handleEdit = async (id: number) => {
    try {
      const article = await adminGetArticle(token, id);
      setEditor(editorFromArticle(article));
      setView('editor');
    } catch {
      toast.error('載入文章失敗');
    }
  };

  const buildPayload = (publish = false): ArticleCreatePayload => ({
    title: editor.title.trim(),
    subtitle: editor.subtitle.trim() || undefined,
    slug: editor.slug.trim() || undefined,
    body_content: editor.body_content,
    cover_image_url: editor.cover_image_url.trim() || undefined,
    key_points: parseList(editor.key_points, '\n'),
    tags: parseList(editor.tags),
    tickers: parseList(editor.tickers).map((ticker) => ticker.toUpperCase()),
    status: publish ? 'published' : 'draft',
  });

  const handleSave = async (publish = false) => {
    if (!editor.title.trim()) {
      toast.error('請輸入文章標題');
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(publish);
      const saved = editor.id
        ? await adminUpdateArticle(token, editor.id, payload)
        : await adminCreateArticle(token, payload);
      const finalArticle = publish ? await adminPublishArticle(token, saved.id) : saved;
      setEditor(editorFromArticle(finalArticle));
      toast.success(publish ? '文章已發布' : '草稿已儲存');
      await loadList();
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知錯誤';
      toast.error(`儲存失敗: ${message}`);
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

  const handleUnpublish = async (id: number) => {
    try {
      const article = await adminUnpublishArticle(token, id);
      toast.success('文章已退回草稿');
      if (view === 'editor' && editor.id === id) {
        setEditor(editorFromArticle(article));
      }
      await loadList();
    } catch {
      toast.error('退回草稿失敗');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('確定要刪除此文章？')) return;
    try {
      await adminDeleteArticle(token, id);
      toast.success('文章已刪除');
      await loadList();
    } catch {
      toast.error('刪除失敗');
    }
  };

  const insertIntoBody = (snippet: string) => {
    const textarea = bodyRef.current;
    const start = textarea?.selectionStart ?? editor.body_content.length;
    const end = textarea?.selectionEnd ?? editor.body_content.length;
    const next = `${editor.body_content.slice(0, start)}${snippet}${editor.body_content.slice(end)}`;
    setField('body_content', next);
    window.setTimeout(() => {
      textarea?.focus();
      textarea?.setSelectionRange(start + snippet.length, start + snippet.length);
    }, 0);
  };

  const copyPublicPath = async () => {
    if (!editor.slug) return;
    try {
      await navigator.clipboard.writeText(`/article/${editor.slug}`);
      toast.success('文章路徑已複製');
    } catch {
      toast.error('複製失敗');
    }
  };

  if (view === 'list') {
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
              TinBoker Editorial
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-normal text-gray-950 dark:text-white">
              文章工作台
            </h2>
          </div>
          <button
            onClick={handleNew}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            新增文章
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <p className="text-xs text-gray-500 dark:text-gray-400">全部文章</p>
            <p className="mt-2 text-2xl font-semibold text-gray-950 dark:text-white">{articles.length}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <p className="text-xs text-gray-500 dark:text-gray-400">已發布</p>
            <p className="mt-2 text-2xl font-semibold text-gray-950 dark:text-white">{publishedCount}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <p className="text-xs text-gray-500 dark:text-gray-400">草稿</p>
            <p className="mt-2 text-2xl font-semibold text-gray-950 dark:text-white">{draftCount}</p>
          </div>
        </div>

        {loading ? (
          <p className="rounded-lg border border-gray-200 bg-white py-12 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-800">
            載入中...
          </p>
        ) : articles.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-gray-300 bg-white py-16 text-gray-400 dark:border-gray-700 dark:bg-gray-800">
            <FileText className="h-10 w-10 opacity-40" />
            <p>尚無文章</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-left dark:border-gray-700 dark:bg-gray-900/50">
                  <th className="px-4 py-3 font-medium text-gray-600 dark:text-gray-300">標題</th>
                  <th className="hidden px-4 py-3 font-medium text-gray-600 dark:text-gray-300 md:table-cell">提及</th>
                  <th className="w-24 px-4 py-3 font-medium text-gray-600 dark:text-gray-300">狀態</th>
                  <th className="hidden w-28 px-4 py-3 font-medium text-gray-600 dark:text-gray-300 sm:table-cell">日期</th>
                  <th className="w-32 px-4 py-3 font-medium text-gray-600 dark:text-gray-300">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {articles.map((article) => (
                  <tr key={article.id} className="transition-colors hover:bg-gray-50 dark:hover:bg-gray-900/40">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-950 line-clamp-1 dark:text-white">{article.title}</div>
                      {article.subtitle && (
                        <div className="mt-0.5 text-xs text-gray-500 line-clamp-1 dark:text-gray-400">
                          {article.subtitle}
                        </div>
                      )}
                    </td>
                    <td className="hidden px-4 py-3 text-xs text-gray-500 dark:text-gray-400 md:table-cell">
                      {(article.tickers || []).slice(0, 3).join(', ') || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusColor(article.status)}`}>
                        {statusLabel(article.status)}
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 text-xs text-gray-500 dark:text-gray-400 sm:table-cell">
                      {formatDate(article.published_at || article.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => void handleEdit(article.id)}
                          className="rounded p-1.5 transition-colors hover:bg-gray-200 dark:hover:bg-gray-700"
                          title="編輯"
                        >
                          <Pencil className="h-4 w-4 text-gray-500" />
                        </button>
                        {article.status === 'draft' && (
                          <button
                            onClick={() => void handlePublish(article.id)}
                            className="rounded p-1.5 transition-colors hover:bg-emerald-100 dark:hover:bg-emerald-900/30"
                            title="發布"
                          >
                            <Send className="h-4 w-4 text-emerald-600" />
                          </button>
                        )}
                        {article.status === 'published' && (
                          <button
                            onClick={() => void handleUnpublish(article.id)}
                            className="rounded p-1.5 transition-colors hover:bg-amber-100 dark:hover:bg-amber-900/30"
                            title="退回草稿"
                          >
                            <Undo2 className="h-4 w-4 text-amber-600" />
                          </button>
                        )}
                        <button
                          onClick={() => void handleDelete(article.id)}
                          className="rounded p-1.5 transition-colors hover:bg-red-100 dark:hover:bg-red-900/30"
                          title="刪除"
                        >
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

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-5">
      <div className="sticky top-0 z-20 -mx-4 border-b border-gray-200 bg-gray-100/95 px-4 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95 lg:-mx-6 lg:px-6">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setView('list')}
              className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-white hover:text-gray-800 dark:hover:bg-gray-800 dark:hover:text-gray-100"
              title="返回列表"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusColor(editor.status)}`}>
                  {statusLabel(editor.status)}
                </span>
                {editor.id && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">ID {editor.id}</span>
                )}
              </div>
              <p className="mt-0.5 truncate text-sm font-medium text-gray-950 dark:text-white">
                {editor.title || '未命名文章'}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {editor.slug && (
              <button
                onClick={() => void copyPublicPath()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                <Copy className="h-4 w-4" />
                複製路徑
              </button>
            )}
            {editor.id && editor.status === 'published' && (
              <button
                onClick={() => void handleUnpublish(editor.id!)}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50"
              >
                <Undo2 className="h-4 w-4" />
                退回草稿
              </button>
            )}
            <button
              onClick={() => void handleSave(false)}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-800 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
            >
              <Save className="h-4 w-4" />
              儲存草稿
            </button>
            {editor.status !== 'published' && (
              <button
                onClick={() => void handleSave(true)}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
                發布
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5">
        <section className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <input
              type="text"
              value={editor.title}
              onChange={(e) => setField('title', e.target.value)}
              placeholder="文章標題"
              className="w-full border-0 bg-transparent text-3xl font-semibold tracking-normal text-gray-950 outline-none placeholder:text-gray-300 dark:text-white dark:placeholder:text-gray-600"
            />
            <input
              type="text"
              value={editor.subtitle}
              onChange={(e) => setField('subtitle', e.target.value)}
              placeholder="副標題"
              className="mt-3 w-full border-0 bg-transparent text-base text-gray-600 outline-none placeholder:text-gray-300 dark:text-gray-300 dark:placeholder:text-gray-600"
            />
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Slug</label>
              <input
                type="text"
                value={editor.slug}
                onChange={(e) => setField('slug', e.target.value)}
                placeholder="自動產生"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">標籤</label>
              <input
                type="text"
                value={editor.tags}
                onChange={(e) => setField('tags', e.target.value)}
                placeholder="ai-chips, semiconductor"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">提及個股</label>
              <input
                type="text"
                value={editor.tickers}
                onChange={(e) => setField('tickers', e.target.value)}
                placeholder="NVDA, 2330"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">封面圖片 URL</label>
              <input
                type="text"
                value={editor.cover_image_url}
                onChange={(e) => setField('cover_image_url', e.target.value)}
                placeholder="https://..."
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">重點摘要（每行一個）</label>
            <textarea
              value={editor.key_points}
              onChange={(e) => setField('key_points', e.target.value)}
              placeholder="每行一個重點"
              rows={3}
              className="w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
              <div className="flex flex-wrap items-center gap-1.5">
                {SNIPPETS.map((snippet) => {
                  const Icon = snippet.icon;
                  return (
                    <button
                      key={snippet.label}
                      onClick={() => insertIntoBody(snippet.text)}
                      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {snippet.label}
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                <span>{writingStats.chars.toLocaleString('zh-TW')} 字元</span>
                <span>{writingStats.readMinutes} 分鐘</span>
                <span>{writingStats.tags} 標籤</span>
                <span>{writingStats.tickers} 個股</span>
              </div>
            </div>
            <textarea
              ref={bodyRef}
              value={editor.body_content}
              onChange={(e) => setField('body_content', e.target.value)}
              placeholder="開始撰寫..."
              rows={28}
              className="min-h-[500px] w-full resize-y border-0 bg-white px-4 py-4 font-mono text-[15px] leading-7 text-gray-900 outline-none placeholder:text-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-600"
            />
          </div>
        </section>

        <section className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-200">文章預覽</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {writingStats.units.toLocaleString('zh-TW')} 字
            </div>
          </div>
          <div className="mx-auto max-w-3xl px-6 py-8">
            {editor.cover_image_url && (
              <img
                src={editor.cover_image_url}
                alt=""
                className="mb-6 max-h-[320px] w-full rounded-lg object-cover"
              />
            )}
            <h1 className="text-[28px] font-bold leading-[1.3] tracking-normal text-gray-950 dark:text-white">
              {editor.title || '（無標題）'}
            </h1>
            {editor.subtitle && (
              <p className="mt-3 text-[16px] leading-relaxed text-gray-500 dark:text-gray-400">
                {editor.subtitle}
              </p>
            )}
            <hr className="my-6 border-gray-200 dark:border-gray-700" />
            {editor.body_content.trim() ? (
              <ArticleBody content={editor.body_content} />
            ) : (
              <p className="py-12 text-center text-sm text-gray-400">尚無內容</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
