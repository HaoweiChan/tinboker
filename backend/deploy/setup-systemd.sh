#!/bin/bash
# Setup script for the TinBoker systemd service (auto-start on boot).
# Run this on the VPS. All three environments run from docker-compose.multi.yml,
# so there is a single unit (not one per env).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing TinBoker systemd service..."

# Remove any legacy per-env units from the pre-multi.yml layout.
for legacy in tinboker-prod tinboker-staging tinboker-dev; do
  if systemctl list-unit-files | grep -q "^${legacy}.service"; then
    echo "Removing legacy unit ${legacy}.service"
    systemctl disable --now "${legacy}.service" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/${legacy}.service"
  fi
done

cp "$SCRIPT_DIR/systemd/tinboker.service" "$SYSTEMD_DIR/"

systemctl daemon-reload
systemctl enable tinboker.service
systemctl start tinboker.service || true

echo ""
echo "=== Service Status ==="
systemctl status tinboker.service --no-pager || true

echo ""
echo "Done! The stack will now start automatically on boot."
echo ""
echo "Useful commands:"
echo "  systemctl status tinboker"
echo "  systemctl restart tinboker            # restarts the whole compose stack"
echo "  journalctl -u tinboker -f"
echo "  # Deploy/restart a single env (image tag from CI):"
echo "  cd /app/backend && PROD_IMAGE_TAG=main docker compose -f docker-compose.multi.yml up -d --no-deps backend-prod"
