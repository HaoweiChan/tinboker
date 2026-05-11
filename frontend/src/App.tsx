import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Landing } from '@/pages/Landing';
import { About } from '@/pages/About';
import { ContactPage } from '@/pages/ContactPage';
import { GraphGallery } from '@/pages/GraphGallery';
import { StockDashboard } from '@/pages/StockDashboard';
import { IndustryAnalysis } from '@/pages/IndustryAnalysis';
import { NewsPage } from '@/pages/NewsPage';
import { PodcasterPage } from '@/pages/PodcasterPage';
import { TagPage } from '@/pages/TagPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { SettingsPage } from '@/pages/SettingsPage';
import { DisclaimerPage } from '@/pages/DisclaimerPage';
import { ComingSoon } from '@/pages/ComingSoon';
import { AdminPage } from '@/pages/AdminPage';
import { AdminDashboardPage } from '@/pages/AdminDashboardPage';
import { TranslationsSection } from '@/pages/TranslationsSection';
import { AdminAnalyticsPage } from '@/pages/AdminAnalyticsPage';
import { AppLayout } from '@/components/layout/AppLayout';
import { GlobalPlayer } from '@/components/player/GlobalPlayer';
import { PlayerConfirmationModal } from '@/components/player/PlayerConfirmationModal';
import { useAuthInit } from '@/hooks/useAuthInit';
import { useAppStore } from '@/store/useAppStore';

// Dev-only redesign QA surface; not registered in production builds.
const DesignPreview = import.meta.env.DEV ? lazy(() => import('@/pages/DesignPreview')) : null;

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
        {/* Redirects (no chrome needed) */}
        <Route path="/gallery" element={<Navigate to="/story" replace />} />
        <Route path="/graph/*" element={<Navigate to="/story" replace />} />

        {/* Consumer app — wrapped in the sidebar + header shell */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<Landing />} />

          {/* New redesign nav targets (Phase 4 fills these in) */}
          <Route path="/podcaster" element={<ComingSoon title="節目" note="所有節目的列表頁正在重新設計。" />} />
          <Route path="/stock" element={<ComingSoon title="個股" note="所有個股的列表頁正在重新設計。" />} />
          <Route path="/topics" element={<ComingSoon title="話題雲" note="話題雲正在重新設計。" />} />
          <Route path="/watchlist" element={<ComingSoon title="自選" note="自選清單正在重新設計。" />} />

          {/* Single-instance / content pages */}
          <Route path="/stock/:ticker" element={<StockDashboard />} />
          <Route path="/podcaster/:id" element={<PodcasterPage />} />
          <Route path="/tag/:tag" element={<TagPage />} />
          <Route path="/news/:id" element={<NewsPage />} />

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

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <GlobalPlayer />
      <PlayerConfirmationModal />
    </BrowserRouter>
  );
}

export default App;
