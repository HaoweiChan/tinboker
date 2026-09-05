import React, { useEffect, useMemo, useState } from 'react';
import { Flame } from 'lucide-react';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import { ChangePct } from '@/components/topics/ChangePct';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { getSectorBoard, type SectorBoardItem } from '@/services/api/podcasts';

interface SectorHeatCardProps {
  exposureId: string;
}

/** Where this sector sits on the /topics board right now: discussion-heat rank among
 *  all sectors, the members' average move, and the aggregate trajectory the bubble
 *  chart draws. One cached board call; hidden when the sector is not on the board. */
export const SectorHeatCard: React.FC<SectorHeatCardProps> = ({ exposureId }) => {
  const [board, setBoard] = useState<SectorBoardItem[] | null>(null);

  useEffect(() => {
    let alive = true;
    getSectorBoard()
      .then((b) => { if (alive) setBoard(b); })
      .catch(() => { if (alive) setBoard([]); });
    return () => { alive = false; };
  }, []);

  const view = useMemo(() => {
    if (!board || board.length === 0) return null;
    const me = board.find((s) => s.exposure_id === exposureId);
    if (!me) return null;
    const byHeat = [...board].sort((a, b) => (b.heat ?? 0) - (a.heat ?? 0));
    const byChange = [...board].filter((s) => s.avg_change != null).sort((a, b) => (b.avg_change ?? 0) - (a.avg_change ?? 0));
    const rankHeat = byHeat.findIndex((s) => s.exposure_id === exposureId) + 1;
    const rankChange = byChange.findIndex((s) => s.exposure_id === exposureId) + 1;
    const series = (me.series && me.series.length > 1 ? me.series : null)
      // Fall back to the members' mean normalized path when the board omits the aggregate.
      ?? meanSeries(me.members.map((m) => m.series ?? []).filter((s) => s.length > 1));
    return { me, rankHeat, rankChange, total: board.length, changeTotal: byChange.length, series };
  }, [board, exposureId]);

  const trend = useStockTrendColor(view?.me.avg_change ?? 0);
  if (!view) return null;
  const { me, rankHeat, rankChange, total, changeTotal, series } = view;
  const hot = rankHeat > 0 && rankHeat <= Math.max(3, Math.ceil(total * 0.1));

  return (
    <div className="bg-card border border-border rounded-md p-5 mb-7">
      <div className="flex items-center gap-2 mb-3.5">
        <Flame size={14} className={hot ? 'text-accent-warning' : 'text-muted-foreground'} />
        <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">討論熱度與成分股表現</h3>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 items-end">
        <div>
          <div className="text-2xs uppercase tracking-wider text-muted-foreground mb-1">討論熱度排名</div>
          <div className="text-2xl font-mono tabular-nums font-semibold">
            #{rankHeat}<span className="text-sm text-muted-foreground font-normal"> / {total}</span>
          </div>
          <div className="text-2xs text-muted-foreground mt-0.5">近期 {me.episode_count} 集提及</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-muted-foreground mb-1">成分股平均漲跌</div>
          <div className="text-2xl font-mono tabular-nums font-semibold">
            {me.avg_change != null ? <ChangePct value={me.avg_change} sizeClass="text-2xl" showArrow /> : '—'}
          </div>
          <div className="text-2xs text-muted-foreground mt-0.5">{rankChange > 0 ? `漲幅排名 #${rankChange} / ${changeTotal}` : '無價格資料'}</div>
        </div>
        <div className="col-span-2">
          <div className="text-2xs uppercase tracking-wider text-muted-foreground mb-1">成分股近 12 日走勢</div>
          {series && series.length > 1 ? (
            <SimpleSparkline data={series} isPositive={(me.avg_change ?? 0) >= 0} color={trend.lineColor} width={260} height={48} smooth />
          ) : (
            <div className="h-12 flex items-center text-xs text-muted-foreground">—</div>
          )}
        </div>
      </div>
      <p className="text-2xs text-muted-foreground/70 leading-relaxed mt-3">
        熱度為近期 Podcast 提及的時間加權；排名以話題排行頁全部 {total} 個題材為母體。整體「熱度是否預測報酬」的驗證見話題排行頁。
      </p>
    </div>
  );
};

// Element-wise mean of series normalized to their first value, so members at very
// different price levels contribute equally.
function meanSeries(list: number[][]): number[] | null {
  if (list.length === 0) return null;
  const len = Math.min(...list.map((s) => s.length));
  const out: number[] = [];
  for (let i = 0; i < len; i++) {
    let sum = 0, n = 0;
    for (const s of list) {
      const base = s[0];
      if (!base) continue;
      sum += s[i] / base; n++;
    }
    out.push(n ? sum / n : 1);
  }
  return out.length > 1 ? out : null;
}
