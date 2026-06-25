import React from 'react';
import {
  Cpu,
  Landmark,
  Ship,
  MemoryStick,
  Server,
  Bot,
  CircuitBoard,
  Zap,
  Radio,
  Plug,
  Network,
  FileCode,
  Package,
  FlaskConical,
  Bike,
  Factory,
  Plane,
  Wrench,
  Droplets,
  Brain,
  Bitcoin,
  Car,
  Shield,
  Rocket,
  Flame,
  Code,
  CreditCard,
  Gem,
  ShoppingCart,
  Hash,
  type LucideIcon,
} from 'lucide-react';

// icon_id (from the compiled universe / API) → lucide component. Keep the names in
// sync with pipelines/.../generate_sector_visuals.py's VISUALS table.
const ICON_REGISTRY: Record<string, LucideIcon> = {
  cpu: Cpu,
  landmark: Landmark,
  ship: Ship,
  'memory-stick': MemoryStick,
  server: Server,
  bot: Bot,
  'circuit-board': CircuitBoard,
  zap: Zap,
  radio: Radio,
  plug: Plug,
  network: Network,
  'file-code': FileCode,
  package: Package,
  'flask-conical': FlaskConical,
  bike: Bike,
  factory: Factory,
  plane: Plane,
  wrench: Wrench,
  droplets: Droplets,
  brain: Brain,
  bitcoin: Bitcoin,
  car: Car,
  shield: Shield,
  rocket: Rocket,
  flame: Flame,
  code: Code,
  'credit-card': CreditCard,
  gem: Gem,
  'shopping-cart': ShoppingCart,
  hash: Hash,
};

// Fallback map by exposure_id, for when the API has not (yet) supplied a visual —
// e.g. a stale cache entry, or an offline render. The API value takes precedence.
const ICON_MAP: Record<string, LucideIcon> = {
  sector_semiconductor: Cpu,
  sector_financials: Landmark,
  sector_shipping: Ship,
  sector_memory: MemoryStick,
  sector_ai_server: Server,
  sector_robotics: Bot,
  sector_passive_components: CircuitBoard,
  sector_power_semiconductor: Zap,
  sector_silicon_photonics: Radio,
  sector_heavy_electrical: Plug,
  sector_networking: Network,
  sector_pcb_substrate: CircuitBoard,
  sector_silicon_ip: FileCode,
  sector_advanced_packaging: Package,
  sector_biotech: FlaskConical,
  sector_bicycle: Bike,
  sector_steel: Factory,
  sector_tourism: Plane,
  sector_semiconductor_equipment: Wrench,
  sector_liquid_cooling: Droplets,
};

const COLOR_MAP: Record<string, string> = {
  sector_semiconductor: '#3B82F6',
  sector_financials: '#F59E0B',
  sector_shipping: '#14B8A6',
  sector_memory: '#EF4444',
  sector_ai_server: '#8B5CF6',
  sector_robotics: '#06B6D4',
  sector_passive_components: '#10B981',
  sector_power_semiconductor: '#EAB308',
  sector_silicon_photonics: '#0EA5E9',
  sector_heavy_electrical: '#F97316',
  sector_networking: '#6366F1',
  sector_pcb_substrate: '#A855F7',
  sector_silicon_ip: '#EC4899',
  sector_advanced_packaging: '#D946EF',
  sector_biotech: '#22C55E',
  sector_bicycle: '#84CC16',
  sector_steel: '#94A3B8',
  sector_tourism: '#F43F5E',
  sector_semiconductor_equipment: '#2DD4BF',
  sector_liquid_cooling: '#38BDF8',
};

function hashHue(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

// Themes and sectors are one ``sector_`` namespace; collapse legacy ``theme_<id>``
// exposure ids (pre-migration episode data / stale cache) so the fallback maps and
// hashed-hue stay stable across the rename. Keep in sync with shared.sectors.normalize_exposure_id.
function normalizeExposureId(exposureId: string): string {
  return exposureId?.startsWith('theme_') ? `sector_${exposureId.slice('theme_'.length)}` : exposureId;
}

/** Resolve a lucide component: API icon_id → exposure_id fallback → Hash. */
function resolveIcon(exposureId: string, iconId?: string | null): LucideIcon {
  if (iconId && ICON_REGISTRY[iconId]) return ICON_REGISTRY[iconId];
  return ICON_MAP[normalizeExposureId(exposureId)] ?? Hash;
}

/** Resolve an accent color: API color_hex → exposure_id fallback → hashed hue. */
export function sectorColor(exposureId: string, colorHex?: string | null): string {
  const id = normalizeExposureId(exposureId || 'topic');
  return colorHex || COLOR_MAP[id] || `hsl(${hashHue(id)} 64% 56%)`;
}

interface SectorIconProps {
  exposureId: string;
  /** Lucide icon name from the API (compiled universe). Falls back to the exposure_id map. */
  iconId?: string | null;
  /** Accent color from the API. Falls back to the exposure_id map, then a hashed hue. */
  color?: string | null;
  className?: string;
  size?: number;
  /**
   * 'plain' — colored icon glyph only.
   * 'chip'  — icon inside a tinted, rounded square for a more colorful, tile-like look.
   */
  variant?: 'plain' | 'chip';
  /** Extra classes for the chip wrapper (variant="chip" only). */
  chipClassName?: string;
}

export const SectorIcon: React.FC<SectorIconProps> = ({
  exposureId,
  iconId,
  color: colorProp,
  className = '',
  size = 14,
  variant = 'plain',
  chipClassName = '',
}) => {
  const Icon = resolveIcon(exposureId, iconId);
  const color = sectorColor(exposureId, colorProp);

  if (variant === 'chip') {
    const box = Math.round(size * 1.7);
    return (
      <span
        className={`inline-grid place-items-center rounded-md shrink-0 ${chipClassName}`}
        style={{
          width: box,
          height: box,
          color,
          backgroundColor: `${color}24`, // ~14% tint
        }}
      >
        <Icon size={size} />
      </span>
    );
  }

  return <Icon size={size} className={className} style={{ color }} />;
};
