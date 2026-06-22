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
                        <p className="text-muted-foreground">
                            目前播放中：
                            <br />
                            <span className="font-semibold text-foreground">
                                {player.currentEpisodeData.title}
                            </span>
                        </p>
                        <p className="text-muted-foreground">
                            即將切換至：
                            <br />
                            <span className="font-semibold text-foreground">
                                {player.pendingEpisode.title}
                            </span>
                        </p>
                    </div>
                </div>

                <div className="flex justify-end gap-3 mt-6">
                    <button
                        onClick={cancelPlay}
                        className="px-4 py-2 text-base font-medium text-muted-foreground hover:bg-muted rounded-lg transition-colors"
                    >
                        取消
                    </button>
                    <button
                        onClick={confirmPlay}
                        className="px-4 py-2 text-base font-medium text-white bg-accent-info hover:bg-accent-info rounded-lg transition-colors"
                    >
                        切換播放
                    </button>
                </div>
            </div>
        </Modal>
    );
};
