import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { useAppStore } from '@/store/useAppStore';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { getPlans, startCheckout } from '@/services/api/billing';
import type { BillingPlans } from '@/validation/schemas';

/** /membership — PR 3a ships this in its "checkout not open yet" state: price +
 * founding-seat info come from `/api/billing/plans`, but no endpoint here talks to
 * NewebPay yet, so the buy button only ever renders disabled ("即將開放"). PR 3b
 * wires `startCheckout` up once NewebPay approves the Periodic API. */
export const MembershipPage: React.FC = () => {
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

  const memberUntilLabel = user?.member_until
    ? new Date(user.member_until).toLocaleDateString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Taipei' })
    : null;

  return (
    <>
      <SEO title="會員方案" description="TinBoker 會員方案：走勢功能（個股 7／30／90 天實際走勢）搶先看，其餘功能維持免費開放。" />
      <PageContent className="max-w-2xl">
        <div className="text-center pt-4 mb-6">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">會員方案</h1>
          <p className="text-base text-muted-foreground mt-2 max-w-lg mx-auto leading-[1.65]">
            解鎖走勢功能，其他功能維持免費，不受影響。
          </p>
        </div>

        <div className="bg-card border border-border rounded-md p-5 sm:p-6 space-y-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 size={20} className="text-accent-info shrink-0 mt-0.5" />
            <div>
              <h2 className="text-base font-semibold text-foreground mb-1">走勢</h2>
              <p className="text-sm text-muted-foreground leading-[1.65]">
                每一位財經 Podcaster 點名的個股，從提及當日起算的 7／30／90 天實際走勢，可依節目篩選。
              </p>
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
                <p className="text-sm text-muted-foreground">每月自動扣款，可隨時取消，取消後可使用至當期結束。</p>
                <p className="text-sm text-muted-foreground">
                  訂閱即表示您同意<Link to="/terms" className="text-accent-info hover:underline">服務條款</Link>、
                  <Link to="/terms#refund" className="text-accent-info hover:underline">退款政策</Link>與
                  <Link to="/terms#privacy" className="text-accent-info hover:underline">隱私權政策</Link>。
                </p>

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
                      onClick={() => { startCheckout().catch(() => {}); }}
                      className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition"
                    >
                      立即加入會員
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

        <p className="text-2xs text-muted-foreground/70 leading-[1.6] mt-5 text-center">
          本服務提供第三方公開言論與事後股價的統計整理，不構成任何投資建議。
          <Link to="/about#disclaimer" className="text-accent-info hover:underline ml-1">詳見免責聲明</Link>
        </p>
      </PageContent>
    </>
  );
};

export default MembershipPage;
