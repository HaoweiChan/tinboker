/**
 * Article API service — public reads + authenticated admin writes.
 */

import { apiClient } from './api/client';
import type { Article, ArticleListItem } from '@/validation/schemas';

// ── Public reads ──────────────────────────────────────────────────────────────

export async function getPublishedArticles(limit = 20, offset = 0): Promise<ArticleListItem[]> {
  const { data } = await apiClient.get<ArticleListItem[]>('/api/articles', { params: { limit, offset } });
  return data;
}

export async function getArticleBySlug(slug: string): Promise<Article> {
  const { data } = await apiClient.get<Article>(`/api/articles/${encodeURIComponent(slug)}`);
  return data;
}

/**
 * Related published articles for the "next best action" module (issue #425).
 * Scored client-side off the existing list endpoint (no dedicated backend route)
 * by counting shared tags/tickers, so it stays within the minimal-scope brief.
 */
export async function getRelatedArticles(article: Article, limit = 3): Promise<ArticleListItem[]> {
  const candidates = await getPublishedArticles(50, 0);
  const tags = new Set((article.tags || []).map((t) => t.toLowerCase()));
  const tickers = new Set((article.tickers || []).map((t) => t.toUpperCase()));

  return candidates
    .filter((a) => a.slug !== article.slug)
    .map((a) => {
      const sharedTags = (a.tags || []).filter((t) => tags.has(t.toLowerCase())).length;
      const sharedTickers = (a.tickers || []).filter((t) => tickers.has(t.toUpperCase())).length;
      return { article: a, score: sharedTags + sharedTickers * 2 };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((x) => x.article);
}

// ── Admin writes ──────────────────────────────────────────────────────────────

function authHeaders(token: string) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function adminListArticles(token: string, limit = 50, offset = 0): Promise<ArticleListItem[]> {
  const { data } = await apiClient.get<ArticleListItem[]>('/api/admin/articles', {
    params: { limit, offset },
    ...authHeaders(token),
  });
  return data;
}

export async function adminGetArticle(token: string, articleId: number): Promise<Article> {
  const { data } = await apiClient.get<Article>(`/api/admin/articles/${articleId}`, authHeaders(token));
  return data;
}

export interface ArticleCreatePayload {
  title: string;
  subtitle?: string;
  slug?: string;
  body_content: string;
  cover_image_url?: string;
  key_points?: string[];
  tags?: string[];
  tickers?: string[];
  premium_pitch?: string;
  premium_includes?: string[];
  subscribe_url?: string;
  status?: string;
}

export async function adminCreateArticle(token: string, payload: ArticleCreatePayload): Promise<Article> {
  const { data } = await apiClient.post<Article>('/api/admin/articles', payload, authHeaders(token));
  return data;
}

export async function adminUpdateArticle(token: string, articleId: number, payload: Partial<ArticleCreatePayload>): Promise<Article> {
  const { data } = await apiClient.patch<Article>(`/api/admin/articles/${articleId}`, payload, authHeaders(token));
  return data;
}

export async function adminPublishArticle(token: string, articleId: number): Promise<Article> {
  const { data } = await apiClient.post<Article>(`/api/admin/articles/${articleId}/publish`, {}, authHeaders(token));
  return data;
}

export async function adminUnpublishArticle(token: string, articleId: number): Promise<Article> {
  const { data } = await apiClient.post<Article>(`/api/admin/articles/${articleId}/unpublish`, {}, authHeaders(token));
  return data;
}

export async function adminDeleteArticle(token: string, articleId: number): Promise<void> {
  await apiClient.delete(`/api/admin/articles/${articleId}`, authHeaders(token));
}
