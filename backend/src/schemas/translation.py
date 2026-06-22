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
    aliases: Optional[List[str]] = Field(None, description="Alt names/symbols that resolve to this ticker")
    name_preference: Optional[Literal["auto", "zh_tw", "en"]] = Field(
        None, description="Display preference. 'en' forces English even when a zh name exists; "
                          "null leaves it unchanged (defaults to 'auto')."
    )


class TranslationCreate(TranslationBase):
    """Schema for creating a new translation."""
    translation_status: Literal["pending", "approved", "auto"] = "pending"


class TranslationUpdate(BaseModel):
    """Schema for updating an existing translation."""
    market: Optional[str] = Field(
        None, max_length=10,
        description="Market code (TW, US, KR, HK, JP). Lets an admin fix a misclassified row."
    )
    name_en: Optional[str] = None
    name_zh_tw: Optional[str] = None
    translation_status: Optional[Literal["pending", "approved", "auto", "unresolvable"]] = None
    brand_color: Optional[str] = Field(None, max_length=7)
    aliases: Optional[List[str]] = None
    name_preference: Optional[Literal["auto", "zh_tw", "en"]] = None


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
    aliases: Optional[List[str]] = None
    name_preference: Optional[str] = None

    class Config:
        from_attributes = True


class TranslationListResponse(BaseModel):
    """Schema for paginated translation list."""
    total: int
    page: int
    limit: int
    items: List[TranslationResponse]


class TranslationSearchItem(BaseModel):
    """A single read-only search/batch result, with a resolved display label.

    `has_zh_name` is computed (true only when `name_zh_tw` holds real CJK text, not an
    English fallback), and `display_name` already encodes the en-vs-zh choice so callers
    (e.g. the MCP server / summary agent) don't have to.
    """
    ticker: str
    market: str
    name_en: Optional[str] = None
    name_zh_tw: Optional[str] = None
    brand_color: Optional[str] = None
    aliases: Optional[List[str]] = None
    translation_status: str
    name_preference: str = Field(
        "auto", description="Display preference: 'auto' | 'zh_tw' | 'en'"
    )
    has_zh_name: bool = Field(
        ..., description="True when a real Chinese name is shown (CJK present and preference != 'en')"
    )
    display_name: str = Field(
        ..., description="Label to render: name_zh_tw when has_zh_name else name_en or ticker"
    )


class TranslationSearchResponse(BaseModel):
    """Read-only search/batch response."""
    query: Optional[str] = None
    total: int
    items: List[TranslationSearchItem]


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
