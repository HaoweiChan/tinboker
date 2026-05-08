"""
SQLAlchemy ORM models for the TinBoker database.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index, UniqueConstraint
from src.database.postgres import Base


class StockTranslation(Base):
    """
    Model for storing stock ticker translations.
    Supports multiple markets (US, TW, JP) with ZH-TW translations.
    """
    __tablename__ = "stock_translations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    name_en = Column(Text, nullable=True)
    name_zh_tw = Column(Text, nullable=True)
    translation_status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # "pending", "approved", "auto"
    last_updated_by = Column(String(100), nullable=True)
    last_updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "market", name="uq_ticker_market"),
        Index("idx_translations_ticker_market", "ticker", "market"),
    )

    def __repr__(self) -> str:
        return f"<StockTranslation(ticker='{self.ticker}', market='{self.market}', name_zh_tw='{self.name_zh_tw}')>"
