import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Bell, TrendingUp, Mic, AlertTriangle, X, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notificationsApi, type AppNotification } from '@/services/api/notifications';
import { useAppStore } from '@/store/useAppStore';
import { formatDate } from '@/lib/date';

interface DisplayNotification {
  id: string;
  type: 'new_episode' | 'stock_mention' | 'price_alert';
  title: string;
  description: string;
  time: string;
  isRead: boolean;
  data: AppNotification['data'];
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return '剛剛';
  if (diffMins < 60) return `${diffMins} 分鐘前`;
  if (diffHours < 24) return `${diffHours} 小時前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return formatDate(date);
}

function mapToDisplay(n: AppNotification): DisplayNotification {
  return {
    id: n.id,
    type: n.type,
    title: n.title,
    description: n.body,
    time: formatTimeAgo(n.created_at),
    isRead: n.is_read,
    data: n.data,
  };
}

export const NotificationDropdown: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<DisplayNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const token = useAppStore((state) => state.token);

  // Fetch unread count periodically
  const fetchUnreadCount = useCallback(async () => {
    if (!token) {
      setUnreadCount(0);
      return;
    }
    const count = await notificationsApi.getUnreadCount();
    setUnreadCount(count);
  }, [token]);

  // Fetch notifications when dropdown opens
  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const response = await notificationsApi.getNotifications(50, 0);
      setNotifications(response.notifications.map(mapToDisplay));
      setUnreadCount(response.notifications.filter(n => !n.is_read).length);
      setHasFetched(true);
    } catch (error) {
      console.error('[NotificationDropdown] Failed to fetch notifications:', error);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  // Poll for unread count every 60 seconds
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 60000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  // Fetch notifications when dropdown opens
  useEffect(() => {
    if (isOpen && token && !hasFetched) {
      fetchNotifications();
    }
  }, [isOpen, token, hasFetched, fetchNotifications]);

  // Refresh when dropdown reopens
  useEffect(() => {
    if (isOpen && token) {
      fetchNotifications();
    }
  }, [isOpen, token, fetchNotifications]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNotificationClick = async (notification: DisplayNotification) => {
    // Mark as read
    if (!notification.isRead) {
      try {
        await notificationsApi.markAsRead(notification.id);
        setNotifications(prev =>
          prev.map(n => n.id === notification.id ? { ...n, isRead: true } : n)
        );
        setUnreadCount(prev => Math.max(0, prev - 1));
      } catch (error) {
        console.error('[NotificationDropdown] Failed to mark as read:', error);
      }
    }
    // Navigate based on type
    if (notification.data.ticker) {
      navigate(`/stock/${notification.data.ticker}`);
    } else if (notification.data.episode_id && notification.data.podcast_name) {
      navigate(`/podcaster/${encodeURIComponent(notification.data.podcast_name)}`);
    }
    setIsOpen(false);
  };

  const markAllAsRead = async () => {
    try {
      await notificationsApi.markAllAsRead();
      setNotifications(prev => prev.map(n => ({ ...n, isRead: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('[NotificationDropdown] Failed to mark all as read:', error);
    }
  };

  const clearNotification = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await notificationsApi.deleteNotification(id);
      setNotifications(prev => prev.filter(n => n.id !== id));
      const removed = notifications.find(n => n.id === id);
      if (removed && !removed.isRead) {
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
    } catch (error) {
      console.error('[NotificationDropdown] Failed to delete notification:', error);
    }
  };

  const getIcon = (type: DisplayNotification['type']) => {
    switch (type) {
      case 'new_episode':
        return <Mic size={16} className="text-accent-info" />;
      case 'stock_mention':
        return <TrendingUp size={16} className="text-blue-400" />;
      case 'price_alert':
        return <AlertTriangle size={16} className="text-red-400" />;
    }
  };

  // Don't render if not logged in
  if (!token) return null;

  return (
    <div className="relative" ref={menuRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="text-slate-400 hover:text-slate-900 dark:hover:text-slate-50 transition relative p-2"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 block h-2 w-2 rounded-full ring-2 ring-white dark:ring-slate-900 bg-red-500"></span>
        )}
      </button>
      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-xl overflow-hidden z-50">
          {/* Header */}
          <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-slate-900 dark:text-slate-50">通知</h3>
              {unreadCount > 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400">{unreadCount} 則未讀</p>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-xs text-accent-info hover:text-accent-info dark:text-accent-info dark:hover:text-accent-info transition"
              >
                全部標為已讀
              </button>
            )}
          </div>
          {/* Notifications List */}
          <div className="max-h-96 overflow-y-auto">
            {isLoading ? (
              <div className="p-8 text-center text-slate-500">
                <Loader2 size={32} className="mx-auto mb-2 animate-spin" />
                <p>載入中...</p>
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-8 text-center text-slate-500">
                <Bell size={32} className="mx-auto mb-2 opacity-50" />
                <p>暫無通知</p>
              </div>
            ) : (
              notifications.map(notification => (
                <button
                  key={notification.id}
                  onClick={() => handleNotificationClick(notification)}
                  className={`w-full p-4 flex items-start gap-3 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left border-b border-slate-100 dark:border-slate-700/50 last:border-0 ${
                    !notification.isRead ? 'bg-slate-50/50 dark:bg-slate-700/30' : ''
                  }`}
                >
                  <div className="mt-0.5 p-2 rounded-lg bg-slate-100 dark:bg-slate-700/50">
                    {getIcon(notification.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <p className={`font-medium text-sm ${notification.isRead ? 'text-slate-600 dark:text-slate-300' : 'text-slate-900 dark:text-slate-50'}`}>
                        {notification.title}
                      </p>
                      <button
                        onClick={(e) => clearNotification(notification.id, e)}
                        className="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">{notification.description}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{notification.time}</p>
                  </div>
                  {!notification.isRead && (
                    <div className="w-2 h-2 rounded-full bg-accent-info dark:bg-accent-info shrink-0 mt-2"></div>
                  )}
                </button>
              ))
            )}
          </div>
          {/* Footer */}
          {notifications.length > 0 && (
            <div className="p-3 border-t border-slate-200 dark:border-slate-700">
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/settings');
                }}
                className="w-full text-center text-sm text-slate-500 hover:text-accent-info dark:text-slate-400 dark:hover:text-accent-info transition"
              >
                通知設定
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationDropdown;
