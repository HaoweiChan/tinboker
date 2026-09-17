import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { PodAvatar } from '@/components/redesign';
import { SwipeToRemove } from '@/components/common/SwipeToRemove';
import { fetchWithFallback } from '@/services/api/migration';
import { getPodcastByName, type Podcast } from '@/services/api/podcasts';

/**
 * 訂閱節目 list shared by the profile (desktop) and 收藏 (mobile) pages so the two never
 * drift. Shows the subscribed channels themselves — one row per show, in the order they
 * are stored, with no popularity or recency ranking applied. Caller guards the empty case.
 *
 * A show whose metadata can't be fetched still gets a row: the subscription is the user's,
 * and a failed lookup should not make it look unsubscribed.
 */
export const SubscribedPodcasters: React.FC<{
  names: string[];
  /** When set, each row swipes left to remove; gets the stored show name back. */
  onRemove?: (name: string, label: string) => void;
}> = ({ names, onRemove }) => {
  const [shows, setShows] = useState<Map<string, Podcast>>(new Map());

  // Fetch for every show seen while mounted. A swipe-removed row drops out of the render
  // below without a refetch, so 復原 brings it back with its episode count intact.
  const seen = useRef(new Set<string>());
  names.forEach((n) => seen.current.add(n));
  const namesKey = JSON.stringify([...seen.current].sort());

  useEffect(() => {
    const all: string[] = JSON.parse(namesKey);
    if (all.length === 0) return;
    let alive = true;
    Promise.all(
      all.map((name) =>
        fetchWithFallback<Podcast | null>(() => getPodcastByName(name), null, `getPodcastByName:${name}`)
          .catch(() => null)
          .then((p) => [name, p] as const),
      ),
    ).then((entries) => {
      if (!alive) return;
      setShows(new Map(entries.filter((e): e is [string, Podcast] => e[1] != null)));
    });
    return () => {
      alive = false;
    };
  }, [namesKey]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {names.map((name) => {
        const show = shows.get(name);
        const row = (
          <Link
            to={`/podcaster/${encodeURIComponent(name)}`}
            className="flex items-center gap-3 bg-card border border-border rounded-md p-4 transition-colors hover:border-foreground/25"
          >
            <PodAvatar src={show?.image_url} name={name} size={40} className="w-10 h-10 rounded-[9px] object-cover shrink-0" />
            <div className="min-w-0">
              <div className="text-lg font-semibold truncate">{name}</div>
              <div className="text-2xs text-muted-foreground font-mono tabular-nums">
                {show ? `${show.episode_count} 集` : '—'}
              </div>
            </div>
          </Link>
        );
        return onRemove ? (
          <SwipeToRemove key={name} className="rounded-md" onRemove={() => onRemove(name, `「${name}」`)}>
            {row}
          </SwipeToRemove>
        ) : (
          <div key={name}>{row}</div>
        );
      })}
    </div>
  );
};
