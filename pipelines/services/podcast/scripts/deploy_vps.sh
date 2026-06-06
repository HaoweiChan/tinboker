#!/bin/bash
# Deploy the podcast API + knowledge-wiki Postgres to the Netcup VPS.
# Usage: ssh root@152.53.136.182 'bash -s' < services/podcast/scripts/deploy_vps.sh
# Or run directly on the VPS after cloning the repo.

set -e

MONOREPO_DIR="/root/tinboker"
REPO_DIR="$MONOREPO_DIR/pipelines"
PODCAST_DIR="$REPO_DIR/services/podcast"
SA_FILE="$PODCAST_DIR/gcp-service-account.json"

echo "=== Podcast API VPS Deployment ==="

# 1. Clone or pull the monorepo
if [ -d "$MONOREPO_DIR/.git" ]; then
    echo "→ Pulling latest changes..."
    cd "$MONOREPO_DIR" && git pull --ff-only
else
    echo "→ Cloning repository..."
    git clone https://github.com/HaoweiChan/tinboker.git "$MONOREPO_DIR"
fi
cd "$REPO_DIR"

# 2. Install uv if missing, then sync the podcast package (uv workspace)
if ! command -v uv >/dev/null 2>&1; then
    echo "→ Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
echo "→ Syncing dependencies (uv sync — podcast + news packages)..."
uv sync --package tinboker-podcast
uv sync --package tinboker-news

# 3. GCP credentials for ADC (Secret Manager, Firestore, GCS)
if [ ! -f "$SA_FILE" ]; then
    if [ -f "/root/gcp-sa-backup.json" ]; then
        cp /root/gcp-sa-backup.json "$SA_FILE"
        chmod 600 "$SA_FILE"
        echo "→ Copied GCP service account from backup"
    else
        echo "ERROR: No GCP service account found!"
        echo "  Place it at $SA_FILE or /root/gcp-sa-backup.json"
        exit 1
    fi
fi

# 4. Postgres for the knowledge wiki (bare-metal, localhost only)
if ! command -v pg_isready >/dev/null 2>&1 && ! dpkg -s postgresql >/dev/null 2>&1; then
    echo "→ Installing Postgres..."
    apt-get update -qq && apt-get install -y -qq postgresql
fi
systemctl enable --now postgresql || true
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='tinboker_wiki'" | grep -q 1; then
    echo "→ Creating tinboker_wiki database..."
    echo "  NOTE: set a real password and the WIKI_DATABASE_URL secret — see docs/MIGRATION.md Part 7."
    sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tinboker') THEN
    CREATE ROLE tinboker WITH LOGIN PASSWORD 'CHANGE_ME';
  END IF;
END $$;
CREATE DATABASE tinboker_wiki OWNER tinboker;
SQL
fi

# 5. Apply the wiki schema (idempotent). Requires WIKI_DATABASE_URL — either exported here,
#    or pulled from Secret Manager by the script's bootstrap fallback (see wiki_migrate.sh).
echo "→ Applying wiki schema (wiki_migrate.sh)..."
bash "$PODCAST_DIR/scripts/wiki_migrate.sh" || echo "  ⚠ wiki migrate skipped — set the WIKI_DATABASE_URL secret (docs/MIGRATION.md Part 7)"

# 6. Install / refresh the systemd service
echo "→ Installing systemd service..."
cat > /etc/systemd/system/podcast-api.service << 'EOF'
[Unit]
Description=Tinboker Podcast API (LangGraph Pipeline + Wiki API)
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/root/tinboker/pipelines/services/podcast
ExecStart=/root/tinboker/pipelines/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8003
Restart=always
RestartSec=5
Environment=PORT=8003
Environment=GOOGLE_APPLICATION_CREDENTIALS=/root/tinboker/pipelines/services/podcast/gcp-service-account.json

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable podcast-api
systemctl restart podcast-api

# 6b. Install / refresh the news-ingest timer (oneshot service + 6h timer)
echo "→ Installing tinboker-news timer..."
chmod +x "$REPO_DIR/services/news/scripts/run_news.sh"
cp "$REPO_DIR/services/news/deploy/tinboker-news.service" /etc/systemd/system/tinboker-news.service
cp "$REPO_DIR/services/news/deploy/tinboker-news.timer" /etc/systemd/system/tinboker-news.timer
systemctl daemon-reload
systemctl enable --now tinboker-news.timer

echo "→ Waiting for service to start..."
sleep 3

# 7. Health checks
if curl -sf http://localhost:8003/health > /dev/null 2>&1; then
    echo "✓ Podcast API is healthy on port 8003"
else
    echo "✗ Health check failed. Check: journalctl -u podcast-api -n 50"
    systemctl status podcast-api --no-pager
    exit 1
fi
curl -s http://localhost:8003/api/wiki/health || true
echo ""

echo "=== Deployment complete ==="
echo "  Service:  systemctl status podcast-api"
echo "  Logs:     journalctl -u podcast-api -f"
echo "  Health:   curl http://localhost:8003/health"
echo "  Wiki:     curl http://localhost:8003/api/wiki/health"
echo "  Wiki DB:  see docs/MIGRATION.md Part 7 (create WIKI_DATABASE_URL secret + backfill)"
