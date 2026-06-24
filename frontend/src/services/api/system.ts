/**
 * API client for system status endpoints.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type { SystemStatusResponse } from '@/types/system';

function adminAuthConfig() {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    return { headers: { Authorization: `Bearer ${token}` } };
}

/**
 * Get system status for admin dashboard.
 */
export async function getSystemStatus(): Promise<SystemStatusResponse> {
    const response = await apiClient.get<SystemStatusResponse>(
        '/api/admin/system/status',
        adminAuthConfig()
    );
    return response.data;
}

/**
 * Get the total number of registered users.
 */
export async function getUserCount(): Promise<number> {
    const response = await apiClient.get<{ count: number }>(
        '/api/admin/system/user-count',
        adminAuthConfig()
    );
    return response.data.count;
}
