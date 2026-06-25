import React from 'react';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import { useStockColorMode, useSetStockColorMode } from '@/hooks/useStockTrendColor';

const TC = { fontFamily: "'Noto Sans TC', sans-serif" } as const;

const Toggle: React.FC<{ checked: boolean; onChange: () => void; label: string }> = ({ checked, onChange, label }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onClick={onChange}
    className={cn(
      'relative inline-flex h-[24px] w-[44px] shrink-0 items-center rounded-full transition-colors',
      checked ? 'bg-accent-info' : 'bg-muted',
    )}
  >
    <span className={cn('inline-block h-[18px] w-[18px] rounded-full bg-white shadow transition-transform', checked ? 'translate-x-[23px]' : 'translate-x-[3px]')} />
  </button>
);

const Row: React.FC<{ label: string; hint: string; control: React.ReactNode; last?: boolean }> = ({ label, hint, control, last }) => (
  <div className={cn('flex items-center justify-between gap-4 py-3', !last && 'border-b border-border')}>
    <div className="min-w-0">
      <div className="text-sm font-medium text-foreground" style={TC}>{label}</div>
      <div className="text-2xs text-muted-foreground leading-[1.5]" style={TC}>{hint}</div>
    </div>
    {control}
  </div>
);

/** Compact display-preference controls (色彩模式 / 深色模式 / 字體大小) for the
 *  onboarding modal. Writes straight to the shared store, so choices made here are
 *  the same ones the Settings page edits. */
export const DisplayPreferences: React.FC = () => {
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const fontSize = useAppStore((s) => s.fontSize);
  const setFontSize = useAppStore((s) => s.setFontSize);
  const stockColorMode = useStockColorMode();
  const setStockColorMode = useSetStockColorMode();

  return (
    <div className="px-0.5">
      <Row
        label="美股/國際模式 (綠漲紅跌)"
        hint="啟用後上漲為綠、下跌為紅；關閉則為台股紅漲綠跌。"
        control={<Toggle checked={stockColorMode === 'US'} onChange={() => setStockColorMode(stockColorMode === 'US' ? 'TW' : 'US')} label="美股/國際模式" />}
      />
      <Row
        label="深色模式"
        hint="切換介面為深色背景。"
        control={<Toggle checked={theme === 'dark'} onChange={() => setTheme(theme === 'dark' ? 'light' : 'dark')} label="深色模式" />}
      />
      <Row
        label="字體大小"
        hint="調整全站文字大小。"
        last
        control={
          <div className="flex gap-1">
            {(['sm', 'base', 'lg'] as const).map((s, i) => (
              <button
                key={s}
                type="button"
                onClick={() => setFontSize(s)}
                className={cn(
                  'px-2.5 py-1 rounded-sm text-xs font-medium border transition-colors',
                  fontSize === s ? 'bg-foreground text-background border-foreground' : 'bg-muted text-muted-foreground border-border hover:border-foreground/30',
                )}
                style={TC}
              >
                {['小', '中', '大'][i]}
              </button>
            ))}
          </div>
        }
      />
    </div>
  );
};
