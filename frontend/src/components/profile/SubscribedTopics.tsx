import { useEffect, useRef, useState } from 'react';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TagBoardCard } from '@/components/topics/TagBoardCard';
import { loadTagLabels, normalizeTagSlug } from '@/hooks/useTagLabels';
import { getTrendingTags, getSectorBoard, type TrendingTag, type SectorBoardItem } from '@/services/api/podcasts';
import { SwipeToRemove } from '@/components/common/SwipeToRemove';

type Labels = Record<string, string>;

type Resolved =
  | { kind: 'sector'; sub: string; sector: SectorBoardItem }
  | { kind: 'tag'; sub: string; tag: TrendingTag; label: string }
  /** Neither a current sector nor a known tag — e.g. a sector renamed in the 2026-09 re-judge. */
  | { kind: 'retired'; sub: string; label: string };

/**
 * Map each stored subscription to what it points at today. Subscriptions are stored
 * as whatever string the subscribe button had: a sector display name, a tag slug, or
 * (from older tag pages) a tag's zh-TW label such as 「AI 晶片」, whose slug is
 * `aichip`. The label must be looked up before normalizing: normalizeTagSlug drops
 * every non-ASCII character, so 「AI 晶片」 would otherwise become `ai`.
 */
function resolveSubscriptions(
  tagSubs: string[],
  sectors: SectorBoardItem[],
  labels: Labels,
  tags: TrendingTag[],
): Resolved[] {
  const sectorByName = new Map(sectors.map((s) => [s.display_name, s]));
  const slugByLabel = new Map(Object.entries(labels).map(([slug, zh]) => [zh, slug]));
  const tagBySlug = new Map(tags.map((t) => [normalizeTagSlug(t.id), t]));
  return tagSubs.map((sub): Resolved => {
    const name = sub.replace(/^#/, '').trim();
    const sector = sectorByName.get(name);
    if (sector) return { kind: 'sector', sub, sector };
    const slug = slugByLabel.get(name) ?? normalizeTagSlug(name);
    const label = labels[slug] ?? name;
    const tag = slug ? tagBySlug.get(slug) : undefined;
    if (tag) return { kind: 'tag', sub, tag, label };
    // A registry tag with nothing in the release window: its 0 is real.
    if (slug && labels[slug]) {
      return { kind: 'tag', sub, label, tag: { id: slug, name: slug, scoped_count: 0, weekly_counts: [], recent_episodes: [] } };
    }
    return { kind: 'retired', sub, label: name };
  });
}

/** Slugs worth asking the trending endpoint about: every subscription that isn't a sector. */
function tagSlugsFor(tagSubs: string[], sectors: SectorBoardItem[], labels: Labels): string[] {
  const sectorNames = new Set(sectors.map((s) => s.display_name));
  const slugByLabel = new Map(Object.entries(labels).map(([slug, zh]) => [zh, slug]));
  const slugs = new Set<string>();
  for (const sub of tagSubs) {
    const name = sub.replace(/^#/, '').trim();
    if (sectorNames.has(name)) continue;
    const slug = slugByLabel.get(name) ?? normalizeTagSlug(name);
    if (slug) slugs.add(slug);
  }
  return [...slugs];
}

/**
 * 追蹤話題 list shared by the profile (desktop) and 收藏 (mobile) pages so the two
 * never drift. Subscriptions mix sectors (stored by display name, live on /sector)
 * and free-form tags (live on /topics), rendered with different cards. Nothing is
 * shown until the sector board, the tag registry and the tags' counts are all in:
 * rendering early painted every subscription as a tag with 「0 集」. Caller guards
 * the empty case.
 */
export const SubscribedTopics: React.FC<{
  tagSubs: string[];
  /** When set, each card swipes left to remove; gets the stored subscription string back. */
  onRemove?: (sub: string, label: string) => void;
}> = ({ tagSubs, onRemove }) => {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'failed' } | { status: 'ready'; sectors: SectorBoardItem[]; labels: Labels; tags: TrendingTag[] }
  >({ status: 'loading' });

  // Fetch for every subscription seen while mounted. A swipe-removed item drops out of
  // the render below without a refetch, so 復原 brings it back with its count intact.
  const seen = useRef(new Set<string>());
  tagSubs.forEach((sub) => seen.current.add(sub));
  const subsKey = JSON.stringify([...seen.current].sort());
  useEffect(() => {
    const subs: string[] = JSON.parse(subsKey);
    if (!subs.length) return;
    let alive = true;
    (async () => {
      try {
        const [sectors, labels] = await Promise.all([getSectorBoard(), loadTagLabels()]);
        const { tags } = await getTrendingTags(6, 3, tagSlugsFor(subs, sectors, labels));
        if (alive) setState({ status: 'ready', sectors, labels, tags });
      } catch {
        if (alive) setState({ status: 'failed' });
      }
    })();
    return () => {
      alive = false;
    };
  }, [subsKey]);

  if (state.status === 'loading') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {tagSubs.map((sub) => (
          <div key={sub} className="bg-card border border-border rounded-xl h-[88px] animate-pulse" />
        ))}
      </div>
    );
  }

  if (state.status === 'failed') {
    return (
      <div className="bg-card border border-border rounded-md p-6 text-center text-sm text-muted-foreground">
        話題資料暫時載入失敗，請稍後再試。
      </div>
    );
  }

  const resolved = resolveSubscriptions(tagSubs, state.sectors, state.labels, state.tags);
  const sectors = resolved.filter((r): r is Extract<Resolved, { kind: 'sector' }> => r.kind === 'sector');
  const others = resolved.filter((r): r is Exclude<Resolved, { kind: 'sector' }> => r.kind !== 'sector');

  return (
    <div className="space-y-8">
      {sectors.length > 0 && (
        <div>
          <h2 className="heading-accent text-lg font-semibold text-foreground mb-3">產業 / 題材</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sectors.map(({ sub, sector }) => (
              <Removable key={sub} onRemove={onRemove && (() => onRemove(sub, sector.display_name))}>
                <SectorBoardCard sector={sector} />
              </Removable>
            ))}
          </div>
        </div>
      )}
      {others.length > 0 && (
        <div>
          <h2 className="heading-accent text-lg font-semibold text-foreground mb-3">標籤</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {others.map((r) => (
              <Removable key={r.sub} onRemove={onRemove && (() => onRemove(r.sub, `#${r.label}`))}>
                {r.kind === 'tag' ? (
                  <TagBoardCard tag={r.tag} label={r.label} />
                ) : (
                  <RetiredTopicCard label={r.label} swipeable={!!onRemove} />
                )}
              </Removable>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

/** A subscription that no longer points at anything. Not a link: its page would be empty. */
const RetiredTopicCard: React.FC<{ label: string; swipeable: boolean }> = ({ label, swipeable }) => (
  <div className="bg-card border border-dashed border-border rounded-xl px-4 pt-3.5 pb-3 text-muted-foreground">
    <div className="flex items-center gap-1.5 mb-1.5">
      <span className="text-2xs font-medium bg-muted/60 px-1.5 py-0.5 rounded leading-none">已停用</span>
    </div>
    <span className="font-semibold block truncate">#{label}</span>
    <span className="text-xs mt-1 block">此分類已不再更新{swipeable ? '，左滑可移除' : ''}</span>
  </div>
);

const Removable: React.FC<{ onRemove?: () => void; children: React.ReactNode }> = ({ onRemove, children }) =>
  onRemove ? <SwipeToRemove className="rounded-md" onRemove={onRemove}>{children}</SwipeToRemove> : <>{children}</>;
