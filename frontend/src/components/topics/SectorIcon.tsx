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
  Hash,
  type LucideIcon,
} from 'lucide-react';

// Map exposure_id prefixes / exact ids to lucide icons
const ICON_MAP: Record<string, LucideIcon> = {
  sector_semiconductor: Cpu,
  sector_financials: Landmark,
  sector_shipping: Ship,
  sector_memory: MemoryStick,
  theme_ai_server: Server,
  theme_robotics: Bot,
  sector_passive_components: CircuitBoard,
  theme_power_semiconductor: Zap,
  theme_silicon_photonics: Radio,
  sector_heavy_electrical: Plug,
  sector_networking: Network,
  sector_pcb_substrate: CircuitBoard,
  theme_silicon_ip: FileCode,
  theme_advanced_packaging: Package,
  sector_biotech: FlaskConical,
  sector_bicycle: Bike,
  sector_steel: Factory,
  sector_tourism: Plane,
};

interface SectorIconProps {
  exposureId: string;
  className?: string;
  size?: number;
}

export const SectorIcon: React.FC<SectorIconProps> = ({
  exposureId,
  className = '',
  size = 14,
}) => {
  const Icon = ICON_MAP[exposureId] ?? Hash;
  return <Icon size={size} className={className} />;
};
