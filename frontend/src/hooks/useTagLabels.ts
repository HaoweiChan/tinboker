import { useEffect, useState } from 'react';
import { getTagRegistry } from '@/services/api/podcasts';

/**
 * Shared English→zh-TW tag label registry.
 *
 * The topics index (`/topics`) already translated tags via `/api/tags/registry`,
 * but the episode hero and the single-topic page (`/topics/:tag`) rendered the
 * raw English slug, so the same tag read differently across pages. This hook
 * exposes the registry as a `slug → display_zh` map, fetched ONCE at module
 * scope and shared by every subscriber (each episode card, the hero, the topic
 * pages) so the label is consistent everywhere with a single request.
 */
type Labels = Record<string, string>;

let cache: Labels | null = null;
let hiddenCache: Set<string> | null = null;
let inflight: Promise<Labels> | null = null;
const subscribers = new Set<(labels: Labels) => void>();
const hiddenSubscribers = new Set<(hidden: Set<string>) => void>();
const EMPTY_HIDDEN: Set<string> = new Set();

/**
 * Canonical lookup key for a tag slug — MUST match the backend + pipeline impls
 * (`normalize_tag_slug`). Lowercases and strips every non-alphanumeric char so
 * `SupplyChain` (vocabulary) / `supply_chain` (legacy DB slug) / `supplychain`
 * (lowercased episode tag) all reconcile to one key. This is why a PascalCase
 * episode tag and a snake_case registry slug can never read differently again.
 */
export function normalizeTagSlug(slug: string): string {
  const s = slug.replace(/^#/, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const aliases: Record<string, string> = {
    datacenters: 'datacenter',
    earningsreport: 'earnings',
    electricvehicles: 'ev',
    electric_vehicles: 'ev',
    lowearthorbitsatellite: 'leosatellite',
    mergersandacquisitions: 'mergersacquisitions',
  };
  return aliases[s] || s;
}

function load(): Promise<Labels> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = getTagRegistry()
      .then((res) => {
        const labels: Labels = {};
        for (const entry of res.tags) {
          if (entry.slug && entry.display_zh) labels[normalizeTagSlug(entry.slug)] = entry.display_zh;
        }
        cache = labels;
        hiddenCache = new Set((res.hidden_slugs ?? []).map(normalizeTagSlug));
        subscribers.forEach((fn) => fn(labels));
        hiddenSubscribers.forEach((fn) => fn(hiddenCache!));
        return labels;
      })
      .catch(() => {
        cache = {};
        hiddenCache = new Set();
        return cache;
      });
  }
  return inflight;
}

/** Translate a raw tag/slug to its zh-TW label, mirroring the topics-index logic. */
export function tagLabelFor(tag: string, labels: Labels): string {
  return labels[normalizeTagSlug(tag.trim())] ?? tag.replace(/^#/, '').replace(/[_-]/g, ' ');
}

/** Subscribe to the shared tag-label registry (slug → zh-TW display). */
export function useTagLabels(): Labels {
  const [labels, setLabels] = useState<Labels>(cache ?? {});
  useEffect(() => {
    if (cache) {
      setLabels(cache);
      return;
    }
    let alive = true;
    const fn = (l: Labels) => {
      if (alive) setLabels(l);
    };
    subscribers.add(fn);
    load();
    return () => {
      alive = false;
      subscribers.delete(fn);
    };
  }, []);
  return labels;
}

/** Subscribe to the set of admin-hidden off-vocab tag slugs (normalized). */
export function useHiddenTagSlugs(): Set<string> {
  const [hidden, setHidden] = useState<Set<string>>(hiddenCache ?? EMPTY_HIDDEN);
  useEffect(() => {
    if (hiddenCache) {
      setHidden(hiddenCache);
      return;
    }
    let alive = true;
    const fn = (h: Set<string>) => {
      if (alive) setHidden(h);
    };
    hiddenSubscribers.add(fn);
    load();
    return () => {
      alive = false;
      hiddenSubscribers.delete(fn);
    };
  }, []);
  return hidden;
}
