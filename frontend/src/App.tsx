import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { HomeFeed } from '@/pages/HomeFeed';
import { About } from '@/pages/About';
import { ContactPage } from '@/pages/ContactPage';
import { GraphGallery } from '@/pages/GraphGallery';
import { StockDashboard } from '@/pages/StockDashboard';
import { IndustryAnalysis } from '@/pages/IndustryAnalysis';
import { EpisodeDetail } from '@/pages/EpisodeDetail';
import { NewsRedirect } from '@/pages/NewsRedirect';
import { PodcasterPage } from '@/pages/PodcasterPage';
import { TagPage } from '@/pages/TagPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { SettingsPage } from '@/pages/SettingsPage';
import { DisclaimerPage } from '@/pages/DisclaimerPage';
import { PodcasterIndex } from '@/pages/PodcasterIndex';
import { StockIndex } from '@/pages/StockIndex';
import { TopicsCloud } from '@/pages/TopicsCloud';
import { WatchlistPage } from '@/pages/WatchlistPage';
import { AdminPage } from '@/pages/AdminPage';
import { AdminDashboardPage } from '@/pages/AdminDashboardPage';
import { TranslationsSection } from '@/pages/TranslationsSection';
import { SourcesSection } from '@/pages/SourcesSection';
import { AdminAnalyticsPage } from '@/pages/AdminAnalyticsPage';
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
      </Routes>
      <EnvGate>
      <Routes>
        {/* Redirects (no chrome needed) */}
        <Route path="/gallery" element={<Navigate to="/story" replace />} />
        <Route path="/graph/*" element={<Navigate to="/story" replace />} />

        {/* Consumer app — wrapped in the sidebar + header shell */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomeFeed />} />

          {/* Redesigned list / cloud pages */}
          <Route path="/podcaster" element={<PodcasterIndex />} />
          <Route path="/stock" element={<StockIndex />} />
          <Route path="/topics" element={<TopicsCloud />} />
          <Route path="/watchlist" element={<WatchlistPage />} />

          {/* Single-instance / content pages */}
          <Route path="/stock/:ticker" element={<StockDashboard />} />
          <Route path="/podcaster/:id" element={<PodcasterPage />} />
          <Route path="/topics/:tag" element={<TagPage />} />
          <Route path="/tag/:tag" element={<TagPage />} />
          <Route path="/episode/:id" element={<EpisodeDetail />} />
          <Route path="/news/:id" element={<NewsRedirect />} />

          {/* Retired from primary nav, kept live */}
          <Route path="/story" element={<GraphGallery />} />
          <Route path="/industry" element={<IndustryAnalysis />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/disclaimer" element={<DisclaimerPage />} />

          {/* User */}
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        {/* Admin — keeps its own layout, outside the consumer shell */}
        <Route path="/admin" element={<AdminPage />}>
          <Route index element={<AdminDashboardPage />} />
          <Route path="translations" element={<TranslationsSection />} />
          <Route path="sources" element={<SourcesSection />} />
          <Route path="analytics" element={<AdminAnalyticsPage />} />
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
      </Routes>
      <GlobalPlayer />
      <PlayerConfirmationModal />
      </EnvGate>
    </BrowserRouter>
  );
}

export default App;
