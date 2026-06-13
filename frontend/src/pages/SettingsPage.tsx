import React, { useEffect, useState } from 'react';
import { Sun, Bell, Loader2, Smartphone } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { PWAInstallSection } from '@/components/common/PWAInstallPrompt';
import { useStockColorMode, useSetStockColorMode } from '@/hooks/useStockTrendColor';
import { useAppStore } from '@/store/useAppStore';
import { userSettingsApi, type NotificationPreferences } from '@/services/api/userSettings';

interface ToggleProps {
  checked: boolean;
  onChange: () => void;
  loading?: boolean;
  'aria-label'?: string;
}

/** Pill toggle — blue when on, muted track when off. */
const Toggle: React.FC<ToggleProps> = ({ checked, onChange, loading, ...rest }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={rest['aria-label']}
    onClick={() => !loading && onChange()}
    disabled={loading}
    className={cn(
      'relative inline-flex h-[26px] w-[46px] shrink-0 items-center rounded-full transition-colors',
      checked ? 'bg-accent-info' : 'bg-muted',
      loading && 'opacity-50 cursor-not-allowed',
    )}
  >
    {loading ? (
      <Loader2 className="absolute inset-0 m-auto h-3.5 w-3.5 animate-spin text-foreground" />
    ) : (
      <span className={cn('inline-block h-5 w-5 rounded-full bg-white shadow transition-transform', checked ? 'translate-x-[22px]' : 'translate-x-[3px]')} />
    )}
  </button>
);

const SettingsSection: React.FC<{ icon: React.ReactNode; title: string; children: React.ReactNode }> = ({ icon, title, children }) => (
  <section className="bg-card border border-border rounded-md px-5 sm:px-6 py-5 mb-4">
    <div className="flex items-center gap-2.5 text-[16px] font-semibold tracking-[-0.01em] mb-4">
      {icon}
      {title}
    </div>
    {children}
  </section>
);

const SettingsRow: React.FC<{ label: string; hint: string; control: React.ReactNode; last?: boolean }> = ({ label, hint, control, last }) => (
  <div className={cn('flex items-center justify-between gap-6 py-4', !last && 'border-b border-border')}>
    <div className="min-w-0">
      <div className="text-[14px] font-medium mb-1">{label}</div>
      <div className="text-[12px] text-muted-foreground leading-[1.5]">{hint}</div>
    </div>
    {control}
  </div>
);

const NOTIF_ROWS: { key: keyof NotificationPreferences; label: string; hint: string }[] = [
  { key: 'new_episodes', label: '訂閱的 Podcast 新集數', hint: '當您訂閱的 Podcast 發布新集數時發送通知。' },
  { key: 'stock_mentions', label: '追蹤標的被提及', hint: '當您的自選股被 Podcast 提及時發送通知。' },
  { key: 'price_alerts', label: '價格警示', hint: '當追蹤標的達到設定的價格條件時發送通知。' },
  { key: 'daily_digest', label: '每日市場摘要', hint: '每天早上 8:00 發送昨日市場重點整理。' },
];

export const SettingsPage: React.FC = () => {
  const token = useAppStore((s) => s.token);
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const stockColorMode = useStockColorMode();
  const setStockColorMode = useSetStockColorMode();

  const [prefs, setPrefs] = useState<NotificationPreferences>({ new_episodes: true, stock_mentions: true, price_alerts: true, daily_digest: false });
  const [loadingPrefs, setLoadingPrefs] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoadingPrefs(true);
    userSettingsApi
      .getNotificationPreferences()
      .then(setPrefs)
      .catch((e) => console.error('Failed to load notification preferences:', e))
      .finally(() => setLoadingPrefs(false));
  }, [token]);

  const toggleNotif = async (key: keyof NotificationPreferences) => {
    if (!token) {
      toast.error('請先登入');
      return;
    }
    const prev = prefs[key];
    setPrefs((p) => ({ ...p, [key]: !prev }));
    setSavingKey(key);
    try {
      await userSettingsApi.updateNotificationPreferences({ [key]: !prev });
      toast.success('通知設定已更新');
    } catch (e) {
      setPrefs((p) => ({ ...p, [key]: prev }));
      toast.error('更新通知設定失敗');
      console.error('Failed to update notification preferences:', e);
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <>
      <SEO title="帳號設定" description="顯示、通知與偏好設定。" />
      <PageContent className="max-w-[680px]">
        <SettingsSection icon={<Sun size={18} />} title="顯示設定">
          <SettingsRow
            label="美股/國際模式 (綠漲紅跌)"
            hint="啟用後，上漲與看多顯示為綠色，下跌與看空顯示為紅色。"
            control={<Toggle checked={stockColorMode === 'US'} onChange={() => setStockColorMode(stockColorMode === 'US' ? 'TW' : 'US')} aria-label="美股/國際模式" />}
          />
          <SettingsRow
            label="深色模式"
            hint="切換介面為深色背景顯示。"
            control={<Toggle checked={theme === 'dark'} onChange={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="深色模式" />}
            last
          />
        </SettingsSection>

        <SettingsSection icon={<Smartphone size={18} />} title="安裝 App">
          <PWAInstallSection />
        </SettingsSection>

        <SettingsSection icon={<Bell size={18} />} title="通知設定">
          {loadingPrefs ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !token ? (
            <div className="text-center py-8 text-[13px] text-muted-foreground">請先登入以管理通知設定</div>
          ) : (
            NOTIF_ROWS.map((row, i) => (
              <SettingsRow
                key={row.key}
                label={row.label}
                hint={row.hint}
                last={i === NOTIF_ROWS.length - 1}
                control={<Toggle checked={prefs[row.key]} onChange={() => toggleNotif(row.key)} loading={savingKey === row.key} aria-label={row.label} />}
              />
            ))
          )}
        </SettingsSection>
      </PageContent>
    </>
  );
};

export default SettingsPage;
