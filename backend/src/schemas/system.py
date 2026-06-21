"""Pydantic schemas for system status API responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status for a single service."""

    status: Literal["healthy", "degraded", "unhealthy"]
    message: str | None = None


class BackendStatus(BaseModel):
    """Backend service status."""

    status: Literal["healthy", "degraded", "unhealthy"]
    uptime_seconds: float
    version: str = "0.4.14"  # fallback only; the live value comes from settings.api_version


class RedisStatus(BaseModel):
    """Redis connection status."""

    status: Literal["healthy", "unhealthy"]
    connected: bool
    memory_mb: float | None = None
    message: str | None = None


class PostgresStatus(BaseModel):
    """PostgreSQL connection pool status."""

    status: Literal["healthy", "degraded", "unhealthy"]
    connected: bool
    pool_size: int | None = None
    active_connections: int | None = None
    idle_connections: int | None = None
    message: str | None = None


class SystemMetrics(BaseModel):
    """VPS system metrics (basic, more detailed in Netdata)."""

    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None


class SystemStatusResponse(BaseModel):
    """Complete system status response."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, ServiceHealth] = Field(
        default_factory=dict,
        description="Summary health of each service",
    )
    backend: BackendStatus
    redis: RedisStatus
    postgres: PostgresStatus
    system: SystemMetrics | None = None


class HealthCheckResponse(BaseModel):
    """Enhanced health check response for Docker healthcheck."""

    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: bool
    redis: bool
    uptime_seconds: float
