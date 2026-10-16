import { useEffect, useMemo, useState } from 'react';
import { getEpisodeCrossShow } from '@/services/api/mentions';
import type { Episode } from '@/services/api/podcasts';
import type { CrossShowResponse } from '@/validation/schemas';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useAppStore } from '@/store/useAppStore';

/** Share member comparisons and prices between the mobile cards and desktop rail. */
export function useCrossShowPanelData(episode: Episode | null, data: CrossShowResponse | null) {
  const isMember = useAppStore((s) => !!s.user?.is_member);
  const [detail, setDetail] = useState<CrossShowResponse | null>(null);
  const [detailFailed, setDetailFailed] = useState(false);
  const episodeId = episode?.id;
  useEffect(() => {
    setDetail(null);
    setDetailFailed(false);
    if (!isMember || !episodeId) return;
    let alive = true;
    getEpisodeCrossShow(episodeId, true)
      .then((res) => { if (alive) setDetail(res); })
      .catch(() => { if (alive) setDetailFailed(true); });
    return () => { alive = false; };
  }, [episodeId, isMember]);

  // The hook's input uses only content_mentions, never summary-derived ticker links.
  const priceEpisodes = useMemo(() => episode && data?.episode_id === episode.id ? [{
    ...episode,
    related_tickers: (data?.subjects ?? []).flatMap((s) => s.mention_type === 'ticker' && s.ticker ? [s.ticker] : []),
  }] : [], [episode, data]);
  const priceSinceMap = useStockPriceSinceMap(priceEpisodes);
  return { isMember, detail, detailFailed, priceSinceMap };
}
