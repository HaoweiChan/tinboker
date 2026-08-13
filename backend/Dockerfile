# TinBoker Backend Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    # cairo rasterises the syndication cover (services/og_image.py). Social crawlers
    # ignore an SVG og:image, so the PNG is the one that actually shows up as a card.
    libcairo2 \
    # ~100MB, and not optional: cairosvg does no font fallback, so without a CJK face
    # every Chinese glyph in a cover renders as a tofu box. Swap for fonts-wqy-zenhei
    # (~15MB) if image size ever matters more than the typography does.
    fonts-noto-cjk \
    # Episode titles carry emoji ("EP684 | 🔦") and no CJK face has those glyphs. cairo
    # renders them in full colour once the family is named — see og_image._runs.
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create data directory for SQLite (if needed)
# Note: GCP service account key is mounted at runtime via docker-compose
RUN mkdir -p data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
