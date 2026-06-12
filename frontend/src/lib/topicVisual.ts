import {
  Hash, Cpu, Sparkles, Car, Landmark, Bitcoin, Zap, Globe, Truck,
  Building2, Banknote, ShieldCheck, FlaskConical, Newspaper, TrendingUp, Server,
  type LucideIcon,
} from 'lucide-react';

/**
 * Deterministic visual identity for a topic/tag — a category icon + a stable
 * gradient derived from the slug. Replaces the flat gray "#" placeholder so each
 * topic reads as a distinct, recognisable tile without falling back to a single
 * letter or zh character (which looked poor for multi-word zh-TW labels).
 */

// Keyword → icon. First match on the normalised slug wins; order matters
// (specific before generic). Falls back to Hash.
const ICON_RULES: Array<[RegExp, LucideIcon]> = [
  [/semiconductor|chip|packaging|powersupply|power/, Cpu],
  [/gpu|datacenter|server|cloud/, Server],
  [/agentic|llm|software|^ai$|aichip|\bai\b/, Sparkles],
  [/ev|electricvehicle|electricvehicles/, Car],
  [/fed|federalreserve|centralbank|monetary|interestrate|fiscalpolicy|reserve/, Landmark],
  [/crypto|bitcoin|digitalasset/, Bitcoin],
  [/energy/, Zap],
  [/geopolitic|tradewar|japanmarket/, Globe],
  [/supplychain/, Truck],
  [/realestate|housing|property|privatemarkets/, Building2],
  [/finance|financial|valuation|fixedincome|treasur|capital|earnings|ipo|mergers/, Banknote],
  [/cyber|security/, ShieldCheck],
  [/biotech|health|medical|demographics/, FlaskConical],
  [/media|streaming/, Newspaper],
  [/inflation|macro|economy|labormarket|narrative|correction|stock|market/, TrendingUp],
];

function normalise(slug: string): string {
  return slug.trim().replace(/^#/, '').replace(/[_\s-]/g, '').toLowerCase();
}

function hashHue(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

export interface TopicVisual {
  Icon: LucideIcon;
  /** Inline CSS gradient for the tile background. */
  gradient: string;
}

export function topicVisual(slug: string): TopicVisual {
  const key = normalise(slug);
  const Icon = ICON_RULES.find(([re]) => re.test(key))?.[1] ?? Hash;
  const hue = hashHue(key || 'topic');
  const gradient = `linear-gradient(135deg, hsl(${hue} 68% 52%), hsl(${(hue + 38) % 360} 64% 42%))`;
  return { Icon, gradient };
}
