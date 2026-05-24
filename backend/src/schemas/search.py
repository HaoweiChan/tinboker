from pydantic import BaseModel
from typing import List, Optional

class SearchResultItem(BaseModel):
    id: str
    type: str  # 'stock', 'podcast', 'episode', 'tag'
    title: str
    subtitle: Optional[str] = None
    icon_url: Optional[str] = None
    link: str
    market: Optional[str] = None  # 'TW' | 'US' | None — stocks only
    metadata: Optional[dict] = None

class SearchResponse(BaseModel):
    stocks: List[SearchResultItem] = []
    podcasts: List[SearchResultItem] = []
    episodes: List[SearchResultItem] = []
    tags: List[SearchResultItem] = []
