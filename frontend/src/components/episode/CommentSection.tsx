import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useUser, useAppStore } from '@/store/useAppStore';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { CommentForm } from './CommentForm';
import { CommentList, type CommentWithReplies } from './CommentList';
import { getEpisodeComments, postComment, deleteComment } from '@/services/api/comments';
import type { Comment } from '@/validation/schemas';

function buildTree(flat: Comment[]): CommentWithReplies[] {
  const map = new Map<string, CommentWithReplies>();
  const roots: CommentWithReplies[] = [];

  // Build map with empty replies arrays
  flat.forEach((c) => map.set(c.id, { ...c, replies: [] }));

  // Wire parent → child
  map.forEach((node) => {
    if (node.parent_comment_id && map.has(node.parent_comment_id)) {
      map.get(node.parent_comment_id)!.replies!.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
}

interface CommentSectionProps {
  podcastName: string;
  episodeId: string;
  /** Show a public/private toggle on the top-level form (used by the feedback board). */
  allowPrivate?: boolean;
}

export const CommentSection: React.FC<CommentSectionProps> = ({ podcastName, episodeId, allowPrivate = false }) => {
  const user = useUser();
  const token = useAppStore((s) => s.token);
  const { guard, ensure } = useRequireAuth();

  const [flatComments, setFlatComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [replyingTo, setReplyingTo] = useState<string | null>(null);

  const tree = buildTree(flatComments);
  const total = flatComments.length;

  const fetchComments = useCallback(async () => {
    try {
      const result = await getEpisodeComments(podcastName, episodeId, 0, 20, token ?? undefined);
      setFlatComments(result.comments);
    } catch {
      if (import.meta.env.DEV) console.warn('Failed to fetch comments');
    }
  }, [podcastName, episodeId, token]);

  useEffect(() => {
    setLoading(true);
    fetchComments().finally(() => setLoading(false));
  }, [fetchComments]);

  // ensure() opens the login prompt and throws when logged out, so the form
  // keeps the user's typed text instead of clearing it on a failed submit.
  const handleSubmit = async (content: string, isPublic: boolean) => {
    ensure();
    const t = useAppStore.getState().token;
    if (!t) return;
    const newComment = await postComment(podcastName, episodeId, content, t, undefined, isPublic);
    // Append to flat list — tree rebuilds automatically
    setFlatComments((prev) => [...prev, newComment]);
  };

  const handleSubmitReply = async (content: string, parentId: string) => {
    ensure();
    const t = useAppStore.getState().token;
    if (!t) return;
    const newComment = await postComment(podcastName, episodeId, content, t, parentId);
    setFlatComments((prev) => [...prev, newComment]);
    setReplyingTo(null);
  };

  // Delete is only surfaced on the user's own comments (logged-in), but guard
  // anyway as defense-in-depth.
  const handleDelete = (commentId: string) =>
    guard(async () => {
      const t = useAppStore.getState().token;
      if (!t) return;
      try {
        await deleteComment(commentId, t);
        setFlatComments((prev) => prev.filter((c) => c.id !== commentId));
      } catch {
        toast.error('刪除失敗，請稍後再試。');
      }
    });

  return (
    <section className="bg-card border border-border rounded-md p-5 sm:p-6">
      <h3 className="text-base font-semibold text-muted-foreground mb-4">
        留言 {total > 0 && <span>({total})</span>}
      </h3>

      {/* Top-level comment form — visible to everyone; submitting while logged
          out opens the login prompt and keeps the typed text. */}
      <div className="mb-5 pb-5 border-b border-border">
        <CommentForm onSubmit={handleSubmit} showVisibilityToggle={allowPrivate} />
      </div>

      {/* Comment tree */}
      {loading ? (
        <p className="text-base text-muted-foreground">載入留言中…</p>
      ) : (
        <CommentList
          comments={tree}
          currentUserId={user?.id}
          onDelete={handleDelete}
          onReply={(parentId) => setReplyingTo(replyingTo === parentId ? null : parentId)}
          onCancelReply={() => setReplyingTo(null)}
          onSubmitReply={handleSubmitReply}
          replyingTo={replyingTo}
        />
      )}
    </section>
  );
};
