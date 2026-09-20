#!/bin/bash
# Start whisper-server bound to this Mac's tailnet address.
#
# The bind address only exists while Tailscale is connected, and at login Tailscale
# usually comes up a few seconds after launchd fires this. Binding 0.0.0.0 would dodge
# the race but would also expose an unauthenticated transcription server to the whole
# LAN, so instead we wait for the address and let launchd's KeepAlive retry if it never
# arrives (the VPS falls back to Groq meanwhile).
set -euo pipefail

TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
MODEL="$HOME/models/whisper/ggml-large-v3-turbo.bin"
PORT=8910
THREADS=10

for _ in $(seq 1 60); do
  IP="$("$TS" ip -4 2>/dev/null | head -1 || true)"
  [ -n "${IP:-}" ] && break
  sleep 5
done

if [ -z "${IP:-}" ]; then
  echo "$(date -Iseconds) no tailnet address after 5 minutes; exiting so launchd retries" >&2
  exit 1
fi

echo "$(date -Iseconds) binding whisper-server to $IP:$PORT" >&2
exec /opt/homebrew/bin/whisper-server -m "$MODEL" --host "$IP" --port "$PORT" -t "$THREADS"
