/**
 * PlayerBroadcast - Cross-tab player synchronization using BroadcastChannel API
 * 
 * Enables global player state to sync across all open browser tabs.
 * Uses BroadcastChannel API which is supported in all modern browsers.
 */

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

export type BroadcastMessageType =
  | 'PLAYER_OPEN'
  | 'PLAYER_CLOSE'
  | 'EPISODE_CHANGE'
  | 'SEEK_REQUEST'
  | 'STATE_SYNC';

export interface PlayerBroadcastMessage {
  type: BroadcastMessageType;
  payload?: {
    episodeData?: EpisodeData;
    seekTo?: number;
    timestamp?: number;
  };
}

export type PlayerBroadcastListener = (message: PlayerBroadcastMessage) => void;

class PlayerBroadcastService {
  private channel: BroadcastChannel | null = null;
  private listeners: Set<PlayerBroadcastListener> = new Set();
  private readonly channelName = 'tinboker-player';

  constructor() {
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel(this.channelName);
      this.channel.onmessage = (event) => {
        this.handleMessage(event.data);
      };
    } else {
      console.warn('BroadcastChannel API not supported in this browser');
    }
  }

  /**
   * Add a listener for broadcast messages
   */
  addListener(listener: PlayerBroadcastListener): void {
    this.listeners.add(listener);
  }

  /**
   * Remove a listener
   */
  removeListener(listener: PlayerBroadcastListener): void {
    this.listeners.delete(listener);
  }

  /**
   * Broadcast a message to all other tabs
   */
  broadcast(message: PlayerBroadcastMessage): void {
    if (!this.channel) {
      return;
    }

    try {
      this.channel.postMessage(message);
    } catch (error) {
      console.error('Failed to broadcast message:', error);
    }
  }

  /**
   * Broadcast player open event
   */
  broadcastPlayerOpen(episodeData: EpisodeData): void {
    if (!episodeData) return;
    
    this.broadcast({
      type: 'PLAYER_OPEN',
      payload: {
        episodeData,
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Broadcast player close event
   */
  broadcastPlayerClose(): void {
    this.broadcast({
      type: 'PLAYER_CLOSE',
      payload: {
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Broadcast episode change event
   */
  broadcastEpisodeChange(episodeData: EpisodeData): void {
    if (!episodeData) return;
    
    this.broadcast({
      type: 'EPISODE_CHANGE',
      payload: {
        episodeData,
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Broadcast seek request
   */
  broadcastSeekRequest(seekTo: number): void {
    this.broadcast({
      type: 'SEEK_REQUEST',
      payload: {
        seekTo,
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Handle incoming broadcast message
   */
  private handleMessage(message: PlayerBroadcastMessage): void {
    // Notify all listeners
    this.listeners.forEach((listener) => {
      try {
        listener(message);
      } catch (error) {
        console.error('Error in broadcast listener:', error);
      }
    });
  }

  /**
   * Clean up resources
   */
  destroy(): void {
    if (this.channel) {
      this.channel.close();
      this.channel = null;
    }
    this.listeners.clear();
  }
}

// Singleton instance
export const playerBroadcast = new PlayerBroadcastService();
