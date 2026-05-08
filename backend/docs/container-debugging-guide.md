# Container Debugging Guide

A quick reference for diagnosing container crashes on the VPS.

## 1. Container Status & Logs

```bash
# See all containers (including stopped ones)
docker ps -a

# Check logs from crashed containers
docker logs tinboker-prod --tail 100
docker logs tinboker-staging --tail 100
docker logs tinboker-dev --tail 100

# Check why container exited
docker inspect tinboker-prod --format='{{.State.ExitCode}} {{.State.Error}}'
```

## 2. System Resources

```bash
# Check RAM usage
free -h

# Check if OOM killer terminated containers
dmesg | grep -i "oom\|out of memory" | tail -20

# Check disk space
df -h

# Check running processes by memory
ps aux --sort=-%mem | head -15
```

## 3. Docker Stats & Events

```bash
# Real-time container resource usage
docker stats --no-stream

# Recent Docker events (restarts, kills)
docker events --since 1h --until now | grep -E "die|kill|oom"
```

## 4. Systemd Service Logs

```bash
journalctl -u tinboker-prod --since "1 hour ago"
journalctl -u docker --since "1 hour ago"
```

## Common Causes

| Issue | How to Confirm |
|-------|---------------|
| **RAM exhaustion** | `dmesg \| grep -i oom` shows OOMKiller events |
| **Disk full** | `df -h` shows 100% on a partition |
| **Container error** | `docker logs` shows application crash |
| **Docker daemon issue** | `journalctl -u docker` shows errors |

## Quick Diagnostic Script

Run this one-liner to get a quick overview:

```bash
echo "=== RAM ===" && free -h && echo "\n=== Disk ===" && df -h / && echo "\n=== Containers ===" && docker ps -a && echo "\n=== OOM Events ===" && dmesg | grep -i oom | tail -5
```
