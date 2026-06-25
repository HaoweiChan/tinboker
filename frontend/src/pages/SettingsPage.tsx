import React, { useEffect, useState } from 'react';
import { Sun, Bell, Loader2, Smartphone, User as UserIcon, Camera } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { PWAInstallSection } from '@/components/common/PWAInstallPrompt';
import { useStockColorMode, useSetStockColorMode } from '@/hooks/useStockTrendColor';
import { useAppStore } from '@/store/useAppStore';
import { userApi } from '@/services/api/user';
import { userSettingsApi, type NotificationPreferences } from '@/services/api/userSettings';
import { Modal } from '@/components/ui/Modal';
import { AvatarCropper } from '@/components/common/AvatarCropper';

// Reject absurd source files before decoding (the cropper bounds the *output* size, but a
// huge source still has to be loaded into memory first).
const MAX_AVATAR_SOURCE_BYTES = 12 * 1024 * 1024; // 12 MB

function initials(name?: string): string {
  return (name || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
}

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
    <div className="flex items-center gap-2.5 text-lg font-semibold tracking-[-0.01em] mb-4">
      {icon}
      {title}
    </div>
    {children}
  </section>
);

const SettingsRow: React.FC<{ label: string; hint: string; control: React.ReactNode; last?: boolean }> = ({ label, hint, control, last }) => (
  <div className={cn('flex items-center justify-between gap-6 py-4', !last && 'border-b border-border')}>
    <div className="min-w-0">
      <div className="text-base font-medium mb-1">{label}</div>
      <div className="text-xs text-muted-foreground leading-[1.5]">{hint}</div>
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
  const user = useAppStore((s) => s.user);
  const updateUser = useAppStore((s) => s.updateUser);
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const stockColorMode = useStockColorMode();
  const setStockColorMode = useSetStockColorMode();
  const fontSize = useAppStore((s) => s.fontSize);
  const setFontSize = useAppStore((s) => s.setFontSize);

  // Profile (display name + avatar) — seeded from the store, saved via PATCH /api/user/me.
  const [name, setName] = useState('');
  const [avatar, setAvatar] = useState<string | undefined>(undefined);
  const [savingProfile, setSavingProfile] = useState(false);
  const [cropFile, setCropFile] = useState<File | null>(null);
  useEffect(() => {
    setName(user?.name ?? '');
    setAvatar(user?.avatar || undefined);
    // Re-seed only when the logged-in identity changes — not on every name/avatar edit,
    // which would clobber in-progress input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);
  const profileDirty = !!user && (name.trim() !== (user.name ?? '') || (avatar || '') !== (user.avatar || ''));
  const pickAvatar = (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('請選擇圖片檔');
      return;
    }
    if (file.size > MAX_AVATAR_SOURCE_BYTES) {
      toast.error('圖片過大（上限 12MB）');
      return;
    }
    setCropFile(file);
  };
  const saveProfile = async () => {
    const n = name.trim();
    if (n.length < 1 || n.length > 40) {
      toast.error('名稱長度需為 1–40 字');
      return;
    }
    setSavingProfile(true);
    try {
      const patch: { name?: string; avatar?: string } = {};
      if (n !== user?.name) patch.name = n;
      if ((avatar || '') !== (user?.avatar || '')) patch.avatar = avatar ?? '';
      const updated = await userApi.updateProfile(patch);
      updateUser({ name: updated.name, avatar: updated.avatar });
      toast.success('個人檔案已更新');
    } catch {
      toast.error('更新失敗，請稍後再試');
    } finally {
      setSavingProfile(false);
    }
  };

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
        <SettingsSection icon={<UserIcon size={18} />} title="個人檔案">
          {!token ? (
            <div className="text-center py-8 text-sm text-muted-foreground">請先登入以編輯個人檔案</div>
          ) : (
            <div className="flex items-center gap-5 flex-wrap">
              <label className="relative cursor-pointer shrink-0 group">
                {avatar ? (
                  <img src={avatar} alt="" className="w-[72px] h-[72px] rounded-full object-cover" />
                ) : (
                  <div className="w-[72px] h-[72px] rounded-full grid place-items-center text-white text-2xl font-semibold bg-accent-info">{initials(name)}</div>
                )}
                <span className="absolute inset-0 rounded-full bg-black/45 grid place-items-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <Camera size={20} className="text-white" />
                </span>
                <input type="file" accept="image/*" className="hidden" onChange={(e) => { pickAvatar(e.target.files?.[0]); e.target.value = ''; }} />
              </label>

              <div className="flex-1 min-w-[200px]">
                <label className="block text-xs text-muted-foreground mb-1.5">顯示名稱</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={40}
                  placeholder="你的名稱"
                  className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-accent-info"
                />
                {avatar && (
                  <button type="button" onClick={() => setAvatar(undefined)} className="mt-2 text-xs text-accent-info hover:underline">移除頭像</button>
                )}
              </div>

              <button
                type="button"
                onClick={saveProfile}
                disabled={!profileDirty || savingProfile}
                className="px-4 py-2 rounded-full text-sm font-medium bg-foreground text-background hover:opacity-90 disabled:opacity-40 transition-opacity"
              >
                {savingProfile ? '儲存中…' : '儲存'}
              </button>
            </div>
          )}
        </SettingsSection>

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
          />
          <SettingsRow
            label="字體大小"
            hint="調整全站文字大小。"
            control={
              <div className="flex gap-1">
                {(['sm', 'base', 'lg'] as const).map((s, i) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setFontSize(s)}
                    className={cn('px-3 py-1.5 rounded text-sm font-medium transition-colors border', fontSize === s ? 'bg-foreground text-background border-foreground' : 'bg-muted text-muted-foreground border-border hover:border-foreground/30')}
                  >
                    {['小', '中', '大'][i]}
                  </button>
                ))}
              </div>
            }
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
            <div className="text-center py-8 text-sm text-muted-foreground">請先登入以管理通知設定</div>
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

      <Modal isOpen={!!cropFile} onClose={() => setCropFile(null)} title="調整頭像">
        {cropFile && (
          <AvatarCropper
            file={cropFile}
            onCancel={() => setCropFile(null)}
            onDone={(uri) => { setAvatar(uri); setCropFile(null); }}
          />
        )}
      </Modal>
    </>
  );
};

export default SettingsPage;
