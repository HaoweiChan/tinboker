"""
Additional schemas and models for backward compatibility
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# Re-export CompanyDetail from stock models
from src.models.stock import CompanyDetail as _CompanyDetail
CompanyDetail = _CompanyDetail


class StockMetadata(BaseModel):
    """Stock metadata model"""
    stock_id: str
    ticker: str
    stock_name: str
    industry_category: str = "Unknown"
    currency: str = "USD"


class StockMetadataCollection(BaseModel):
    """Collection of stock metadata"""
    stocks: List[StockMetadata] = Field(default_factory=list)
    
    def add(self, stock: StockMetadata):
        """Add stock to collection"""
        self.stocks.append(stock)
    
    def get_by_stock_id(self, stock_id: str) -> Optional[StockMetadata]:
        """Get stock by ID"""
        for stock in self.stocks:
            if stock.stock_id.upper() == stock_id.upper():
                return stock
        return None
    
    def get_all_stock_ids(self) -> List[str]:
        """Get all stock IDs"""
        return [stock.stock_id for stock in self.stocks]


class StockPriceRecord(BaseModel):
    """Stock price record"""
    date: str
    timestamp: Optional[int] = None
    Trading_Volume: int = 0
    Trading_money: float = 0.0
    open: float = 0.0
    max: float = 0.0
    min: float = 0.0
    close: float = 0.0
    spread: float = 0.0
    Trading_turnover: float = 0.0


class StockPriceHistory(BaseModel):
    """Stock price history"""
    day: List[StockPriceRecord] = Field(default_factory=list)
    
    def add_record(self, record: StockPriceRecord):
        """Add price record"""
        self.day.append(record)


class CompanyStats(BaseModel):
    """Company statistics"""
    volume: int = 0
    beta: float = 0.0
    volatility: float = 0.0


class Stock(BaseModel):
    """Stock model with full data"""
    stock_id: str
    metadata: StockMetadata
    stock_price_history: StockPriceHistory = Field(default_factory=StockPriceHistory)
    price: Optional[float] = None
    change: Optional[float] = None
    changePercent: Optional[float] = Field(None, alias="changePercent")
    marketCap: Optional[int] = Field(None, alias="marketCap")
    revenue: Optional[int] = None
    pe: Optional[float] = None
    dividendYield: Optional[float] = Field(None, alias="dividendYield")
    about: Optional[str] = None
    stats: Optional[CompanyStats] = None
    # Built from stored bars because the upstream failed: no details, maybe a stale tail.
    # Served so the chart isn't blank, never cached (StockService).
    from_stored_bars: bool = False

    class Config:
        populate_by_name = True


class ErrorResponse(BaseModel):
    """Error response model"""
    error: dict

