import { useEffect, useState } from 'react';
import { z } from 'zod';
import { apiClient } from '@/services/api/client';
import { useAppStore } from '@/store/useAppStore';

function authConfig() {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    return { headers: { Authorization: `Bearer ${token}` }, timeout: 90000 };
}

const statusSchema = z.object({
    tracked_posts: z.number(), metric_snapshots: z.number(), backfill_complete: z.boolean(),
});
const pageSchema = z.object({
    available: z.boolean(), complete: z.boolean().optional(), busy: z.boolean().optional(),
    more_pages: z.boolean().optional(), root_posts: z.number().optional(),
    already_tracked: z.number().optional(), would_import: z.number().optional(),
    insights_available: z.boolean().optional(), insight_metrics: z.array(z.string()).optional(),
    imported: z.number().optional(), metrics_captured: z.number().optional(),
    errors: z.number().optional(), unusable_timestamps: z.number().optional(),
    unavailable_metrics: z.number().optional(), truncated_reply_posts: z.number().optional(),
});

export function ThreadsHistorySync() {
    const [status, setStatus] = useState<z.infer<typeof statusSchema> | null>(null);
    const [preview, setPreview] = useState<z.infer<typeof pageSchema> | null>(null);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState('');
    const refresh = async () => {
        const response = await apiClient.get('/api/admin/threads/history-sync/status', authConfig());
        setStatus(statusSchema.parse(response.data));
    };
    useEffect(() => { void refresh().catch(() => setMessage('無法讀取回補狀態，請稍後重新預覽。')); }, []);

    const dryRun = async () => {
        setBusy(true);
        setPreview(null);
        try {
            await refresh();
            const response = await apiClient.post('/api/admin/threads/history-sync/dry-run', {}, authConfig());
            const result = pageSchema.parse(response.data);
            setPreview(result);
            setMessage(result.complete ? '歷史回補已完成。' : result.available
                ? `本批 ${result.root_posts ?? 0} 篇主貼文，已追蹤 ${result.already_tracked ?? 0} 篇，預計新增 ${result.would_import ?? 0} 篇。成效指標：${result.insight_metrics?.length ?? 0} 項。尚未寫入資料。`
                : 'Threads 尚未連線。');
        } catch {
            setMessage('預覽失敗，未開始回補。請稍後重試。');
        } finally { setBusy(false); }
    };

    const backfill = async () => {
        setBusy(true);
        let imported = 0;
        let sampled = 0;
        let incomplete = 0;
        try {
            for (let page = 1; page <= 100; page++) {
                const response = await apiClient.post('/api/admin/threads/history-sync/backfill', {}, authConfig());
                const result = pageSchema.parse(response.data);
                if (!result.available || result.busy) {
                    setMessage(result.busy ? '另一個收集工作正在執行，請稍後繼續。' : 'Threads 尚未連線。');
                    break;
                }
                imported += result.imported ?? 0;
                sampled += result.metrics_captured ?? 0;
                incomplete += Math.max(result.errors ?? 0, result.unavailable_metrics ?? 0) + (result.unusable_timestamps ?? 0);
                setMessage(`${result.complete ? '回補完成' : `已處理 ${page} 批`}：本次新增 ${imported} 篇，保存 ${sampled} 筆成效；${incomplete} 項資料未能完整取得。${page === 100 && !result.complete ? '請再按一次繼續回補。' : ''}`);
                if (result.complete || !result.more_pages) break;
            }
        } catch {
            setMessage(`回補暫停：本次已確認新增 ${imported} 篇、保存 ${sampled} 筆成效。已完成資料會保留，可再次按下繼續回補。`);
        } finally {
            await refresh().catch(() => {});
            setBusy(false);
        }
    };

    return (
        <div className="mt-4 rounded-lg border border-border p-3 text-sm">
            <p>歷史貼文與成效回補</p>
            <p className="mt-1 text-xs text-muted-foreground">取回已發佈貼文與目前成效，不會發文。過去未收集的每日數據無法還原。執行時請保持此頁開啟。</p>
            {status && <p className="mt-2">已追蹤 {status.tracked_posts} 篇 · 成效紀錄 {status.metric_snapshots} 筆 · {status.backfill_complete ? '歷史回補完成' : '歷史回補尚未完成'}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" disabled={busy} onClick={() => void dryRun()} className="rounded border border-border px-3 py-2 disabled:opacity-50">預覽回補</button>
                <button type="button" disabled={busy || !preview?.available || status?.backfill_complete} onClick={() => void backfill()} className="rounded border border-border px-3 py-2 disabled:opacity-50">{busy ? '處理中…' : '開始／繼續回補'}</button>
            </div>
            <p role="status" className="mt-2 text-xs text-muted-foreground">{message}</p>
        </div>
    );
}
