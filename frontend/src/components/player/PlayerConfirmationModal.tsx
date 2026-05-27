import React from 'react';
import { usePlayerStore } from '@/store/usePlayerStore';
import { Modal } from '@/components/ui/Modal';
import { AlertCircle } from 'lucide-react';

export const PlayerConfirmationModal: React.FC = () => {
    const { player, confirmPlay, cancelPlay } = usePlayerStore();

    if (!player.showPlayerConfirmation || !player.pendingEpisode || !player.currentEpisodeData) {
        return null;
    }

    return (
        <Modal
            isOpen={player.showPlayerConfirmation}
            onClose={cancelPlay}
            title="切換節目？"
            className="max-w-md"
        >
            <div className="p-4 space-y-4">
                <div className="flex items-start gap-4">
                    <div className="p-2 bg-accent-info-soft dark:bg-accent-info/30 rounded-full text-accent-info dark:text-accent-info shrink-0">
                        <AlertCircle size={24} />
                    </div>
                    <div className="space-y-2">
                        <p className="text-slate-600 dark:text-slate-300">
                            目前播放中：
                            <br />
                            <span className="font-semibold text-slate-900 dark:text-slate-100">
                                {player.currentEpisodeData.title}
                            </span>
                        </p>
                        <p className="text-slate-600 dark:text-slate-300">
                            即將切換至：
                            <br />
                            <span className="font-semibold text-slate-900 dark:text-slate-100">
                                {player.pendingEpisode.title}
                            </span>
                        </p>
                    </div>
                </div>

                <div className="flex justify-end gap-3 mt-6">
                    <button
                        onClick={cancelPlay}
                        className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                    >
                        取消
                    </button>
                    <button
                        onClick={confirmPlay}
                        className="px-4 py-2 text-sm font-medium text-white bg-accent-info hover:bg-accent-info rounded-lg transition-colors"
                    >
                        切換播放
                    </button>
                </div>
            </div>
        </Modal>
    );
};
