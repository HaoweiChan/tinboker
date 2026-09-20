import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { useAppStore } from '@/store/useAppStore';
import { PlanCard } from '@/components/membership/PlanCard';

/** /membership — PR 3a ships this in its "checkout not open yet" state: price +
 * founding-seat info come from `/api/billing/plans`, but no endpoint here talks to
 * NewebPay yet, so the buy button only ever renders disabled ("即將開放"). PR 3b
 * wires `startCheckout` up once NewebPay approves the Periodic API. */
export const MembershipPage: React.FC = () => {
  const user = useAppStore((s) => s.user);

  return (
    <>
      <SEO title="會員方案" description="TinBoker 會員方案：走勢功能（個股 7／30／90 天實際走勢）搶先看，其餘功能維持免費開放。" />
      <PageContent className="max-w-2xl">
        <div className="text-center pt-4 mb-6">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">會員方案</h1>
          <p className="text-base text-muted-foreground mt-2 max-w-lg mx-auto leading-[1.65]">
            解鎖走勢功能，其他功能維持免費，不受影響。
          </p>
          {!user && (
            <p className="text-sm text-accent-info mt-2">
              登入後可在這裡管理訂閱節目、自選股票與收藏。
            </p>
          )}
        </div>

        <PlanCard />

        <p className="text-2xs text-muted-foreground/70 leading-[1.6] mt-5 text-center">
          本服務提供第三方公開言論與事後股價的統計整理，不構成任何投資建議。
          <Link to="/about#disclaimer" className="text-accent-info hover:underline ml-1">詳見免責聲明</Link>
        </p>
      </PageContent>
    </>
  );
};

export default MembershipPage;
