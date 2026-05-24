import { apiClient } from './client';
import { CommentListSchema, CommentSchema, type Comment, type CommentList } from '../../validation/schemas';

export async function getEpisodeComments(
  podcastName: string,
  episodeId: string,
  offset = 0,
  limit = 20,
): Promise<CommentList> {
  const res = await apiClient.get(
    `/api/episodes/${encodeURIComponent(podcastName)}/${encodeURIComponent(episodeId)}/comments`,
    { params: { offset, limit } },
  );
  return CommentListSchema.parse(res.data);
}

export async function postComment(
  podcastName: string,
  episodeId: string,
  content: string,
  token: string,
  parentCommentId?: string,
): Promise<Comment> {
  const res = await apiClient.post(
    `/api/episodes/${encodeURIComponent(podcastName)}/${encodeURIComponent(episodeId)}/comments`,
    { content, parent_comment_id: parentCommentId ?? null },
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return CommentSchema.parse(res.data);
}

export async function deleteComment(commentId: string, token: string): Promise<void> {
  await apiClient.delete(`/api/comments/${encodeURIComponent(commentId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}
