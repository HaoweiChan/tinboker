import React, { useEffect, useState } from 'react';
import { FlaskConical, Info } from 'lucide-react';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { TOPICS_TYPOGRAPHY } from './topicsTypography';
import { ChangePct } from './ChangePct';
import { getHeatValidation, type HeatValidation, type HeatValidationBucket } from '@/services/api/podcasts';

// Horizons mirror the bubble chart's 7/30/90D toggle — same framing, corrected data.
const HZ = ['7', '30', '90'] as const;
type Hz = (typeof HZ)[number];

const bucketLabel = (b: number, total: number): string =>
  b === 1 ? '討論最冷' : b === total ? '討論最熱' : `Q${b}`;

// One quantile row — its own component so useStockTrendColor runs at hook top level.
const BucketRow: React.FC<{ b: HeatValidationBucket; total: number; maxAbs: number }> = ({ b, total, maxAbs }) => {
  const trend = useStockTrendColor(b.mean_return);
  const type = TOPICS_TYPOGRAPHY.className;
  const pct = maxAbs > 0 ? Math.min(100, (Math.abs(b.mean_return) / maxAbs) * 100) : 0;
  const positive = b.mean_return >= 0;

  return (
    <div className="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
      <span className={`${type.meta} w-14 shrink-0 text-muted-foreground`}>{bucketLabel(b.bucket, total)}</span>

      {/* Diverging bar: zero at center, up-color right / down-color left. */}
      <div className="relative flex-1 h-3">
        <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <div
          className="absolute inset-y-0 rounded-sm"
          style={{
            backgroundColor: trend.lineColor,
            opacity: 0.65,
            width: `${pct / 2}%`,
            left: positive ? '50%' : undefined,
            right: positive ? undefined : '50%',
          }}
        />
      </div>

      <div className="w-16 shrink-0 flex justify-end">
        <ChangePct value={b.mean_return} sizeClass={type.memberMetric} />
      </div>
      <span className={`${type.micro} w-10 shrink-0 text-right text-muted-foreground/60 font-mono tabular-nums`}>
        n={b.n}
      </span>
    </div>
  );
};

/**
 * Point-in-time validation panel for the /topics board. The live bubble chart pairs
 * *current* discussion heat with *trailing* return (both computed now) — a look-ahead
 * artifact. This panel recomputes heat *as of* past dates and quantizes it against the
 * *forward* 7/30/90-day return, so higher-heat buckets earning higher returns is the
 * only evidence that heat predicts profit. Buckets carry their sample count so a thin
 * (short price-history) bucket isn't mistaken for a robust one.
 */
export const HeatReturnValidation: React.FC = () => {
  const type = TOPICS_TYPOGRAPHY.className;
  const [data, setData] = useState<HeatValidation | null>(null);
  const [loading, setLoading] = useState(true);
  const [hz, setHz] = useState<Hz>('30');

  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getHeatValidation().catch(() => null);
      if (!alive) return;
      setData(res);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const horizon = data?.horizons?.[hz];
  const buckets = horizon?.buckets ?? [];
  const maxAbs = buckets.reduce((m, b) => Math.max(m, Math.abs(b.mean_return)), 0);

  if (loading) {
    return <div className="rounded-xl border border-border bg-card p-4 h-56 animate-pulse bg-muted/20" />;
  }
  if (!data) return null; // endpoint unavailable — panel is additive, fail silent

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2">
          <span className="inline-grid place-items-center rounded-lg bg-accent-info/10 text-accent-info shrink-0" style={{ width: 26, height: 26 }}>
            <FlaskConical size={15} />
          </span>
          <h2 className={`${type.sectionTitle} font-semibold`}>討論熱度 → 未來報酬驗證</h2>
        </div>
        <div className={`flex shrink-0 items-center gap-0.5 ${type.micro}`}>
          {HZ.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHz(h)}
              className={`rounded px-1.5 py-0.5 transition-colors ${
                hz === h ? 'bg-primary/15 font-semibold text-primary' : 'text-muted-foreground/70 hover:text-foreground'
              }`}
            >
              {h}日
            </button>
          ))}
        </div>
      </div>

      <p className={`mb-3 flex items-start gap-1.5 ${type.meta} text-muted-foreground`}>
        <Info size={12} className="mt-0.5 shrink-0" />
        <span>
          用<strong className="font-medium text-foreground/80">歷史當時</strong>的討論熱度分組，對照<strong className="font-medium text-foreground/80">其後 {hz} 日</strong>的題材平均報酬（非事後同時段），避免看後照鏡。熱度越高的組別報酬越高，才代表熱度有預測力。
        </span>
      </p>

      {buckets.length > 0 ? (
        <>
          <div className="divide-y divide-border/20">
            {buckets.map((b) => (
              <BucketRow key={b.bucket} b={b} total={buckets.length} maxAbs={maxAbs} />
            ))}
          </div>
          <p className={`mt-3 ${type.micro} text-muted-foreground/60 font-mono tabular-nums`}>
            {horizon?.n ?? 0} 筆觀察 · {data.as_of_count} 個交易日
            {data.date_span.start && data.date_span.end ? ` · ${data.date_span.start}~${data.date_span.end}` : ''}
          </p>
        </>
      ) : (
        <div className={`py-8 text-center ${type.empty} text-muted-foreground`}>
          {hz} 日觀察資料不足（價格歷史約 90 日，長天期樣本較少）。
        </div>
      )}
    </div>
  );
};
