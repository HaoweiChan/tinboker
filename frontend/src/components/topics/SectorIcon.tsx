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
  Cable,
  Monitor,
  Laptop,
  Shirt,
  Building,
  Utensils,
  Sun,
  Lightbulb,
  Store,
  Settings,
  Fuel,
  HeartPulse,
  Code2,
  Wind,
  Mountain,
  Square,
  PlugZap,
  Layers,
  GitBranch,
  BatteryCharging,
  Satellite,
  Atom,
  SquareStack,
  Diamond,
  Battery,
  Minus,
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
  cable: Cable,
  monitor: Monitor,
  laptop: Laptop,
  shirt: Shirt,
  building: Building,
  utensils: Utensils,
  sun: Sun,
  lightbulb: Lightbulb,
  store: Store,
  settings: Settings,
  fuel: Fuel,
  'heart-pulse': HeartPulse,
  'code-2': Code2,
  wind: Wind,
  mountain: Mountain,
  square: Square,
  'plug-zap': PlugZap,
  layers: Layers,
  'git-branch': GitBranch,
  'battery-charging': BatteryCharging,
  satellite: Satellite,
  atom: Atom,
  'square-stack': SquareStack,
  diamond: Diamond,
  battery: Battery,
  minus: Minus,
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

/** Resolve a lucide component: API icon_id → Hash. */
// eslint-disable-next-line react-refresh/only-export-components
export function resolveIcon(_exposureId: string, iconId?: string | null): LucideIcon {
  if (iconId && ICON_REGISTRY[iconId]) return ICON_REGISTRY[iconId];
  return Hash;
}

// eslint-disable-next-line react-refresh/only-export-components
export function sectorColor(exposureId: string, colorHex?: string | null): string {
  const id = normalizeExposureId(exposureId || 'topic');
  return colorHex || `hsl(${hashHue(id)} 64% 56%)`;
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
