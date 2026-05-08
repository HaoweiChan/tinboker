# AGENTS.md - TinBoker Backend

This file contains guidelines for AI coding agents working on this codebase.

## Project Overview

FastAPI-based backend for a stock portfolio management application with graph visualization.
Features stock data from Massive/FinMind APIs, Redis caching, WebSocket real-time updates,
and Firestore for podcast data.

## Tech Stack

- **Language**: Python 3.12+
- **Framework**: FastAPI 0.104.1
- **Data Validation**: Pydantic 2.5.0
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Caching**: Redis with hiredis
- **Package Manager**: uv (preferred) or pip
- **Testing**: pytest with pytest-asyncio

## Build & Run Commands

```bash
# Install dependencies (preferred)
uv sync
# or
pip install -r requirements.txt

# Run development server (uses port from .env, default 5174)
python -m src.main

# Run with uvicorn directly
uvicorn src.main:app --reload --host 0.0.0.0 --port 5174

# Start Redis (required for caching)
docker compose up -d redis
```

## Testing Commands

```bash
# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/unit/test_stock_service.py -v

# Run a single test function
pytest tests/unit/test_stock_service.py::TestStockService::test_get_stock_info_from_db -v

# Run by marker
pytest -m asyncio -v        # async tests
pytest -m integration -v    # integration tests
pytest -m slow -v           # slow tests

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v
```

## Project Structure

```
src/
  main.py              # FastAPI app entry point
  config.py            # Settings via pydantic-settings
  config_loader.py     # GCP Secret Manager loader
  cache/               # Redis client and cache config
  database/            # SQLite/PostgreSQL DB layer
  models/              # Pydantic models (stock.py, graph.py, news.py, etc.)
  routers/             # API endpoints (stock.py, graph.py, podcast.py, etc.)
  services/            # Business logic (stock.py, massive_service.py, etc.)
  schemas/             # Request/response schemas
  utils/               # Helpers (auth.py, timeframe.py)
  workers/             # Background workers
tests/
  conftest.py          # Pytest fixtures
  unit/                # Unit tests
  integration/         # Integration tests
  performance/         # Performance tests
```

## Code Style Guidelines

### Imports

Order imports as: stdlib, third-party, local. Group with blank lines:

```python
from datetime import datetime
from typing import Optional, List, Dict, Any
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.stock import StockService
from src.models.stock import CompanyDetail
from src.cache.redis_client import cache_get, cache_set
```

### Type Hints

Always use type hints for function signatures:

```python
def get_stock_info(self, ticker: str) -> Optional[CompanyDetail]:
    """Get stock information"""
    ...

async def get_sorted_stocks_async(
    self, sort_by: str = "ticker", limit: int = 50
) -> List[Dict[str, Any]]:
    """Get sorted stocks list with caching"""
    ...
```

### Pydantic Models

Use Pydantic v2 style with Field descriptions and ConfigDict:

```python
from pydantic import BaseModel, Field, ConfigDict

class ChartDataPoint(BaseModel):
    """Single OHLCV data point for stock chart"""
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    price: float = Field(..., description="Closing price")
    date: str = Field(..., description="ISO date string (YYYY-MM-DD)")
    volume: int = Field(..., description="Trading volume")

class CompanyDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    ticker: str = Field(..., description="Stock ticker symbol")
    changePercent: float = Field(..., alias="changePercent")
```

### Docstrings

Use triple-quoted docstrings with Args/Returns sections:

```python
def collect_stock_data(self, ticker: str, timeframe: Optional[str] = None) -> Optional[Stock]:
    """
    Collect stock data from external API
    
    Args:
        ticker: Stock ticker symbol
        timeframe: Optional timeframe filter (1H, 1D, 1W, 1M, etc.)
        
    Returns:
        Stock object or None if not found
    """
```

### Async Patterns

Provide both sync and async versions when needed. Use `run_in_executor` for blocking calls:

```python
async def get_stock_info_async(self, ticker: str) -> Optional[CompanyDetail]:
    """Async version with caching"""
    cached = await cache_get(cache_key)
    if cached:
        return CompanyDetail(**json.loads(cached))
    
    # Offload blocking call to thread pool
    loop = asyncio.get_event_loop()
    stock_data = await loop.run_in_executor(
        None,
        lambda: self.data_collection_service.collect_stock_data(ticker)
    )
    ...
```

### Error Handling

Use HTTPException for API errors. Log warnings/errors appropriately:

```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

@router.get("/{ticker}")
async def get_stock(ticker: str):
    stock = await stock_service.get_stock_info_async(ticker.upper())
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
    return stock
```

### Naming Conventions

- **Files**: snake_case (`stock_service.py`, `redis_client.py`)
- **Classes**: PascalCase (`StockService`, `CompanyDetail`)
- **Functions/Methods**: snake_case (`get_stock_info`, `cache_get`)
- **Constants**: UPPER_SNAKE_CASE (`CACHE_TTL`, `API_VERSION`)
- **Variables**: snake_case (`stock_data`, `cache_key`)

### Router Patterns

```python
router = APIRouter(prefix="/api/stocks", tags=["stocks"])

@router.get("", response_model=List[dict])
async def get_sorted_stocks(
    sort_by: str = Query(default="ticker", description="Sort field"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    """Get sorted stocks list"""
    return await stock_service.get_sorted_stocks_async(sort_by=sort_by, limit=limit)
```

### Testing Patterns

Use pytest fixtures, mock external services:

```python
import pytest
from unittest.mock import Mock, patch

class TestStockService:
    def test_get_stock_info(self, test_db):
        """Test getting stock info from database"""
        service = StockService()
        stock = service.get_stock_info("TEST")
        assert stock is not None
        assert stock.ticker == "TEST"
    
    @patch('src.services.stock.DataCollectionService')
    def test_external_fallback(self, mock_service, test_db):
        """Test fallback to external API"""
        mock_service.return_value.collect_stock_data.return_value = Mock(...)
        ...
```

### Configuration

Use pydantic-settings for environment configuration:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    finmind_api_key: Optional[str] = None
    port: int = 5174
    environment: str = "development"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )
```

### Caching Pattern

```python
cache_key = f"stock:{ticker.upper()}:info"
cached = await cache_get(cache_key)
if cached:
    return json.loads(cached)

# Fetch fresh data
result = await fetch_data()

# Store in cache
await cache_set(cache_key, json.dumps(result), CACHE_TTL["stock_info"])
return result
```

## Important Files

- `src/config.py` - All configuration and environment variables
- `src/main.py` - FastAPI app initialization and middleware
- `tests/conftest.py` - Shared pytest fixtures
- `pytest.ini` - Test configuration and markers
- `pyproject.toml` - Project dependencies (for uv)
- `requirements.txt` - Project dependencies (for pip)

## Environment Variables

Required in `.env`:
- `MASSIVE_API_KEY` - Massive API key for US stocks
- `FINMIND_API_KEY` - FinMind API key for Taiwan stocks
- `REDIS_URL` - Redis connection string (optional, caching disabled without it)
- `PORT` - Server port (default: 5174)
- `ENVIRONMENT` - development/staging/production

## Deployment Rules

**NEVER deploy code directly to servers via SSH/rsync.**

All code changes must follow the Git workflow:
1. Make changes locally
2. Commit to appropriate branch (feat/, fix/, etc.)
3. Push to GitHub
4. Create PR to `develop` branch
5. Let CI/CD pipeline handle deployment

### Forbidden Commands (for deployment):
- `rsync ... root@<server>:/app/` - Direct code sync
- `scp ... root@<server>:/app/` - Direct file copy  
- `ssh root@<server> "cd /app && docker compose up --build"` - Remote rebuild

### Allowed Server Commands:
- Health checks: `curl https://api.tinboker.com/health`
- Log inspection: `ssh root@... "docker logs tinboker-backend-prod --tail=50"`
- Status checks: `ssh root@... "docker ps"`
- Environment setup: Initial `.env` configuration, service account key deployment
- **Emergency debugging only**: Manual deployment acceptable during critical issues, but must be followed by proper Git commits

### Git Workflow
- Feature branches: `feat/<feature-name>` from `develop`
- Bug fixes: `fix/<bug-name>` from `develop`  
- Hotfixes: `hotfix/<issue>` from `main`
- PRs require CI checks to pass before merge

### CI/CD Pipeline (GitHub Actions)

**On Pull Request:**
- Runs tests (`pytest`) and linter (`ruff`)
- Builds Docker image tagged as `pr-{number}`
- Pushes to `ghcr.io/haoweichan/tinboker-backend:pr-{number}`
- Comments on PR with test instructions

**On Merge to `develop` or `main`:**
1. Builds Docker image tagged with branch name
2. Pushes to `ghcr.io/haoweichan/tinboker-backend:{branch}`
3. SSHs to VPS, pulls new image, restarts container
4. Runs health check

**Required GitHub Secrets:**
- `VPS_HOST`: VPS IP address (152.53.136.182)
- `VPS_USER`: SSH username (root)
- `VPS_SSH_KEY`: SSH private key for VPS access
- `GITHUB_TOKEN`: Auto-provided for GHCR access

### PR and Deploy Workflow

**IMPORTANT: Backend changes must be PR'd and tested BEFORE frontend changes.**

#### Step-by-Step Process:

1. **Create Backend PR first** (if backend changes needed)
   - Branch: `feat/your-feature` from `develop`
   - CI builds image as `ghcr.io/haoweichan/tinboker-backend:pr-{N}`
   
2. **Deploy PR image to staging for testing:**
   ```bash
   ssh root@152.53.136.182 "
     cd /app && 
     docker pull ghcr.io/haoweichan/tinboker-backend:pr-{N} && 
     IMAGE_TAG=pr-{N} docker compose -f docker-compose.staging.yml up -d backend
   "
   ```

3. **Create Frontend PR** (if frontend changes needed)
   - Cloudflare Pages auto-creates preview URL
   - Preview URL uses staging backend (api.tinboker.com)
   
4. **Test using Cloudflare preview URL**
   - Access: `https://{branch}.tinboker-platform.pages.dev`
   - This connects to staging backend running your PR image

5. **Merge Backend PR** to `develop`
   - CI auto-deploys to staging (api.tinboker.com)
   
6. **Merge Frontend PR** to `develop`
   - Cloudflare auto-deploys to staging

7. **Promote to Production** (when ready)
   - Merge `develop` to `main` for both repos
   - CI auto-deploys to production
