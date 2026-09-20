import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2 } from '@/components/redesign';
import { SwipeToRemove } from '@/components/common/SwipeToRemove';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { SubscribedPodcasters } from '@/components/profile/SubscribedPodcasters';
import { SubscribedTickers } from '@/components/profile/SubscribedTickers';
import { SubscribedTopics } from '@/components/profile/SubscribedTopics';
import { userApi } from '@/services/api/user';
import { useAppStore, useSubscriptions, useWatchlist, useTagSubscriptions } from '@/store/useAppStore';
import { useBookmarkedEpisodes } from '@/hooks/useBookmarkedEpisodes';
import { useRemoveWithUndo } from '@/hooks/useRemoveWithUndo';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { savedCount } from '@/lib/savedCount';

type Tab = 'podcasters' | 'tickers' | 'topics' | 'episodes';

export const WatchlistPage: React.FC = () => {
  const token = useAppStore((s) => s.token);
  const localSubscriptions = useSubscriptions();
  const localWatchlist = useWatchlist();
  const localTagSubscriptions = useTagSubscriptions();
  const [tab, setTab] = useState<Tab>('podcasters');
  const [bookmarkedIds, setBookmarkedIds] = useState<string[]>([]);
  // Server-side data for logged-in users
  const [apiSubscriptions, setApiSubscriptions] = useState<string[]>([]);
  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [apiTagSubs, setApiTagSubs] = useState<string[]>([]);
  const [serverLoaded, setServerLoaded] = useState(false);
  // Swiped-away items, hidden immediately and restored in place by 復原. The lists
  // themselves aren't edited, so an undo puts a row back where it was.
  const { removed, removeWithUndo } = useRemoveWithUndo();
  const toggleWatchlist = useAppStore((s) => s.toggleWatchlist);
  const toggleSubscription = useAppStore((s) => s.toggleSubscription);
  const toggleTagSubscription = useAppStore((s) => s.toggleTagSubscription);
  const toggleEpisodeBookmark = useAppStore((s) => s.toggleEpisodeBookmark);

  // Effective lists: prefer server data for logged-in users, fall back to local store
  const subscriptions = useMemo(
    () => (token && serverLoaded ? apiSubscriptions : localSubscriptions).filter((n) => !removed.has(`podcaster:${n}`)),
    [token, serverLoaded, apiSubscriptions, localSubscriptions, removed],
  );
  const watchlist = useMemo(
    () => (token && serverLoaded ? apiWatchlist : localWatchlist).filter((t) => !removed.has(`ticker:${t}`)),
    [token, serverLoaded, apiWatchlist, localWatchlist, removed],
  );
  const tagSubscriptions = useMemo(
    () => (token && serverLoaded ? apiTagSubs : localTagSubscriptions).filter((t) => !removed.has(`topic:${t}`)),
    [token, serverLoaded, apiTagSubs, localTagSubscriptions, removed],
  );

  // Fetch server-side user data on mount when logged in
  useEffect(() => {
    if (!token) {
      setServerLoaded(false);
      return;
    }
    Promise.all([
      userApi.getPodcastSubscriptions().catch(() => [] as string[]),
      userApi.getWatchlist().catch(() => [] as string[]),
      userApi.getTagSubscriptions().catch(() => [] as string[]),
      userApi.getEpisodeBookmarks().catch(() => [] as string[]),
    ]).then(([subs, wl, tags, bm]) => {
      setApiSubscriptions(subs);
      setApiWatchlist(wl);
      setApiTagSubs(tags);
      setBookmarkedIds(bm);
      setServerLoaded(true);
    });
  }, [token]);

  const { episodes: bookmarked, resolved: bookmarksResolved } = useBookmarkedEpisodes(bookmarkedIds, {
    repair: true,
    onChange: setBookmarkedIds,
  });
  const bookmarkedTickers = useMemo(() => bookmarked.flatMap((ep) => ep.related_tickers ?? []), [bookmarked]);
  const bookmarkedPriceMap = useStockPriceMap(bookmarkedTickers);
  const bookmarkedPriceSinceMap = useStockPriceSinceMap(bookmarked);

  // Fetch bookmarked episode IDs (for anonymous users only — logged-in fetched above)
  useEffect(() => {
    if (token) return;
    setBookmarkedIds([]);
  }, [token]);

  const sortedWatchlist = useMemo(() => [...watchlist], [watchlist]);
  const visibleBookmarked = useMemo(() => bookmarked.filter((ep) => !removed.has(`episode:${ep.id}`)), [bookmarked, removed]);
  const visibleBookmarkCount = savedCount(bookmarked.length, visibleBookmarked.length, bookmarkedIds.length);

  // Show loading state while server data is being fetched for logged-in users
  const isLoading = token && !serverLoaded;

  return (
    <>
      <SEO title="收藏" description="追蹤的節目與個股。" />
      <PageContent>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] mb-3.5">收藏</h1>
        <div className="flex items-center gap-2 overflow-x-auto mb-[18px]">
          {([
            ['podcasters', `節目 ${subscriptions.length}`],
            ['tickers', `股票 ${watchlist.length}`],
            ['topics', `話題 ${tagSubscriptions.length}`],
            ['episodes', `集數 ${visibleBookmarkCount}`],
          ] as const).map(([val, label]) => (
            <button
              key={val}
              type="button"
              onClick={() => setTab(val)}
              data-active={tab === val || undefined}
              className="filter-pill"
            >
              {label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {tab === 'podcasters' && (
              subscriptions.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
                  尚未訂閱任何節目 — 去 <Link to="/podcaster" className="text-accent-info hover:underline">節目</Link> 頁追蹤幾個吧。
                </div>
              ) : (
                <SubscribedPodcasters
                  names={subscriptions}
                  onRemove={(name, label) => removeWithUndo(`podcaster:${name}`, label, () => toggleSubscription(name, { silent: true }))}
                />
              )
            )}

            {tab === 'tickers' && (
              watchlist.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
                  尚未加入任何自選股票 — 去 <Link to="/stock" className="text-accent-info hover:underline">個股</Link> 頁加入幾檔吧。
                </div>
              ) : (
                <SubscribedTickers
                  tickers={sortedWatchlist}
                  onRemove={(sym, label) => removeWithUndo(`ticker:${sym}`, label, () => toggleWatchlist(sym, { silent: true }))}
                />
              )
            )}

            {tab === 'topics' && (
              tagSubscriptions.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
                  尚未追蹤任何話題 — 去 <Link to="/topics" className="text-accent-info hover:underline">話題</Link> 頁追蹤幾個吧。
                </div>
              ) : (
                <SubscribedTopics
                  tagSubs={tagSubscriptions}
                  onRemove={(sub, label) => removeWithUndo(`topic:${sub}`, label, () => toggleTagSubscription(sub, { silent: true }))}
                />
              )
            )}

            {tab === 'episodes' && (
              visibleBookmarkCount === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">目前沒有收藏的集數。</div>
              ) : bookmarked.length === 0 && !bookmarksResolved ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Array.from({ length: Math.min(bookmarkedIds.length, 4) }).map((_, i) => (
                    <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
                  ))}
                </div>
              ) : bookmarked.length === 0 ? (
                // Everything settled and nothing came back — say so rather than pulse forever.
                <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">收藏的集數目前無法載入，可能已下架。稍後再試一次吧。</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {visibleBookmarked.map((ep) => (
                    <SwipeToRemove
                      key={ep.id}
                      className="rounded-md"
                      onRemove={() => removeWithUndo(`episode:${ep.id}`, `「${ep.episode_title || '這集'}」`, () =>
                        toggleEpisodeBookmark(ep.podcast_name, ep.id, { silent: true }))}
                    >
                      <EpisodeCardV2 {...apiEpisodeToCardV2(ep, bookmarkedPriceMap, undefined, undefined, undefined, bookmarkedPriceSinceMap)} />
                    </SwipeToRemove>
                  ))}
                </div>
              )
            )}
          </>
        )}
      </PageContent>
    </>
  );
};
