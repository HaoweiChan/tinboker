import { apiClient } from './client';
import { AxiosError } from 'axios';

export interface AuthResponse {
  user: {
    id: string;
    google_id: string;
    email: string;
    name: string;
    avatar?: string;
    email_verified: boolean;
    created_at: string;
    updated_at: string;
    watchlist?: string[];
    podcast_subscriptions?: string[];
    episode_bookmarks?: string[];
    alerts?: string[];
    tag_subscriptions?: string[];
  };
  token: string;
  refresh_token?: string;
}

export const authApi = {
  verifyGoogleToken: async (data: { idToken?: string; accessToken?: string }): Promise<AuthResponse> => {
    try {
      const response = await apiClient.post<AuthResponse>(
        '/api/auth/google',
        data,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
      return response.data;
    } catch (error: any) {
      if (error.isAxiosError || error instanceof AxiosError) {
        const message = error.response?.data?.detail || error.message;
        throw new Error(`Authentication failed: ${message}`);
      }
      throw error;
    }
  },

  getCurrentUser: async (token: string): Promise<AuthResponse['user']> => {
    try {
      const response = await apiClient.get<AuthResponse['user']>(
        '/api/auth/me',
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      return response.data;
    } catch (error: any) {
      if (error.isAxiosError || error instanceof AxiosError) {
        const message = error.response?.data?.detail || error.message;
        throw new Error(`Failed to get user: ${message}`);
      }
      throw error;
    }
  },

  isAdmin: async (token: string): Promise<boolean> => {
    try {
      const response = await apiClient.get<{ is_admin: boolean }>('/api/auth/is-admin', {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.data.is_admin;
    } catch {
      return false;
    }
  },

  logout: async (): Promise<void> => {
    try {
      await apiClient.post('/api/auth/logout');
    } catch (error) {
      // Logout is handled client-side, so errors are non-critical
      console.warn('Logout request failed:', error);
    }
  },
};
