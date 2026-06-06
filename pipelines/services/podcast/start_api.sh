#!/bin/bash
# Script to start the Podcast Downloader API server

# Default values
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8003}  # Avoid conflict with backend-staging on 8002

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --localhost-only)
            HOST="127.0.0.1"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--host HOST] [--port PORT] [--localhost-only]"
            echo "  --host HOST          Bind to specific host (default: 0.0.0.0)"
            echo "  --port PORT          Use specific port (default: 8003)"
            echo "  --localhost-only     Bind to localhost only (127.0.0.1)"
            exit 1
            ;;
    esac
done

# Activate virtual environment
cd "$(dirname "$0")"
source .venv/bin/activate

# Secrets are pulled from Google Secret Manager at process start
# (see src/secrets_bootstrap.py). Make sure ADC is configured:
#   - Local:  gcloud auth application-default login
#   - VPS:    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json

echo "Starting Podcast Downloader API server..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Access: http://$HOST:$PORT"
if [ "$HOST" = "0.0.0.0" ]; then
    echo "  Public IP: http://159.195.45.195:$PORT"
fi
echo ""

python -m uvicorn app:app --host "$HOST" --port "$PORT"
