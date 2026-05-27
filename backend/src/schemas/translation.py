"""
Pydantic schemas for stock translations.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class TranslationBase(BaseModel):
    """Base translation schema with common fields."""
    ticker: str = Field(..., max_length=20, description="Stock ticker symbol")
    market: str = Field(..., max_length=10, description="Market code (US, TW, JP)")
    name_en: Optional[str] = Field(None, description="English name")
    name_zh_tw: Optional[str] = Field(None, description="Chinese Traditional name")
    brand_color: Optional[str] = Field(None, max_length=7, description="Brand hex color e.g. '#1A2B3C'")


class TranslationCreate(TranslationBase):
    """Schema for creating a new translation."""
    translation_status: Literal["pending", "approved", "auto"] = "pending"


class TranslationUpdate(BaseModel):
    """Schema for updating an existing translation."""
    name_en: Optional[str] = None
    name_zh_tw: Optional[str] = None
    translation_status: Optional[Literal["pending", "approved", "auto"]] = None
    brand_color: Optional[str] = Field(None, max_length=7)


class TranslationResponse(TranslationBase):
    """Schema for translation response."""
    id: int
    translation_status: str
    last_updated_by: Optional[str] = None
    last_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranslationPublicResponse(BaseModel):
    """Schema for public translation lookup response."""
    ticker: str
    market: str
    name_en: Optional[str] = None
    name_zh_tw: Optional[str] = None
    brand_color: Optional[str] = None

    class Config:
        from_attributes = True


class TranslationListResponse(BaseModel):
    """Schema for paginated translation list."""
    total: int
    page: int
    limit: int
    items: List[TranslationResponse]


class BulkImportItem(TranslationBase):
    """Schema for a single item in bulk import."""
    translation_status: Literal["pending", "approved", "auto"] = "auto"


class BulkImportResponse(BaseModel):
    """Schema for bulk import response."""
    imported: int
    updated: int
    errors: List[str] = []


class MissingTranslation(BaseModel):
    """Schema for missing translation report."""
    ticker: str
    market: str
    name_en: Optional[str] = None


class MissingTranslationsResponse(BaseModel):
    """Schema for missing translations list."""
    total: int
    items: List[MissingTranslation]
