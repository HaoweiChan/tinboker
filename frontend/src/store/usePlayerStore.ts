import { create } from 'zustand';
import { playerBroadcast } from '@/services/PlayerBroadcast';
import type { PlayerBroadcastMessage } from '@/services/PlayerBroadcast';

interface TimestampedSection {
  title: string;
  timestampSeconds: number;
  formattedTime: string;
}

interface EpisodeData {
  id: string;
  title: string;
  showName: string;
  coverUrl?: string;
  spotifyUri?: string;
  mp3Url?: string;
  timestampedSections?: TimestampedSection[];
}

interface PlayerState {
  currentEpisodeId: string | null;
  isPlaying: boolean;
  isPlayerVisible: boolean;
  currentEpisodeData: EpisodeData | null;
  seekRequest: number | null;
  pendingEpisode: Omit<EpisodeData, 'timestampedSections'> | null;
  pendingSeek: number | null;
  showPlayerConfirmation: boolean;
}

interface PlayerStore {
  player: PlayerState;
  playEpisode: (data: EpisodeData, options?: { seekTo?: number }) => void;
  requestSeek: (seconds: number) => void;
  clearSeekRequest: () => void;
  closePlayer: () => void;
  confirmPlay: () => void;
  cancelPlay: () => void;
  closePlayerConfirmation: () => void;
}

export const usePlayerStore = create<PlayerStore>()((set, get) => ({
  player: {
    currentEpisodeId: null,
    isPlaying: false,
    isPlayerVisible: false,
    currentEpisodeData: null,
    seekRequest: null,
    pendingEpisode: null,
    pendingSeek: null,
    showPlayerConfirmation: false,
  },

  playEpisode: (data, options) => {
    const { player } = get();
    if (player.isPlaying && player.currentEpisodeId !== data.id) {
      set({
        player: {
          ...player,
          pendingEpisode: data,
          pendingSeek: options?.seekTo || null,
          showPlayerConfirmation: true,
        },
      });
      return;
    }
    set({
      player: {
        ...player,
        currentEpisodeId: data.id,
        isPlaying: true,
        isPlayerVisible: true,
        currentEpisodeData: data,
        seekRequest: options?.seekTo ?? null,
        pendingEpisode: null,
        pendingSeek: null,
        showPlayerConfirmation: false,
      },
    });
    playerBroadcast.broadcastPlayerOpen(data);
    if (options?.seekTo !== undefined) {
      playerBroadcast.broadcastSeekRequest(options.seekTo);
    }
  },

  confirmPlay: () =>
    set((state) => {
      const { pendingEpisode, pendingSeek } = state.player;
      if (!pendingEpisode) return state;
      return {
        player: {
          ...state.player,
          currentEpisodeId: pendingEpisode.id,
          isPlaying: true,
          isPlayerVisible: true,
          currentEpisodeData: pendingEpisode,
          seekRequest: pendingSeek,
          pendingEpisode: null,
          pendingSeek: null,
          showPlayerConfirmation: false,
        },
      };
    }),

  cancelPlay: () =>
    set((state) => ({
      player: {
        ...state.player,
        pendingEpisode: null,
        pendingSeek: null,
        showPlayerConfirmation: false,
      },
    })),

  closePlayerConfirmation: () =>
    set((state) => ({
      player: {
        ...state.player,
        pendingEpisode: null,
        pendingSeek: null,
        showPlayerConfirmation: false,
      },
    })),

  requestSeek: (seconds) => {
    set((state) => ({
      player: { ...state.player, seekRequest: seconds },
    }));
    playerBroadcast.broadcastSeekRequest(seconds);
  },

  clearSeekRequest: () =>
    set((state) => ({
      player: { ...state.player, seekRequest: null },
    })),

  closePlayer: () => {
    set((state) => ({
      player: {
        ...state.player,
        isPlaying: false,
        isPlayerVisible: false,
        currentEpisodeData: null,
        seekRequest: null,
      },
    }));
    playerBroadcast.broadcastPlayerClose();
  },
}));

// Cross-tab broadcast listener
const handleBroadcastMessage = (message: PlayerBroadcastMessage) => {
  const { type, payload } = message;
  switch (type) {
    case 'PLAYER_OPEN':
    case 'EPISODE_CHANGE':
      if (payload?.episodeData) {
        usePlayerStore.setState((state) => ({
          player: {
            ...state.player,
            currentEpisodeId: payload.episodeData!.id,
            isPlaying: true,
            isPlayerVisible: true,
            currentEpisodeData: payload.episodeData!,
            seekRequest: null,
            pendingEpisode: null,
            pendingSeek: null,
            showPlayerConfirmation: false,
          },
        }));
      }
      break;
    case 'PLAYER_CLOSE':
      usePlayerStore.setState((state) => ({
        player: {
          ...state.player,
          isPlaying: false,
          isPlayerVisible: false,
          currentEpisodeData: null,
          seekRequest: null,
        },
      }));
      break;
    case 'SEEK_REQUEST':
      if (payload?.seekTo !== undefined) {
        usePlayerStore.setState((state) => ({
          player: { ...state.player, seekRequest: payload.seekTo! },
        }));
      }
      break;
  }
};

playerBroadcast.addListener(handleBroadcastMessage);
