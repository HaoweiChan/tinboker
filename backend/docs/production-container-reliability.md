# Production Container Reliability

> **⚠️ Historical (2026-02-02) — superseded.** This report describes the original
> per-environment layout (separate `tinboker-{prod,staging,dev}.service` units running
> `docker-compose.{env}.yml`). The VPS now runs all three environments from a single
> `docker-compose.multi.yml` via one `tinboker.service`. For the current setup see
> [`docs/infra-runbook.md`](../../docs/infra-runbook.md) and
> [`backend/deploy/systemd/tinboker.service`](../deploy/systemd/tinboker.service).

Implementation report for ensuring TinBoker backend containers are highly available and automatically recover from failures.

## Implementation Date

2026-02-02

## Problem Statement

On 2026-02-02, the production API (`api.tinboker.com`) was down because the `tinboker-backend-prod` container was not running. Only staging and dev containers were active, causing:
- 502 errors from Cloudflare/Caddy
- Website falling back to mock data
- No automatic recovery mechanism

## Implemented Solutions

### 1. Systemd Services (Boot-time Auto-start)

Systemd service files ensure all containers start automatically when the VPS boots or restarts.

**Files Created:**
- `deploy/systemd/tinboker-prod.service`
- `deploy/systemd/tinboker-staging.service`
- `deploy/systemd/tinboker-dev.service`
- `deploy/setup-systemd.sh`

**Installation:**
```bash
cd /app
./deploy/setup-systemd.sh
```

**Service Status:**
```bash
systemctl status tinboker-prod
systemctl status tinboker-staging
systemctl status tinboker-dev
```

**Benefits:**
- Containers start automatically on VPS reboot
- Logs integrated with `journalctl`
- Standard Linux service management

### 2. GitHub Actions Health Check (Auto-recovery)

A scheduled GitHub Actions workflow checks API health every 10 minutes and restarts unhealthy containers.

**Workflow:** `.github/workflows/health-check.yml`

**Features:**
- Checks all three environments (prod, staging, dev)
- Restarts unhealthy containers via SSH
- Generates summary report
- Runs every 10 minutes

**Endpoints Monitored:**
- `https://api.tinboker.com/health`
- `https://staging-api.tinboker.com/health`
- `https://dev-api.tinboker.com/health`

### 3. UptimeRobot Monitoring (External Alerts)

External monitoring service provides alerts and uptime tracking.

**Configuration:**
- Monitor: HTTP check on `https://api.tinboker.com/health`
- Check interval: 5 minutes
- Alerts: Email notifications on downtime

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         VPS Boot                            │
│                            │                                │
│                            ▼                                │
│   ┌──────────────────────────────────────────────────────┐ │
│   │              Systemd Services                        │ │
│   │  tinboker-prod.service                             │ │
│   │  tinboker-staging.service                          │ │
│   │  tinboker-dev.service                              │ │
│   └──────────────────────────────────────────────────────┘ │
│                            │                                │
│                            ▼                                │
│   ┌──────────────────────────────────────────────────────┐ │
│   │          Docker Containers Running                   │ │
│   │  • tinboker-backend-prod (port 8000)               │ │
│   │  • tinboker-backend-staging (port 8002)            │ │
│   │  • tinboker-backend-dev (port 8001)                │ │
│   │  • tinboker-redis                                  │ │
│   │  • tinboker-netdata                                │ │
│   └──────────────────────────────────────────────────────┘ │
│                            ▲                                │
│                            │                                │
│   ┌────────────────────────┴───────────────────────────┐   │
│   │                                                     │   │
│   │  GitHub Actions         UptimeRobot                │   │
│   │  (every 10 mins)        (every 5 mins)             │   │
│   │  Auto-restart           Alerts                      │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Recovery Scenarios

| Scenario | Recovery Method | Recovery Time |
|----------|-----------------|---------------|
| VPS reboot | Systemd auto-start | Immediate |
| Container crash | Docker restart policy | Seconds |
| Process hang | GitHub Actions | ≤ 10 minutes |
| Unknown failure | GitHub Actions | ≤ 10 minutes |

## Quick Recovery Commands

If manual intervention is needed:

```bash
# SSH to VPS
ssh root@152.53.136.182

# Check container status
docker ps -a | grep tinboker

# Start production stack
cd /app
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check logs
docker logs tinboker-backend-prod --tail=50

# Verify health
curl http://localhost:8000/health
```

## Files Reference

| File | Purpose |
|------|---------|
| `deploy/systemd/tinboker-prod.service` | Production systemd service |
| `deploy/systemd/tinboker-staging.service` | Staging systemd service |
| `deploy/systemd/tinboker-dev.service` | Development systemd service |
| `deploy/setup-systemd.sh` | Service installation script |
| `.github/workflows/health-check.yml` | Automated health check workflow |

## Related PRs

- PR #100: `hotfix/production-reliability` - Added systemd services and health check workflow
