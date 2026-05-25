/**
 * Admin Dashboard home page with system status overview.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Database, Server, Cpu, RefreshCw, AlertCircle } from 'lucide-react';
import { getSystemStatus } from '@/services/api/system';
import { StatusCard } from '@/components/admin/StatusCard';
import { NetdataEmbed } from '@/components/admin/NetdataEmbed';
import type { SystemStatusResponse } from '@/types/system';

export const AdminDashboardPage: React.FC = () => {
    const [status, setStatus] = useState<SystemStatusResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await getSystemStatus();
            setStatus(data);
            setLastUpdated(new Date());
        } catch (err: any) {
            setError(err.message || '無法取得系統狀態');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        // Auto-refresh every 30 seconds
        const interval = setInterval(fetchStatus, 30000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    const formatUptime = (seconds: number): string => {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        if (days > 0) return `${days}d ${hours}h ${minutes}m`;
        if (hours > 0) return `${hours}h ${minutes}m`;
        return `${minutes}m`;
    };

    const getStatusColor = (status: string): 'green' | 'yellow' | 'red' => {
        if (status === 'healthy') return 'green';
        if (status === 'degraded') return 'yellow';
        return 'red';
    };

    return (
        <div className="mx-auto max-w-7xl">
            {/* Header */}
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                        系統狀態
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        {lastUpdated
                            ? `更新時間：${lastUpdated.toLocaleTimeString()}`
                            : '載入中...'}
                    </p>
                </div>
                <button
                    onClick={fetchStatus}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    重新整理
                </button>
            </div>

            {/* Error message */}
            {error && (
                <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                    <AlertCircle className="h-5 w-5 flex-shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Status cards */}
            <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatusCard
                    title="後端服務"
                    icon={<Server className="h-5 w-5" />}
                    status={status?.backend.status || 'unknown'}
                    value={status ? formatUptime(status.backend.uptime_seconds) : '--'}
                    subtitle={status ? `版本 v${status.backend.version}` : '載入中...'}
                    color={status ? getStatusColor(status.backend.status) : 'yellow'}
                    loading={loading && !status}
                />
                <StatusCard
                    title="Redis"
                    icon={<Database className="h-5 w-5" />}
                    status={status?.redis.status || 'unknown'}
                    value={
                        status?.redis.connected
                            ? `${status.redis.memory_mb?.toFixed(1) || '?'} MB`
                            : '未連線'
                    }
                    subtitle={status?.redis.message || (status?.redis.connected ? '已連線' : '檢查中...')}
                    color={status ? getStatusColor(status.redis.status) : 'yellow'}
                    loading={loading && !status}
                />
                <StatusCard
                    title="PostgreSQL"
                    icon={<Database className="h-5 w-5" />}
                    status={status?.postgres.status || 'unknown'}
                    value={
                        status?.postgres.pool_size !== undefined
                            ? `${status.postgres.active_connections}/${status.postgres.pool_size}`
                            : status?.postgres.connected
                                ? '已連線'
                                : '未連線'
                    }
                    subtitle={
                        status?.postgres.message ||
                        (status?.postgres.idle_connections !== undefined
                            ? `閒置連線 ${status.postgres.idle_connections}`
                            : '檢查中...')
                    }
                    color={status ? getStatusColor(status.postgres.status) : 'yellow'}
                    loading={loading && !status}
                />
                <StatusCard
                    title="主機資源"
                    icon={<Cpu className="h-5 w-5" />}
                    status={status?.system ? 'healthy' : 'unknown'}
                    value={status?.system ? `CPU ${status.system.cpu_percent.toFixed(0)}%` : 'N/A'}
                    subtitle={
                        status?.system
                            ? `記憶體 ${status.system.memory_percent.toFixed(0)}% ｜ 磁碟 ${status.system.disk_percent.toFixed(0)}%`
                            : '未安裝 psutil'
                    }
                    color={
                        status?.system
                            ? status.system.cpu_percent > 80 || status.system.memory_percent > 90
                                ? 'red'
                                : status.system.cpu_percent > 60 || status.system.memory_percent > 80
                                    ? 'yellow'
                                    : 'green'
                            : 'yellow'
                    }
                    loading={loading && !status}
                />
            </div>

            {/* Netdata embed */}
            <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
                <div className="mb-4 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-gray-500 dark:text-gray-400" />
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                        Netdata 即時監控
                    </h2>
                </div>
                <NetdataEmbed />
            </div>
        </div>
    );
};
