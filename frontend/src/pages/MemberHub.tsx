import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { useUser } from '@/store/useAppStore';
import { formatMemberUntil } from '@/lib/date';
import { PicksPage } from '@/pages/PicksPage';

// One home for every member-only feature. Today there is exactly one (走勢), so
// it renders directly under the status strip — no tab/segmented control for a
// single item. A second feature turns this into a `Segmented` switch:
// `features.length > 1 && <Segmented .../>` is enough, nothing more.
const FEATURES = [
  { key: 'picks', label: '走勢', render: () => <PicksPage embedded /> },
] as const;

/** /member — the member-only hub (route gating lives in App.tsx's MemberRoute;
 *  this component assumes the viewer is already a confirmed member). */
export const MemberHub: React.FC = () => {
  const user = useUser();
  const memberUntilLabel = user?.member_until ? formatMemberUntil(user.member_until) : null;

  return (
    <>
      <SEO title="會員專區" description="TinBoker 會員專屬功能：走勢、訂閱管理。" />
      <PageContent>
        <div className="flex items-center justify-between flex-wrap gap-2 mb-5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-accent-info">會員</span>
            {memberUntilLabel && <span className="text-sm text-muted-foreground">有效至 {memberUntilLabel}</span>}
          </div>
          <Link to="/membership" className="text-xs text-accent-info hover:underline">管理訂閱</Link>
        </div>

        {/* Single feature today — no switcher. Add one back with
            `FEATURES.length > 1 && <Segmented ... />` once FEATURES grows. */}
        {FEATURES[0].render()}
      </PageContent>
    </>
  );
};

export default MemberHub;
