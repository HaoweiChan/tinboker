import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { getSubscription, cancelSubscription, type BillingSubscription } from '@/services/api/billing';
import { authApi } from '@/services/api/auth';
import { useAppStore } from '@/store/useAppStore';
import { sessionUser } from '@/lib/authSession';
import { formatMemberUntil } from '@/lib/date';

const labels: Record<BillingSubscription['status'], string> = {
  pending: '等待付款確認', active: '訂閱中', cancelling: '取消續訂確認中', cancelled: '已取消自動續訂', ended: '自動續訂已結束', failed: '付款未完成',
};

export function SubscriptionStatus({ paymentReturn }: { paymentReturn: boolean }) {
  const token = useAppStore((state) => state.token);
  const preview = useAppStore((state) => state.user?.membership_preview);
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const cancelPending = useRef(false);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let polls = 0;
    setLoading(true);
    setError('');
    const readStatus = async () => {
      try {
        const current = await getSubscription(controller.signal);
        if (controller.signal.aborted) return;
        setSubscription(current);
        setLoading(false);
        const pending = current?.status === 'pending' || current?.status === 'cancelling';
        setWaiting(pending && ++polls < 20);
        if (pending && polls < 20) timer = setTimeout(() => { void readStatus(); }, 3000);
        if (current && !pending) {
          // The return URL only triggers a lookup; /me alone supplies entitlement.
          const currentToken = useAppStore.getState().token;
          if (!currentToken) return;
          const user = await authApi.getCurrentUser(currentToken);
          const session = useAppStore.getState();
          if (!controller.signal.aborted && session.token && session.user?.id === user.id) {
            session.login(sessionUser(user), session.token);
          }
        }
      } catch {
        if (controller.signal.aborted) return;
        setLoading(false);
        setWaiting(false);
        setError('無法更新訂閱狀態，請稍後重試。');
      }
    };
    void readStatus();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [token, attempt]);

  const cancel = async () => {
    if (cancelPending.current) return;
    cancelPending.current = true;
    setCancelling(true);
    setError('');
    try {
      const current = await cancelSubscription();
      setSubscription(current);
      setConfirmCancel(false);
    } catch {
      setError('取消續訂尚未確認，請重新查詢訂閱狀態後再試。');
    } finally {
      cancelPending.current = false;
      setCancelling(false);
    }
  };

  if (!token) return null;
  return (
    <section aria-label="訂閱狀態" className="mb-5 rounded-md border border-border bg-card p-5 sm:p-6 space-y-3">
      <h2 className="text-base font-semibold">{paymentReturn ? '付款確認' : '目前訂閱'}</h2>
      {loading ? <p role="status" className="text-sm text-muted-foreground">正在查詢訂閱狀態…</p> : subscription ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{labels[subscription.status]}</span>
            {subscription.gateway_env === 'sandbox' && <span className="rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">測試付款</span>}
          </div>
          {subscription.status === 'pending' ? (
            <p role="status" className="text-sm text-muted-foreground">{waiting ? '正在等待付款確認，畫面會自動更新。' : '付款確認需要較長時間，請稍後重新查詢。'}請勿重複付款。</p>
          ) : subscription.status === 'cancelling' ? (
            <p role="status" className="text-sm text-muted-foreground">正在確認取消續訂結果，請勿重複操作。{!waiting && '請稍後重新查詢。'}</p>
          ) : subscription.status === 'failed' ? (
            <p className="text-sm text-muted-foreground">尚未完成付款，請重新查詢。若已扣款，請聯絡我們確認。</p>
          ) : (
            <div className="space-y-1 text-sm text-muted-foreground">
              <p>NT$ {subscription.amount.toLocaleString('zh-TW')} / 月{subscription.is_founding ? ' · 創始會員價' : ''}</p>
              {subscription.paid_until && <p>已付款會員期限：{formatMemberUntil(subscription.paid_until)}</p>}
              {subscription.status === 'active' && subscription.next_auth_date && <p>下次扣款日：{subscription.next_auth_date}</p>}
              {subscription.status === 'cancelled' && <p>不再自動扣款，已付款期間的會員權益不受影響。</p>}
            </div>
          )}
          {subscription.status === 'active' && <Link to="/member" className="inline-block text-sm text-accent-info hover:underline">前往會員專區</Link>}
          {subscription.status === 'active' && !confirmCancel && (
            <div><button type="button" disabled={Boolean(preview)} onClick={() => setConfirmCancel(true)} className="rounded border border-border px-3 py-2 text-xs hover:bg-muted disabled:opacity-50">取消自動續訂</button></div>
          )}
          {preview && <p className="text-xs text-muted-foreground">會員預覽中；請先重新登入，再管理付款。</p>}
          {confirmCancel && (
            <div role="group" aria-label="取消自動續訂確認" className="rounded-md border border-border bg-muted/30 p-3 space-y-3">
              <p className="text-sm">確定取消自動續訂？不再自動扣款，會員權益仍保留至{subscription.paid_until ? formatMemberUntil(subscription.paid_until) : '已付款期間結束'}。</p>
              <div className="flex gap-2">
                <button type="button" disabled={cancelling} onClick={() => { void cancel(); }} className="rounded bg-foreground px-3 py-2 text-xs font-medium text-background disabled:opacity-50">{cancelling ? '取消中…' : '確認取消續訂'}</button>
                <button type="button" disabled={cancelling} onClick={() => setConfirmCancel(false)} className="rounded border border-border px-3 py-2 text-xs">保留訂閱</button>
              </div>
            </div>
          )}
        </>
      ) : !error && <p className="text-sm text-muted-foreground">{paymentReturn ? '尚未收到付款確認，請稍後重新查詢。' : '目前沒有自動續訂方案。'}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {!loading && !waiting && <button type="button" disabled={cancelling} onClick={() => setAttempt((value) => value + 1)} className="text-xs text-accent-info hover:underline">重新查詢</button>}
    </section>
  );
}
