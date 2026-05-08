#!/bin/bash
set -e

# Default Remote Host
REMOTE_HOST="willy@100.114.150.46"
CONTAINER_NAME="tinboker-redis"

# Export Redis Timeouts (Increased for remote connections)
export REDIS_CONNECT_TIMEOUT=30
export REDIS_SOCKET_TIMEOUT=30

echo "=== TinBoker Dev: Remote Redis Mode ==="
echo "    Configured Timeouts: Connect=${REDIS_CONNECT_TIMEOUT}s, Socket=${REDIS_SOCKET_TIMEOUT}s"

# Ensure CORS_ORIGINS includes the current frontend port (5174/5173)
# We use single quotes to wrap the JSON string to avoid shell expansion issues
export CORS_ORIGINS='["http://localhost:5173","http://localhost:5174","http://127.0.0.1:5173","http://127.0.0.1:5174"]'

# 1. Stop Local Docker Redis
echo "[1] Stopping local Docker services..."
# Check if docker-compose.yml exists in parent or current dir
if [ -f "docker-compose.yml" ]; then
    docker compose stop redis 2>/dev/null || true
    echo "    Local Redis stopped."
elif [ -f "../docker-compose.yml" ]; then
    (cd .. && docker compose stop redis 2>/dev/null || true)
    echo "    Local Redis stopped."
else
    echo "    ⚠️  docker-compose.yml not found, assuming local redis is handled elsewhere."
fi

# 2. Wake up Remote Redis (Ensure it's running)
echo "[2] Ensuring Remote Redis is running on $REMOTE_HOST..."
# We use ssh to start the container just in case it was stopped manually
ssh $REMOTE_HOST "docker start $CONTAINER_NAME" > /dev/null && echo "    Remote Redis is UP." || echo "    ⚠️  Could not start remote redis (might already be running or permissions issue)."

# 2.5 Pre-flight Connection Check
echo "[2.5] Testing Connectivity to Remote Redis..."
HOST_ONLY=$(echo $REMOTE_HOST | sed 's/.*@//')
# Check 6380 (from user errors) and 6379 (standard)
if nc -z -w 5 $HOST_ONLY 6380 2>/dev/null; then
    echo "    ✅ Connection to $HOST_ONLY:6380 successful."
elif nc -z -w 5 $HOST_ONLY 6379 2>/dev/null; then
    echo "    ✅ Connection to $HOST_ONLY:6379 successful."
else
    echo "    ⚠️  Warning: Could not connect to $HOST_ONLY on port 6380 or 6379 via TCP."
    echo "        This might be due to Tailscale latency or firewall rules."
fi

# 3. Run Local Backend
echo "[3] Starting Uvicorn..."

# Check and kill existing process on port 8000
if lsof -ti :8000 > /dev/null; then
    echo "    Port 8000 is busy. Killing existing process..."
    lsof -ti :8000 | xargs kill -9
fi

# Assuming we are in the project root or scripts folder
if [ -f "src/main.py" ]; then
    # We are in root
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --loop asyncio
elif [ -d "../src" ]; then
    # We are in scripts/, move up
    cd ..
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --loop asyncio
else
    echo "❌ Could not find src/main.py. Please run this from the project root."
    exit 1
fi
