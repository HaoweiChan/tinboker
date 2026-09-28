import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { Link } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { getPlans, startCheckout } from '@/services/api/billing';
import type { BillingPlans } from '@/validation/schemas';
import { formatMemberUntil } from '@/lib/date';
import { INSIGHT_PAYWALL_DAYS } from '@/lib/insightPaywall';

/** The plan pitch: what membership includes, price (from `/api/billing/plans`), buy
 * button, and consent line. Shared by MembershipPage (/membership) and the locked 走勢
 * section on /member so the sales copy and price fetching live in exactly one place.
 *
 * Both benefits listed here are gates that already exist in the app: 走勢 (PicksPage,
 * members only) and the newest 個股觀點 (INSIGHT_PAYWALL_DAYS in lib/insightPaywall) —
 * keep this list and those gates in step, or the page sells the wrong thing. */
export const PlanCard: React.FC = () => {
  const checkoutPending = useRef(false);
  const [starting, setStarting] = useState(false);
  const [checkoutError, setCheckoutError] = useState('');
  const [plans, setPlans] = useState<BillingPlans | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAuthReady = useAppStore((s) => s.isAuthReady);
  const user = useAppStore((s) => s.user);
  const { guard } = useRequireAuth();

  useEffect(() => {
    let alive = true;
    getPlans()
      .then((p) => { if (alive) setPlans(p); })
      .catch(() => { if (alive) setError('無法載入方案資訊，請稍後再試'); });
    return () => { alive = false; };
  }, []);

  const checkout = async () => {
    if (checkoutPending.current) return;
    checkoutPending.current = true;
    setStarting(true);
    setCheckoutError('');
    try {
      await startCheckout();
    } catch (error) {
      setCheckoutError(isAxiosError(error) && error.response?.status === 403
        ? plans?.gateway_env === 'sandbox' ? '測試付款僅開放管理員；請使用一般登入後再試。' : '目前無法付款，請重新登入後再試。'
        : isAxiosError(error) && error.response?.status === 409
          ? '已有訂閱或待確認的付款，請先查看訂閱狀態。'
          : '無法開始付款，請稍後再試。');
      checkoutPending.current = false;
      setStarting(false);
    }
  };

  const memberUntilLabel = user?.member_until ? formatMemberUntil(user.member_until) : null;

  return (
    <div className="bg-card border border-border rounded-md p-5 sm:p-6 space-y-5">
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <CheckCircle2 size={20} className="text-accent-info shrink-0 mt-0.5" />
          <div>
            <h2 className="text-base font-semibold text-foreground mb-1">
              {user?.is_member ? <Link to="/member" className="hover:underline">走勢</Link> : '走勢'}
            </h2>
            <p className="text-sm text-muted-foreground leading-[1.65]">
              每一位財經 Podcaster 點名的個股，從提及當日起算的 7／30／90 天實際走勢，可依節目篩選。
            </p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <CheckCircle2 size={20} className="text-accent-info shrink-0 mt-0.5" />
          <div>
            <h2 className="text-base font-semibold text-foreground mb-1">最新個股觀點</h2>
            <p className="text-sm text-muted-foreground leading-[1.65]">
              個股頁上最近 {INSIGHT_PAYWALL_DAYS} 天的 Podcast 觀點摘要。{INSIGHT_PAYWALL_DAYS} 天前的觀點對所有人免費。
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-5 space-y-4">
        {!plans && !error && <div className="h-20 rounded-md bg-muted animate-pulse" />}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {plans && (
          <>
            {plans.founding_open ? (
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-foreground font-mono tabular-nums">NT$ {plans.founding_price}</span>
                  <span className="text-sm text-muted-foreground">/ 月</span>
                </div>
                <p className="text-sm text-accent-info mt-1">
                  創始會員價，訂閱期間不調漲 · 剩餘 {plans.founding_remaining} 個名額
                </p>
              </div>
            ) : (
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold text-foreground font-mono tabular-nums">NT$ {plans.list_price}</span>
                <span className="text-sm text-muted-foreground">/ 月</span>
              </div>
            )}
            {plans.gateway_env === 'sandbox' && <p className="text-xs font-medium text-primary">測試付款 · 僅限管理員使用測試卡</p>}
            <p className="text-sm text-muted-foreground">每月自動扣款，可隨時取消，取消後可使用至當期結束。</p>
            <p className="text-sm text-muted-foreground">
              訂閱即表示您同意<Link to="/terms" className="text-accent-info hover:underline">服務條款</Link>、
              <Link to="/terms#refund" className="text-accent-info hover:underline">退款政策</Link>與
              <Link to="/terms#privacy" className="text-accent-info hover:underline">隱私權政策</Link>。
            </p>

            {user?.membership_preview && <p className="text-xs text-muted-foreground">會員預覽中；請先重新登入，再進行付款。</p>}
            {checkoutError && <p role="alert" className="text-sm text-destructive">{checkoutError} <Link to="/membership" className="underline">查看訂閱</Link></p>}
            <div className="pt-1">
              {!isAuthReady ? (
                <div className="h-11 w-40 rounded-sm bg-muted animate-pulse" />
              ) : !user ? (
                <button
                  onClick={() => guard(() => {})}
                  className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition"
                >
                  登入以加入會員
                </button>
              ) : user.is_member ? (
                <p className="text-sm text-foreground font-medium">會員有效至 {memberUntilLabel}</p>
              ) : plans.checkout_open ? (
                <button
                  onClick={() => { void checkout(); }}
                  disabled={starting || Boolean(user.membership_preview)}
                  className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition"
                >
                  {starting ? '正在前往付款…' : user.membership_preview ? '預覽模式無法付款' : '立即加入會員'}
                </button>
              ) : (
                <button
                  disabled
                  className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-muted text-muted-foreground text-sm font-bold cursor-not-allowed"
                >
                  即將開放
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default PlanCard;
