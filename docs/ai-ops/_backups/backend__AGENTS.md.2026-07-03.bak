# AGENTS.md — TinBoker Backend

Domain-specific guidelines for AI agents working in `backend/`. For project-wide rules
(git, deployment, environments, known bugs), see the root `CLAUDE.md`.

---

## Code Style

### Imports

Order: stdlib → third-party → local, separated by blank lines.

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

Always annotate function signatures:

```python
def get_stock_info(self, ticker: str) -> Optional[CompanyDetail]:
    ...

async def get_sorted_stocks_async(
    self, sort_by: str = "ticker", limit: int = 50
) -> List[Dict[str, Any]]:
    ...
```

### Pydantic Models

Use Pydantic v2 style with `ConfigDict`:

```python
from pydantic import BaseModel, Field, ConfigDict

class ChartDataPoint(BaseModel):
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    price: float = Field(..., description="Closing price")
    volume: int = Field(..., description="Trading volume")

class CompanyDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ticker: str = Field(..., description="Stock ticker symbol")
    changePercent: float = Field(..., alias="changePercent")
```

### Async Patterns

Use `run_in_executor` for blocking calls inside async endpoints:

```python
async def get_stock_info_async(self, ticker: str) -> Optional[CompanyDetail]:
    cached = await cache_get(cache_key)
    if cached:
        return CompanyDetail(**json.loads(cached))

    loop = asyncio.get_event_loop()
    stock_data = await loop.run_in_executor(
        None,
        lambda: self.data_collection_service.collect_stock_data(ticker)
    )
    ...
```

### Error Handling

```python
logger = logging.getLogger(__name__)

@router.get("/{ticker}")
async def get_stock(ticker: str):
    stock = await stock_service.get_stock_info_async(ticker.upper())
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
    return stock
```

### Router Pattern

```python
router = APIRouter(prefix="/api/stocks", tags=["stocks"])

@router.get("", response_model=List[dict])
async def get_sorted_stocks(
    sort_by: str = Query(default="ticker", description="Sort field"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results")
):
    return await stock_service.get_sorted_stocks_async(sort_by=sort_by, limit=limit)
```

### Caching Pattern

```python
cache_key = f"stock:{ticker.upper()}:info"
cached = await cache_get(cache_key)
if cached:
    return json.loads(cached)

result = await fetch_data()
await cache_set(cache_key, json.dumps(result), CACHE_TTL["stock_info"])
return result
```

### Testing Pattern

```python
class TestStockService:
    def test_get_stock_info(self, test_db):
        service = StockService()
        stock = service.get_stock_info("TEST")
        assert stock is not None
        assert stock.ticker == "TEST"

    @patch('src.services.stock.DataCollectionService')
    def test_external_fallback(self, mock_service, test_db):
        mock_service.return_value.collect_stock_data.return_value = Mock(...)
        ...
```

---

## Important Files

| File | Purpose |
|------|---------|
| `src/main.py` | FastAPI app entry point and lifespan |
| `src/config.py` | Settings via pydantic-settings + GCP Secret Manager |
| `src/config_loader.py` | Secret Manager loader |
| `tests/conftest.py` | Shared pytest fixtures |
| `pytest.ini` | Test configuration and markers |
| `pyproject.toml` | Dependencies (uv) |
