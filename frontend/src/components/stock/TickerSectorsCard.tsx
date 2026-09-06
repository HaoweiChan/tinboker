import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { getSectorsByTicker } from '@/services/api/stocks';
import type { SectorByTickerItem } from '@/validation/schemas';

interface TickerSectorsCardProps {
  symbol: string;
  className?: string;
  /** 'chips': bento tile with just the sector chips (cyan), no reasons. */
  variant?: 'full' | 'chips';
}

export const TickerSectorsCard: React.FC<TickerSectorsCardProps> = ({ symbol, className, variant = 'full' }) => {
  const [items, setItems] = useState<SectorByTickerItem[]>([]);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setVisible(false);
    getSectorsByTicker(symbol)
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        setVisible(response.items.length > 0);
      })
      .catch(() => {
        if (cancelled) return;
        setItems([]);
        setVisible(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (!visible) return null;

  if (variant === 'chips') {
    return (
      <div className={cn('bg-card border border-border rounded-[10px] p-5 flex flex-col gap-2.5', className)}>
        <div className="text-xs text-muted-foreground">所屬題材</div>
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <Link
              key={item.exposure_id}
              to={`/sector/${encodeURIComponent(item.exposure_id)}`}
              title={item.reason || undefined}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent-info-soft text-accent-info px-2.5 py-1 text-xs font-medium hover:opacity-80 transition-opacity"
            >
              <SectorIcon exposureId={item.exposure_id} iconId={item.icon_id} color={item.color_hex} size={12} variant="chip" />
              {item.display_name}
            </Link>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-card border border-border rounded-md p-5', className)}>
      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">所屬產業與題材</h3>
      <div className="flex flex-col gap-2.5">
        {items.map((item) => (
          <div key={item.exposure_id} className="rounded-md border border-border/60 bg-muted/20 px-2.5 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <SectorIcon
                exposureId={item.exposure_id}
                iconId={item.icon_id}
                color={item.color_hex}
                size={13}
                variant="chip"
              />
              <Link
                to={`/sector/${encodeURIComponent(item.exposure_id)}`}
                className="inline-flex min-w-0 max-w-full items-center rounded-full bg-muted px-2 py-1 text-sm font-medium leading-none hover:bg-muted/80 transition-colors"
              >
                <span className="truncate">{item.display_name}</span>
              </Link>
            </div>
            {item.reason && (
              <p className="text-xs leading-[1.6] text-muted-foreground mt-1 pt-2.5 border-t border-border/60">
                {item.reason}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
