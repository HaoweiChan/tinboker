#!/bin/bash
set -u

# --- Configuration ---
REDIS_PORT=6380
CONTAINER_NAME="tinboker-redis"
IMAGE="redis:7-alpine"
# Generate a random password or use existing one if you prefer (here we generate new for security)
REDIS_PASSWORD=$(openssl rand -hex 16)

echo "=== Remote Redis Docker Setup ==="

# 1. Stop Native Redis (if running)
echo "[1] Stopping native Redis service (to free up ports/resources)..."
if sudo systemctl is-active --quiet redis-server; then
    sudo systemctl stop redis-server
    sudo systemctl disable redis-server
    echo "    Stopped and disabled native redis-server."
else
    echo "    Native redis-server service not active."
fi

# Force kill in case it was started manually (direct execution)
echo "    Ensuring no rogue redis-server processes..."
sudo pkill -f redis-server || true

# 2. Check/Install Docker
echo "[2] Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "    Docker not found. Installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    # Add user to docker group to avoid sudo for docker commands
    sudo usermod -aG docker $USER
    echo "    Docker installed. You may need to logout/login for group changes to take effect."
    echo "    Retrying with sudo for now..."
    DOCKER_CMD="sudo docker"
else
    DOCKER_CMD="docker"
    # Check permission
    if ! docker ps &> /dev/null; then
        DOCKER_CMD="sudo docker"
    fi
fi

# 3. Stop/Remove Existing Container
echo "[3] Cleaning up old container..."
$DOCKER_CMD rm -f $CONTAINER_NAME 2>/dev/null || true

# 4. Run New Container
echo "[4] Starting Redis Container ($IMAGE)..."
# We map host:6380 -> container:6379
# We use --restart always
$DOCKER_CMD run -d \
    --name $CONTAINER_NAME \
    --restart always \
    -p $REDIS_PORT:6379 \
    $IMAGE \
    redis-server --requirepass "$REDIS_PASSWORD" --appendonly yes

# 5. Output Info
IP_ADDRESS=$(tailscale ip -4 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "======================================================="
echo "✅ Redis Docker Running!"
echo "======================================================="
echo "Host:     $IP_ADDRESS"
echo "Port:     $REDIS_PORT"
echo "Password: $REDIS_PASSWORD"
echo "URL:      redis://:$REDIS_PASSWORD@$IP_ADDRESS:$REDIS_PORT/0"
echo "======================================================="
echo ""
echo "👉 Update your local .env with the URL above."
