import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

export interface AppNotification {
  id: string;
  user_id: string;
  type: 'new_episode' | 'stock_mention' | 'topic_mention' | 'price_alert';
  title: string;
  body: string;
  data: {
    podcast_name?: string;
    episode_id?: string;
    ticker?: string;
    tag?: string;
    alert_type?: string;
    current_price?: number;
    threshold?: number;
  };
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: AppNotification[];
  total: number;
  has_more: boolean;
}

export const notificationsApi = {
  /**
   * Get user's notifications with pagination
   */
  getNotifications: async (limit = 50, offset = 0): Promise<NotificationListResponse> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');

    const response = await apiClient.get<NotificationListResponse>(
      `/api/notifications?limit=${limit}&offset=${offset}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  /**
   * Get count of unread notifications
   */
  getUnreadCount: async (): Promise<number> => {
    const token = useAppStore.getState().token;
    if (!token) return 0;

    try {
      const response = await apiClient.get<{ unread_count: number }>(
        '/api/notifications/unread-count',
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data.unread_count;
    } catch {
      return 0;
    }
  },

  /**
   * Mark a notification as read
   */
  markAsRead: async (notificationId: string): Promise<{ id: string; is_read: boolean }> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');

    const response = await apiClient.post<{ id: string; is_read: boolean }>(
      `/api/notifications/${notificationId}/read`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  /**
   * Mark all notifications as read
   */
  markAllAsRead: async (): Promise<{ updated_count: number }> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');

    const response = await apiClient.post<{ updated_count: number }>(
      '/api/notifications/read-all',
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  /**
   * Delete a notification
   */
  deleteNotification: async (notificationId: string): Promise<void> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');

    await apiClient.delete(
      `/api/notifications/${notificationId}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
  },
};
