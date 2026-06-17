import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'sonner';
import { HomeFeed } from '@/pages/HomeFeed';
import { About } from '@/pages/About';
import { ContactPage } from '@/pages/ContactPage';
import { StockDashboard } from '@/pages/StockDashboard';
import { EpisodeDetail } from '@/pages/EpisodeDetail';
import { NewsRedirect } from '@/pages/NewsRedirect';
import { PodcasterPage } from '@/pages/PodcasterPage';
import { TagPage } from '@/pages/TagPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { SettingsPage } from '@/pages/SettingsPage';
import { ReportPage } from '@/pages/ReportPage';
import { DisclaimerPage } from '@/pages/DisclaimerPage';
import { PodcasterIndex } from '@/pages/PodcasterIndex';
import { StockIndex } from '@/pages/StockIndex';
import { TopicsCloud } from '@/pages/TopicsCloud';
import { WatchlistPage } from '@/pages/WatchlistPage';
import { PicksPage } from '@/pages/PicksPage';
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
import { DevPortalPage } from '@/pages/DevPortalPage';
import { DevGrafanaPage } from '@/pages/DevGrafanaPage';
import { DevPodcasterListPage } from '@/pages/DevPodcasterListPage';
import { DevTranslationsPage } from '@/pages/DevTranslationsPage';
import { DevBypass } from '@/pages/DevBypass';
import { AppLayout } from '@/components/layout/AppLayout';
import { GlobalPlayer } from '@/components/player/GlobalPlayer';
import { PlayerConfirmationModal } from '@/components/player/PlayerConfirmationModal';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useAppStore } from '@/store/useAppStore';
import { EnvGate } from '@/components/auth/EnvGate';

// Dev-only redesign QA surface; not registered in production builds.
const DesignPreview = import.meta.env.DEV ? lazy(() => import('@/pages/DesignPreview')) : null;

// Developer portal — only registered when VITE_STAGE=DEV (dev.tinboker.com).
// STAGING and PRODUCTION builds never register /dev routes so they fall through to the catch-all.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

function GatedApp() {
  return (
    <EnvGate>
      <Outlet />
      <GlobalPlayer />
      <PlayerConfirmationModal />
    </EnvGate>
  );
}

function App() {
  // Validate stored auth token on app initialization
  useAuthInit();
  const theme = useAppStore((state) => state.theme);

  return (
    <BrowserRouter>
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
            <Route path="/" element={<HomeFeed />} />

            {/* Redesigned list / cloud pages */}
            <Route path="/podcaster" element={<PodcasterIndex />} />
            <Route path="/stock" element={<StockIndex />} />
            <Route path="/topics" element={<TopicsCloud />} />
            <Route path="/watchlist" element={<WatchlistPage />} />
            <Route path="/picks" element={<PicksPage />} />

            {/* Single-instance / content pages */}
            <Route path="/stock/:ticker" element={<StockDashboard />} />
            <Route path="/podcaster/:id" element={<PodcasterPage />} />
            <Route path="/topics/:tag" element={<TagPage />} />
            <Route path="/tag/:tag" element={<TagPage />} />
            <Route path="/episode/:id" element={<EpisodeDetail />} />
            <Route path="/news/:id" element={<NewsRedirect />} />
            <Route path="/articles" element={<ArticleList />} />
            <Route path="/article/:slug" element={<ArticleDetail />} />

            {/* /industry hidden for launch — rendered fabricated sector data
                (mocks/sectorData.ts). Falls through to the catch-all redirect.
                Page + components retained for future real-data wiring. */}
            <Route path="/about" element={<About />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/disclaimer" element={<DisclaimerPage />} />
            <Route path="/report" element={<ReportPage />} />

            {/* User */}
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          {/* Admin — keeps its own layout, outside the consumer shell */}
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
