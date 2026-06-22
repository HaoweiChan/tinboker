import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { ChangePct } from '@/components/topics/ChangePct';
import type { SectorExposure, SectorBoardItem, SectorResolvedTicker } from '@/services/api/podcasts';

interface SectorExposureRowProps {
  exp: SectorExposure;
  /** Matching board entry (avg_change + visuals); absent if the sector isn't on the board. */
  perf?: SectorBoardItem;
  /** True while the board is still loading, so the change shows a skeleton not a dash. */
  loading?: boolean;
}

/**
 * One sector/theme exposure: a compact row showing the colorful icon, the name,
 * and the sector's aggregate performance. Collapsed by default; the chevron
 * expands the full list of constituent tickers so the rail stays scannable.
 */
const SectorExposureRow: React.FC<SectorExposureRowProps> = ({ exp, perf, loading = false }) => {
  const [open, setOpen] = useState(false);
  const tickers = exp.resolved_tickers ?? [];
  const hasTickers = tickers.length > 0;

  return (
    <div className="rounded-md border border-border/60 bg-muted/20 overflow-hidden">
      <div className="flex items-center gap-2 px-2.5 py-2">
        <SectorIcon
          exposureId={exp.exposure_id}
          iconId={perf?.icon_id}
          color={perf?.color_hex}
          size={13}
          variant="chip"
        />
        <Link
          to={`/sector/${encodeURIComponent(exp.exposure_id)}`}
          className="text-sm font-medium hover:underline truncate flex-1 min-w-0 leading-snug"
        >
          {exp.display_name}
        </Link>
        <ChangePct value={perf?.avg_change ?? null} sizeClass="text-xs" skeleton={loading && !perf} />
        {hasTickers && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-label={open ? `收合 ${exp.display_name} 成分股` : `展開 ${exp.display_name} 成分股`}
            className="shrink-0 p-0.5 -mr-0.5 rounded text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronDown size={14} className={cn('transition-transform duration-200', open && 'rotate-180')} />
          </button>
        )}
      </div>

      {open && hasTickers && (
        <div className="flex flex-wrap gap-1 px-2.5 pb-2.5 pt-0.5">
          {tickers.map((rt: SectorResolvedTicker) => (
            <Link
              key={rt.ticker}
              to={`/stock/${encodeURIComponent(rt.ticker)}`}
              title={rt.name}
              className="inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded bg-muted hover:bg-muted/80 transition-colors"
            >
              <span className="font-mono text-2xs text-muted-foreground">{rt.ticker.replace(/\.[A-Z]+$/i, '')}</span>
              {rt.name && rt.name !== rt.ticker && <span>{rt.name}</span>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

interface SectorExposureListProps {
  exposures: SectorExposure[];
  /** exposure_id → board entry, for the per-sector performance + visuals. */
  perfMap: Map<string, SectorBoardItem>;
  loading?: boolean;
}

/** Collapse duplicate exposure_ids (episodes can tag the same sector more than once),
 *  keeping the entry with the richest constituent list. */
function dedupeExposures(exposures: SectorExposure[]): SectorExposure[] {
  const byId = new Map<string, SectorExposure>();
  for (const exp of exposures) {
    const prev = byId.get(exp.exposure_id);
    if (!prev || (exp.resolved_tickers?.length ?? 0) > (prev.resolved_tickers?.length ?? 0)) {
      byId.set(exp.exposure_id, exp);
    }
  }
  return [...byId.values()];
}

export const SectorExposureList: React.FC<SectorExposureListProps> = ({ exposures, perfMap, loading }) => (
  <div className="flex flex-col gap-1.5">
    {dedupeExposures(exposures).map((exp) => (
      <SectorExposureRow key={exp.exposure_id} exp={exp} perf={perfMap.get(exp.exposure_id)} loading={loading} />
    ))}
  </div>
);
