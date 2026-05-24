import React from 'react';
import { Trash2, CornerDownRight } from 'lucide-react';
import { CommentForm } from './CommentForm';
import type { Comment } from '@/validation/schemas';

const MAX_DEPTH = 5;

export interface CommentWithReplies extends Comment {
  replies?: CommentWithReplies[];
}

function timeAgo(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return '剛才';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} 分鐘前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小時前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} 個月前`;
  return `${Math.floor(months / 12)} 年前`;
}

interface CommentItemProps {
  comment: CommentWithReplies;
  currentUserId: string | undefined;
  onDelete: (commentId: string) => void;
  onReply?: (parentId: string) => void;
  onCancelReply?: () => void;
  onSubmitReply?: (content: string, parentId: string) => Promise<void>;
  replyingTo?: string | null;
}

const CommentItem: React.FC<CommentItemProps> = ({
  comment,
  currentUserId,
  onDelete,
  onReply,
  onCancelReply,
  onSubmitReply,
  replyingTo,
}) => {
  const isReplying = replyingTo === comment.id;
  const depth = comment.depth ?? 0;
  // Visual indent capped at 4 levels to prevent excessive narrowing
  const indentClass = depth > 0 ? 'ml-6 pl-3 border-l border-border' : '';

  return (
    <div className={indentClass}>
      <div className="flex gap-3 py-3">
        {/* Avatar */}
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-muted flex items-center justify-center overflow-hidden">
          {comment.user_avatar ? (
            <img src={comment.user_avatar} alt={comment.user_name} className="w-full h-full object-cover" />
          ) : (
            <span className="text-[11px] font-semibold text-muted-foreground uppercase">
              {comment.user_name.charAt(0)}
            </span>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-0.5">
            <span className="text-[13px] font-semibold truncate">{comment.user_name}</span>
            <span className="text-[11px] text-muted-foreground flex-shrink-0">{timeAgo(comment.created_at)}</span>
          </div>
          <p className="text-[13px] text-foreground break-words whitespace-pre-wrap">{comment.content}</p>

          {/* Actions */}
          <div className="flex items-center gap-3 mt-1.5">
            {depth < MAX_DEPTH && (
              <button
                onClick={() => onReply?.(comment.id)}
                className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                <CornerDownRight className="h-3 w-3" />
                回覆
              </button>
            )}
            {currentUserId === comment.user_id && (
              <button
                onClick={() => onDelete(comment.id)}
                className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-destructive transition-colors"
                title="刪除留言"
              >
                <Trash2 className="h-3 w-3" />
                刪除
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Inline reply form */}
      {isReplying && (
        <div className="ml-10 mb-2">
          <CommentForm
            onSubmit={async (content) => { await onSubmitReply?.(content, comment.id); }}
            onCancel={() => onCancelReply?.()}
            placeholder={`回覆 ${comment.user_name}…`}
            autoFocus
          />
        </div>
      )}

      {/* Recursive replies */}
      {(comment.replies?.length ?? 0) > 0 && (
        <div>
          {comment.replies?.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              currentUserId={currentUserId}
              onDelete={onDelete}
              onReply={onReply}
              onCancelReply={onCancelReply}
              onSubmitReply={onSubmitReply}
              replyingTo={replyingTo}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface CommentListProps {
  comments: CommentWithReplies[];
  currentUserId: string | undefined;
  onDelete: (commentId: string) => void;
  onReply?: (parentId: string) => void;
  onCancelReply?: () => void;
  onSubmitReply?: (content: string, parentId: string) => Promise<void>;
  replyingTo?: string | null;
}

export const CommentList: React.FC<CommentListProps> = ({
  comments,
  currentUserId,
  onDelete,
  onReply,
  onCancelReply,
  onSubmitReply,
  replyingTo,
}) => {
  if (comments.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground py-2">
        還沒有留言，來當第一個吧！
      </p>
    );
  }

  return (
    <div className="divide-y divide-border">
      {comments.map((comment) => (
        <CommentItem
          key={comment.id}
          comment={comment}
          currentUserId={currentUserId}
          onDelete={onDelete}
          onReply={onReply}
          onCancelReply={onCancelReply}
          onSubmitReply={onSubmitReply}
          replyingTo={replyingTo}
        />
      ))}
    </div>
  );
};
