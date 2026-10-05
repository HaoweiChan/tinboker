import { apiClient } from './client';
import { z } from 'zod';
import {
  CommentListSchema, CommentSchema, ThreadsCommentSchema,
  type Comment, type CommentList, type ThreadsComment,
} from '../../validation/schemas';

export async function getEpisodeComments(
  podcastName: string,
  episodeId: string,
  offset = 0,
  limit = 20,
  token?: string,
): Promise<CommentList> {
  const res = await apiClient.get(
    `/api/episodes/${encodeURIComponent(podcastName)}/${encodeURIComponent(episodeId)}/comments`,
    {
      params: { offset, limit },
      // Send auth when available so the viewer sees their own private comments.
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    },
  );
  return CommentListSchema.parse(res.data);
}

export async function postComment(
  podcastName: string,
  episodeId: string,
  content: string,
  token: string,
  parentCommentId?: string,
  isPublic = true,
): Promise<Comment> {
  const res = await apiClient.post(
    `/api/episodes/${encodeURIComponent(podcastName)}/${encodeURIComponent(episodeId)}/comments`,
    { content, parent_comment_id: parentCommentId ?? null, is_public: isPublic },
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return CommentSchema.parse(res.data);
}

export async function deleteComment(commentId: string, token: string): Promise<void> {
  await apiClient.delete(`/api/comments/${encodeURIComponent(commentId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getEpisodeThreadsComments(podcastName: string, episodeId: string): Promise<ThreadsComment[]> {
  const res = await apiClient.get(
    `/api/episodes/${encodeURIComponent(podcastName)}/${encodeURIComponent(episodeId)}/threads-comments`,
  );
  return z.object({ comments: z.array(ThreadsCommentSchema) }).parse(res.data).comments;
}
