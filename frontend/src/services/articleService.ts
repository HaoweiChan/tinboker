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
