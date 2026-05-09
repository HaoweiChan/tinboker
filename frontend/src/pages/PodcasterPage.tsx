import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Mic, Wifi, Check } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { Button } from '@/components/ui';
import EpisodeCard from '@/components/home/EpisodeCard';
import { useAppStore, useSubscriptions } from '@/store/useAppStore';
import type { Episode as MockEpisode } from '@/data/mockData';
import { getPodcastByName, getPodcastEpisodes, type Podcast } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { Breadcrumbs } from '@/components/common/Breadcrumbs';
import { SEO } from '@/components/common/SEO';
import { transformApiEpisodeToMock } from '@/services/api/transformers';
import { PodcasterPicksList } from '@/components/financial/PodcasterPicksList';



export const PodcasterPage: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toggleSubscription } = useAppStore();
  const subscriptions = useSubscriptions();
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [podcasterEpisodes, setPodcasterEpisodes] = useState<MockEpisode[]>([]);
  const [loading, setLoading] = useState(true);

  // Get podcaster name from URL
  const podcasterName = decodeURIComponent(id || '');
  // Check subscription status from store (with optimistic updates)
  const isSubscribed = subscriptions.includes(podcasterName);

  // Scroll to top when entering the page or changing podcaster
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [podcasterName]);

  // Fetch podcast data and episodes
  useEffect(() => {
    const fetchPodcastData = async () => {
      if (!podcasterName) return;

      setLoading(true);
      try {
        // Fetch podcast metadata
        const podcastData = await fetchWithFallback(
          () => getPodcastByName(podcasterName),
          null,
          `getPodcastByName(${podcasterName})`
        );
        setPodcast(podcastData);

        // Fetch episodes
        const apiEpisodes = await fetchWithFallback(
          () => getPodcastEpisodes(podcasterName, { limit: 20, sortBy: 'spotify_release_date', order: 'desc', includeContent: true }),
          [],
          `getPodcastEpisodes(${podcasterName})`
        );

        // Transform API episodes to mock format, filtering out those without summary
        const transformedEpisodes = apiEpisodes
          .map(transformApiEpisodeToMock)
          .filter((ep): ep is MockEpisode => ep !== null);

        // Sort by spotify_release_date (descending - newest first)
        // Since API might not sort correctly, we sort client-side as well
        transformedEpisodes.sort((a, b) => {
          // Find original API episodes to get release dates
          const apiA = apiEpisodes.find(ep => ep.id === a.id);
          const apiB = apiEpisodes.find(ep => ep.id === b.id);

          if (!apiA || !apiB) return 0;

          // Get release dates (prefer spotify_release_date, fallback to created_time)
          const dateA = apiA.spotify_release_date || apiA.created_time;
          const dateB = apiB.spotify_release_date || apiB.created_time;

          // Convert to timestamps for comparison
          const timeA = typeof dateA === 'string' ? new Date(dateA).getTime() : dateA;
          const timeB = typeof dateB === 'string' ? new Date(dateB).getTime() : dateB;

          // Descending order (newest first)
          return timeB - timeA;
        });

        setPodcasterEpisodes(transformedEpisodes);
      } catch (error) {
        console.error('[PodcasterPage] Failed to fetch podcast data:', error);
        setPodcast(null);
        setPodcasterEpisodes([]);
      } finally {
        setLoading(false);
      }
    };

    fetchPodcastData();
  }, [podcasterName]);

  // Helper to get avatar and color for podcast
  const getPodcastStyle = (name: string) => {
    if (name.includes('股癌')) {
      return { avatar: 'IMG', colorClass: 'bg-slate-200 text-slate-600' };
    } else if (name.includes('財報狗')) {
      return { avatar: '狗', colorClass: 'bg-indigo-100 text-indigo-600' };
    }
    const initials = name.substring(0, 2).toUpperCase();
    return { avatar: initials, colorClass: 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300' };
  };

  const style = getPodcastStyle(podcasterName);

  const handleTickerClick = (symbol: string) => {
    navigate(`/stock/${symbol}`);
  };

  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'ProfilePage',
    'mainEntity': {
      '@type': 'Organization',
      'name': podcasterName,
      'description': `這裡是 ${podcasterName} 的節目列表。透過深入淺出的方式，帶你了解最新的市場動態與投資趨勢。`
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950">
      <SEO
        title={`${podcasterName} - Podcast 頻道`}
        description={`追蹤 ${podcasterName} 的最新 Podcast 節目摘要與相關股票分析。`}
        structuredData={structuredData}
        url={window.location.href}
      />
      <Header />

      <main className="flex-1 overflow-y-auto pb-12">
        {/* Immersive Hero Section with Blurred Backdrop */}
        <div className="relative w-full overflow-hidden">
          {/* Blurred Background Gradient */}
          <div
            className="absolute inset-0 bg-gradient-to-b from-slate-200 to-slate-50 dark:from-slate-900 dark:to-slate-950"
            style={{
              backgroundImage: podcasterEpisodes[0]?.imageUrl ? `url(${podcasterEpisodes[0].imageUrl})` : 'none',
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(60px)',
              opacity: 0.3,
              transform: 'scale(1.1)',
            }}
          />

          {/* Hero Content */}
          <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <Breadcrumbs items={[{ label: podcasterName }]} className="mb-8" />

            <div className="flex flex-col md:flex-row items-center md:items-start gap-8">
              {/* Large Cover Image */}
              <div className="flex-shrink-0">
                {podcasterEpisodes[0]?.imageUrl ? (
                  <img
                    src={podcasterEpisodes[0].imageUrl}
                    alt={podcasterName}
                    className="w-40 h-40 md:w-48 md:h-48 rounded-xl shadow-2xl object-cover"
                  />
                ) : (
                  <div className={`w-40 h-40 md:w-48 md:h-48 rounded-xl flex items-center justify-center text-4xl font-bold shadow-2xl ${style.colorClass}`}>
                    {style.avatar}
                  </div>
                )}
              </div>

              {/* Info Column */}
              <div className="flex-1 space-y-4 text-center md:text-left backdrop-blur-md bg-white/60 dark:bg-black/20 p-6 rounded-xl border border-white/20 dark:border-white/10 shadow-sm mobile:w-full">
                <div className="flex flex-col md:flex-row items-center md:items-start justify-between gap-4">
                  <div>
                    <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-slate-50 mb-2">{podcasterName}</h1>
                    <div className="flex flex-wrap items-center justify-center md:justify-start gap-2 mb-3">
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-200 dark:bg-white/10 text-slate-700 dark:text-slate-50 text-xs font-medium">
                        <Mic size={14} /> 財經
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-200 dark:bg-white/10 text-slate-700 dark:text-slate-50 text-xs font-medium">
                        投資
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-200 dark:bg-white/10 text-slate-700 dark:text-slate-50 text-xs font-medium">
                        科技
                      </span>
                    </div>
                  </div>

                  {/* Prominent Subscribe Button */}
                  <Button
                    variant={isSubscribed ? "default" : "outline"}
                    onClick={() => toggleSubscription(podcasterName)}
                    className={`${isSubscribed
                      ? 'bg-amber-500 text-slate-900 hover:bg-amber-600 border-transparent shadow-lg'
                      : 'border-slate-300 dark:border-white/30 bg-white/50 dark:bg-white/10 text-slate-700 dark:text-slate-50 hover:bg-white/80 dark:hover:bg-white/20'} gap-2 px-6 py-3 h-auto font-bold transition-all rounded-lg`}
                  >
                    {isSubscribed ? <Check size={18} /> : <Wifi size={18} />}
                    {isSubscribed ? "已訂閱" : "訂閱"}
                  </Button>
                </div>

                <p className="text-slate-600 dark:text-slate-300 max-w-2xl leading-relaxed">
                  這裡是 {podcasterName} 的節目列表。透過深入淺出的方式，帶你了解最新的市場動態與投資趨勢。
                </p>

                {/* Stats Row with Icons */}
                <div className="flex items-center justify-center md:justify-start gap-8 pt-2">
                  <div className="flex items-center gap-2">
                    <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center">
                      <Mic size={18} className="text-slate-700 dark:text-slate-50" />
                    </div>
                    <div>
                      <div className="font-bold text-xl text-slate-900 dark:text-slate-50 font-financial">
                        {loading ? '...' : (podcast?.episode_count || podcasterEpisodes.length)}
                      </div>
                      <div className="text-xs text-slate-500 dark:text-slate-300">集數</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center">
                      <span className="text-slate-700 dark:text-slate-50 text-sm">⭐</span>
                    </div>
                    <div>
                      <div className="font-bold text-xl text-slate-900 dark:text-slate-50 font-financial">4.9</div>
                      <div className="text-xs text-slate-500 dark:text-slate-300">評分</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Episodes & Picks Section */}
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 mt-8">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left Column: Episodes (Span 2) */}
            <div className="lg:col-span-2">
              <section aria-label="Episodes List">
                <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50 mb-6">最新集數</h2>

                <div className="space-y-6">
                  {loading ? (
                    <div className="flex items-center justify-center py-12">
                      <p className="text-slate-500 dark:text-slate-400">載入中...</p>
                    </div>
                  ) : podcasterEpisodes.length > 0 ? (
                    podcasterEpisodes.map(episode => (
                      <EpisodeCard
                        key={episode.id}
                        episode={episode}
                        onTickerClick={handleTickerClick}
                      />
                    ))
                  ) : (
                    <div className="text-center py-12 bg-slate-100 dark:bg-slate-900 rounded-xl">
                      <p className="text-slate-500">此 Podcaster 目前沒有相關集數。</p>
                    </div>
                  )}
                </div>
              </section>
            </div>

            {/* Right Column: Recent Picks (Span 1) */}
            <div className="lg:col-span-1">
              <PodcasterPicksList
              podcasterName={podcasterName}
              episodes={podcasterEpisodes}
              podcastSlug={podcast?.id !== podcasterName ? podcast?.id : undefined}
            />
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default PodcasterPage;
