import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation, useNavigationType } from 'react-router-dom';
import { Toaster } from 'sonner';
import { HomeFeed } from '@/pages/HomeFeed';
import { About } from '@/pages/About';
import { StockDashboard } from '@/pages/StockDashboard';
import { EpisodeDetail } from '@/pages/EpisodeDetail';
import { NewsRedirect } from '@/pages/NewsRedirect';
import { PodcasterPage } from '@/pages/PodcasterPage';
import { TagPage } from '@/pages/TagPage';
import { SectorPage } from '@/pages/SectorPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { PodcasterIndex } from '@/pages/PodcasterIndex';
import { StockIndex } from '@/pages/StockIndex';
import { TopicsCloud } from '@/pages/TopicsCloud';
import { WatchlistPage } from '@/pages/WatchlistPage';
import { AdminPage } from '@/pages/AdminPage';
import { AdminDashboardPage } from '@/pages/AdminDashboardPage';
import { TranslationsSection } from '@/pages/TranslationsSection';
import { SourcesSection } from '@/pages/SourcesSection';
import { PipelineSettingsPage } from '@/pages/PipelineSettingsPage';
import { AdminAnalyticsPage } from '@/pages/AdminAnalyticsPage';
import { AdminArticlesPage } from '@/pages/AdminArticlesPage';
import { AdminTagsPage } from '@/pages/AdminTagsPage';
import { AdminSocialPage } from '@/pages/AdminSocialPage';
import { ArticleDetail } from '@/pages/ArticleDetail';
import { ArticleList } from '@/pages/ArticleList';
import { WeeklyPage } from '@/pages/WeeklyPage';
import { WeeklyIndex } from '@/pages/WeeklyIndex';
import { DevPortalPage } from '@/pages/DevPortalPage';
import { DevGrafanaPage } from '@/pages/DevGrafanaPage';
import { DevPodcasterListPage } from '@/pages/DevPodcasterListPage';
import { DevTranslationsPage } from '@/pages/DevTranslationsPage';
import { DevBypass } from '@/pages/DevBypass';
import { AppLayout } from '@/components/layout/AppLayout';
import { RequireLogin } from '@/components/auth/RequireLogin';
import { GlobalPlayer } from '@/components/player/GlobalPlayer';
import { PlayerConfirmationModal } from '@/components/player/PlayerConfirmationModal';
import { useEffect } from 'react';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useAppStore } from '@/store/useAppStore';
import { EnvGate } from '@/components/auth/EnvGate';

// Dev-only redesign QA surface; not registered in production builds.
const DesignPreview = import.meta.env.DEV ? lazy(() => import('@/pages/DesignPreview')) : null;

// Developer portal — only registered when VITE_STAGE=DEV (dev.tinboker.com).
// STAGING and PRODUCTION builds never register /dev routes so they fall through to the catch-all.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

// PR 3a — public plan/pricing page. Own chunk: most visitors never open it either.
const MembershipPage = lazy(() => import('@/pages/MembershipPage'));

// Member hub (/member) — replaces the old /picks route. Own chunk: most
// anonymous visitors never open it.
const MemberHub = lazy(() => import('@/pages/MemberHub'));

// Legal/policy page — low-traffic, own chunk like MembershipPage.
const TermsPage = lazy(() => import('@/pages/TermsPage'));

// /member: the single "my stuff" home for every signed-in user (free or paying).
// Signed in -> the hub (which itself locks the 走勢 tab for non-members);
// logged out -> the plan page /membership, so the sales pitch lives in one place.
function MemberRoute() {
  const isAuthReady = useAppStore((s) => s.isAuthReady);
  const user = useAppStore((s) => s.user);
  // Same wait MemberGate itself does — otherwise a signed-in user gets bounced
  // to the plan page for the one tick before auth hydrates.
  if (!isAuthReady) return null;
  return (
    <Suspense fallback={null}>
      {user ? <MemberHub /> : <MembershipPage />}
    </Suspense>
  );
}

/** /profile -> /member, preserving ?tab= (a plain <Navigate> drops the search). */
function ProfileRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/member${search}`} replace />;
}

// Admin dashboard is developer-only. The PRODUCTION backend mounts no /api/admin/* routes
// (see backend main.py `if not settings.is_production`), so a prod admin page would only
// 404. Register the routes wherever the API exists — dev + staging, i.e. non-PRODUCTION.
const ADMIN_ENABLED = (import.meta.env.VITE_STAGE as string) !== 'PRODUCTION';

function GatedApp() {
  return (
    <EnvGate>
      <Outlet />
      <GlobalPlayer />
      <PlayerConfirmationModal />
    </EnvGate>
  );
}


/** A new page starts at the top. React Router keeps the window's scroll offset across
 * navigations, so clicking a stock from halfway down the feed used to open the stock
 * page halfway down. Back/forward (POP) is left alone — the browser restores where the
 * reader was — and so is an in-page #anchor. */
function ScrollToTop() {
  const { pathname, hash } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    if (navigationType === 'POP' || hash) return;
    window.scrollTo(0, 0);
  }, [pathname, hash, navigationType]);
  return null;
}

function App() {
  // Validate stored auth token on app initialization
  useAuthInit();
  const theme = useAppStore((state) => state.theme);
  const fontSize = useAppStore((state) => state.fontSize);
  useEffect(() => {
    document.documentElement.style.fontSize = { sm: '15px', base: '17px', lg: '19px' }[fontSize ?? 'base'];
  }, [fontSize]);

  return (
    <BrowserRouter>
      <ScrollToTop />
      <Toaster
        position="top-center"
        theme={theme}
        richColors
        closeButton
        duration={4000}
      />
      <Routes>
        {/* Dev bypass — outside EnvGate so it works unauthenticated */}
        <Route path="/auth/dev-bypass" element={<DevBypass />} />

        <Route element={<GatedApp />}>
          {/* Retired /story (knowledge-graph gallery) rendered fabricated demo
              content, so it and its aliases are pulled from the public build.
              Page + redirect targets fall through to the catch-all → home. */}
          <Route path="/gallery" element={<Navigate to="/" replace />} />
          <Route path="/graph/*" element={<Navigate to="/" replace />} />
          <Route path="/story" element={<Navigate to="/" replace />} />

          {/* Consumer app — wrapped in the sidebar + header shell */}
          <Route element={<AppLayout />}>
            {/* Public — browsable without login (home, podcaster, stock index,
                static pages) so visitors + crawlers have an entry point. */}
            <Route path="/" element={<HomeFeed />} />
            <Route path="/podcaster" element={<PodcasterIndex />} />
            <Route path="/podcaster/:id" element={<PodcasterPage />} />
            <Route path="/stock" element={<StockIndex />} />
            <Route path="/sector/:exposureId" element={<SectorPage />} />
            <Route path="/news/:id" element={<NewsRedirect />} />
            {/* Old paid-feature route — kept working for bookmarks/old links. */}
            <Route path="/picks" element={<Navigate to="/member" replace />} />
            {/* /profile merged into /member (the personal hub) — keep the old
                links working, preserving ?tab= for deep links. */}
            <Route path="/profile" element={<ProfileRedirect />} />
            {/* One home for membership: signed in -> the hub, everyone else -> the
                plan page below. Personalized, so never add it to the sitemap. */}
            <Route path="/member" element={<MemberRoute />} />
            {/* Public pricing and owner-scoped billing return/status. */}
            <Route
              path="/membership"
              element={
                <Suspense fallback={null}>
                  <MembershipPage />
                </Suspense>
              }
            />
            <Route path="/about" element={<About />} />
            {/* Former standalone support pages — now sections of /about. */}
            <Route path="/contact" element={<Navigate to="/about#contact" replace />} />
            <Route path="/disclaimer" element={<Navigate to="/about#disclaimer" replace />} />
            <Route path="/report" element={<Navigate to="/about#contact" replace />} />
            <Route
              path="/terms"
              element={
                <Suspense fallback={null}>
                  <TermsPage />
                </Suspense>
              }
            />
            {/* NewebPay merchant review + consumer-protection expectations: dedicated
                paths for the policy sections, folded into /terms like /about's own
                legacy redirects. */}
            <Route path="/privacy" element={<Navigate to="/terms#privacy" replace />} />
            <Route path="/refund" element={<Navigate to="/terms#refund" replace />} />

            {/* Public content — browsable without login so visitors + crawlers
                can read it (soft wall). Personalized actions (bookmark, watchlist,
                comment) prompt login on click via useRequireAuth(). */}
            <Route path="/stock/:ticker" element={<StockDashboard />} />
            <Route path="/topics" element={<TopicsCloud />} />
            <Route path="/weekly" element={<WeeklyIndex />} />
            <Route path="/weekly/:week" element={<WeeklyPage />} />
            <Route path="/topics/:tag" element={<TagPage />} />
            <Route path="/tag/:tag" element={<TagPage />} />
            <Route path="/episode/:id" element={<EpisodeDetail />} />
            <Route path="/articles" element={<ArticleList />} />
            <Route path="/article/:slug" element={<ArticleDetail />} />

            {/* Login-gated — personal surfaces with nothing to show logged out. */}
            <Route element={<RequireLogin />}>
              <Route path="/watchlist" element={<WatchlistPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>

          {/* Admin — keeps its own layout, outside the consumer shell. Non-PRODUCTION
              only; prod serves no /api/admin/* API, so the page would just 404. */}
          {ADMIN_ENABLED && (
            <Route path="/admin" element={<AdminPage />}>
              <Route index element={<AdminDashboardPage />} />
              <Route path="translations" element={<TranslationsSection />} />
              <Route path="sources" element={<SourcesSection />} />
              <Route path="pipeline" element={<PipelineSettingsPage />} />
              <Route path="tags" element={<AdminTagsPage />} />
              <Route path="social" element={<AdminSocialPage />} />
              <Route path="analytics" element={<AdminAnalyticsPage />} />
              <Route path="articles" element={<AdminArticlesPage />} />
            </Route>
          )}

          {/* Dev-only design preview (standalone, no shell) */}
          {DesignPreview && (
            <Route
              path="/__design"
              element={
                <Suspense fallback={null}>
                  <DesignPreview />
                </Suspense>
              }
            />
          )}

          {/* Developer portal — only on dev.tinboker.com (VITE_STAGE=DEV) */}
          {IS_DEV_ENV && (
            <Route path="/dev" element={<DevPortalPage />}>
              <Route index element={<DevGrafanaPage />} />
              <Route path="podcasters" element={<DevPodcasterListPage />} />
              <Route path="translations" element={<DevTranslationsPage />} />
            </Route>
          )}

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
