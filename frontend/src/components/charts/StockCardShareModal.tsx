import React, { useEffect, useMemo, useState } from 'react';
import { Download, Share2 } from 'lucide-react';
import { toast } from 'sonner';
import { Modal } from '@/components/ui/Modal';

interface StockCardShareModalProps {
    url: string;
    ticker: string;
    onClose: () => void;
}

/**
 * Preview of the stock card PNG with 分享 / 下載.
 *
 * The button used to be a plain link to the PNG with Content-Disposition. In the installed
 * app (standalone PWA) that link has nowhere to go, so tapping it did nothing visible. Now
 * the card is fetched once (the API sends CORS) and held as a File: the preview, the share
 * sheet and the download all use those bytes.
 *
 * The fetch starts when the modal opens, not on 分享 — navigator.share needs a recent tap,
 * and a cold card can take ~5s to render, which would outlive it.
 */
export const StockCardShareModal: React.FC<StockCardShareModalProps> = ({ url, ticker, onClose }) => {
    const [file, setFile] = useState<File | null>(null);
    const [failed, setFailed] = useState(false);
    const filename = `${ticker}-${new Date().toISOString().slice(0, 10)}.png`;

    useEffect(() => {
        let alive = true;
        fetch(url)
            .then((r) => {
                if (!r.ok) throw new Error(`card ${r.status}`);
                return r.blob();
            })
            .then((blob) => {
                if (alive) setFile(new File([blob], filename, { type: 'image/png' }));
            })
            .catch(() => {
                if (alive) setFailed(true);
            });
        return () => { alive = false; };
    }, [url, filename]);

    const objectUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
    useEffect(() => () => { if (objectUrl) URL.revokeObjectURL(objectUrl); }, [objectUrl]);

    // Desktop Firefox and older browsers can't share files; they get 下載 only.
    const canShare = !!file && typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] });

    const share = async () => {
        if (!file) return;
        try {
            await navigator.share({ files: [file], title: `${ticker} 走勢圖卡` });
        } catch (e) {
            if ((e as Error).name !== 'AbortError') toast.error('分享失敗，請改用下載');
        }
    };

    return (
        <Modal isOpen onClose={onClose} title="走勢圖卡">
            <div className="p-4">
                <div className="aspect-square w-full overflow-hidden rounded-md border border-border bg-muted/30">
                    {objectUrl ? (
                        <img src={objectUrl} alt={`${ticker} 走勢圖卡`} className="h-full w-full object-contain" />
                    ) : failed ? (
                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">圖卡產生失敗，請稍後再試</div>
                    ) : (
                        <div className="h-full w-full animate-pulse" />
                    )}
                </div>
                <div className="mt-4 flex gap-2">
                    {canShare && (
                        <button
                            type="button"
                            onClick={share}
                            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition-opacity"
                        >
                            <Share2 size={15} /> 分享
                        </button>
                    )}
                    <a
                        href={objectUrl ?? undefined}
                        download={filename}
                        aria-disabled={!objectUrl}
                        className={`flex flex-1 items-center justify-center gap-1.5 rounded-md border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors ${objectUrl ? 'hover:bg-muted' : 'pointer-events-none opacity-50'}`}
                    >
                        <Download size={15} /> 下載
                    </a>
                </div>
            </div>
        </Modal>
    );
};
