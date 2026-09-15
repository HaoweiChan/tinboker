import { useEffect, useMemo, useState } from 'react';
import { Layers, Hash } from 'lucide-react';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TagBoardCard } from '@/components/topics/TagBoardCard';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';
import { getTrendingTags, getSectorBoard, type TrendingTag, type SectorBoardItem } from '@/services/api/podcasts';
import { SwipeToRemove } from '@/components/common/SwipeToRemove';

/**
 * 追蹤話題 list shared by the profile (desktop) and 收藏 (mobile) pages so the two
 * never drift. Subscriptions mix two kinds — free-form tags (stored by slug, live
 * on /topics) and sectors (stored by display name, live on /sector) — which render
 * with different cards and route to different pages, so we resolve both sources and
 * split them like the topics page. Caller guards the empty case.
 */
export const SubscribedTopics: React.FC<{
  tagSubs: string[];
  /** When set, each card swipes left to remove; gets the stored subscription string back. */
  onRemove?: (sub: string, label: string) => void;
}> = ({ tagSubs, onRemove }) => {
  const tagLabels = useTagLabels();
  const [trendingTags, setTrendingTags] = useState<TrendingTag[]>([]);
  const [sectorBoard, setSectorBoard] = useState<SectorBoardItem[]>([]);

  const hasSubs = tagSubs.length > 0;
  useEffect(() => {
    if (!hasSubs) {
      setTrendingTags([]);
      setSectorBoard([]);
      return;
    }
    let alive = true;
    getTrendingTags().then((res) => { if (alive) setTrendingTags(res.tags); }).catch(() => {});
    getSectorBoard().then((s) => { if (alive) setSectorBoard(s); }).catch(() => {});
    return () => {
      alive = false;
    };
  }, [hasSubs]);

  const { subscribedSectors, subscribedTags } = useMemo(() => {
    const sectorByName = new Map(sectorBoard.map((s) => [s.display_name, s]));
    const tagById = new Map(trendingTags.map((t) => [t.id, t]));
    const sectors: { sub: string; sector: SectorBoardItem }[] = [];
    const tags: { sub: string; tag: TrendingTag }[] = [];
    for (const sub of tagSubs) {
      const name = sub.replace(/^#/, '');
      const sector = sectorByName.get(name);
      if (sector) sectors.push({ sub, sector });
      else tags.push({ sub, tag: tagById.get(name) ?? { id: name, name, scoped_count: 0, weekly_counts: [], recent_episodes: [] } });
    }
    return { subscribedSectors: sectors, subscribedTags: tags };
  }, [tagSubs, trendingTags, sectorBoard]);

  return (
    <div className="space-y-8">
      {subscribedSectors.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Layers size={13} className="text-muted-foreground" />
            <h2 className="text-sm font-semibold">產業 / 題材</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {subscribedSectors.map(({ sub, sector }) => (
              <Removable key={sector.exposure_id} onRemove={onRemove && (() => onRemove(sub, sector.display_name))}>
                <SectorBoardCard sector={sector} />
              </Removable>
            ))}
          </div>
        </div>
      )}
      {subscribedTags.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Hash size={13} className="text-muted-foreground" />
            <h2 className="text-sm font-semibold">標籤</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {subscribedTags.map(({ sub, tag }) => (
              <Removable key={tag.id} onRemove={onRemove && (() => onRemove(sub, `#${tagLabelFor(tag.id, tagLabels)}`))}>
                <TagBoardCard tag={tag} label={tagLabelFor(tag.id, tagLabels)} />
              </Removable>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const Removable: React.FC<{ onRemove?: () => void; children: React.ReactNode }> = ({ onRemove, children }) =>
  onRemove ? <SwipeToRemove className="rounded-md" onRemove={onRemove}>{children}</SwipeToRemove> : <>{children}</>;
