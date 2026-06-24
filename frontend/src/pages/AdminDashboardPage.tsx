/**
 * Admin Dashboard home page with system status overview.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Database, Server, Cpu, RefreshCw, AlertCircle, Users } from 'lucide-react';
import { getSystemStatus, getUserCount } from '@/services/api/system';
import { StatusCard } from '@/components/admin/StatusCard';
import { NetdataEmbed } from '@/components/admin/NetdataEmbed';
import type { SystemStatusResponse } from '@/types/system';

export const AdminDashboardPage: React.FC = () => {
    const [status, setStatus] = useState<SystemStatusResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [userCount, setUserCount] = useState<number | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await getSystemStatus();
            setStatus(data);
            setLastUpdated(new Date());
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch system status');
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

    // User count is server-cached (5 min) — fetch once on mount, not on the 30s poll.
    useEffect(() => {
        getUserCount().then(setUserCount).catch(() => setUserCount(null));
    }, []);

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
                    <h1 className="text-2xl font-bold text-foreground">
                        System Status
                    </h1>
                    <p className="text-base text-muted-foreground">
                        {lastUpdated
                            ? `Last updated: ${lastUpdated.toLocaleTimeString()}`
                            : 'Loading...'}
                    </p>
                </div>
                <button
                    onClick={fetchStatus}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted disabled:opacity-50"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Error message */}
            {error && (
                <div className="mb-6 flex items-center gap-2 rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
                    <AlertCircle className="h-5 w-5 flex-shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Status cards */}
            <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatusCard
                    title="Registered Users"
                    icon={<Users className="h-5 w-5" />}
                    status="healthy"
                    value={userCount != null ? userCount.toLocaleString() : '--'}
                    subtitle="會員總數"
                    color="green"
                    loading={userCount == null}
                />
                <StatusCard
                    title="Backend"
                    icon={<Server className="h-5 w-5" />}
                    status={status?.backend.status || 'unknown'}
                    value={status ? formatUptime(status.backend.uptime_seconds) : '--'}
                    subtitle={status ? `v${status.backend.version}` : 'Loading...'}
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
                            : 'Disconnected'
                    }
                    subtitle={status?.redis.message || (status?.redis.connected ? 'Connected' : 'Checking...')}
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
                                ? 'Connected'
                                : 'Disconnected'
                    }
                    subtitle={
                        status?.postgres.message ||
                        (status?.postgres.idle_connections !== undefined
                            ? `${status.postgres.idle_connections} idle`
                            : 'Checking...')
                    }
                    color={status ? getStatusColor(status.postgres.status) : 'yellow'}
                    loading={loading && !status}
                />
                <StatusCard
                    title="System"
                    icon={<Cpu className="h-5 w-5" />}
                    status={status?.system ? 'healthy' : 'unknown'}
                    value={status?.system ? `${status.system.cpu_percent.toFixed(0)}% CPU` : 'N/A'}
                    subtitle={
                        status?.system
                            ? `RAM: ${status.system.memory_percent.toFixed(0)}% | Disk: ${status.system.disk_percent.toFixed(0)}%`
                            : 'psutil not installed'
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
            <div className="rounded-lg border border-border bg-card p-4">
                <div className="mb-4 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-muted-foreground" />
                    <h2 className="text-xl font-semibold text-foreground">
                        Netdata Monitoring
                    </h2>
                </div>
                <NetdataEmbed />
            </div>
        </div>
    );
};
