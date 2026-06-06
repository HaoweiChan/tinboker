from typing import List, Dict, Set
from src.schemas.search import SearchResultItem
import asyncio
import logging
from collections import defaultdict
import re

logger = logging.getLogger(__name__)

class SuggestionIndex:
    """
    In-memory optimized index for instant search suggestions.
    Uses token-based prefix indexing + scoring.
    """
    _instance = None
    _items: Dict[str, SearchResultItem]  # ID -> Item
    _index: Dict[str, Set[str]]          # Prefix -> Set of Item IDs (using Set for dedup)
    _keywords: Dict[str, List[str]]      # ID -> List of keywords (for scoring)
    _lock: asyncio.Lock
    _is_initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SuggestionIndex, cls).__new__(cls)
            cls._instance._items = {}
            cls._instance._index = defaultdict(set)
            cls._instance._keywords = defaultdict(list)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    def _tokenize(self, text: str) -> Set[str]:
        """Split text into tokens for indexing."""
        if not text:
            return set()
        # Split by whitespace and punctuation, keeping alphanumeric parts
        # Also handle Chinese characters as individual tokens? 
        # For mixed English/Chinese, user might type "台積" (prefix of "台積電")
        # Or "2330".
        # Simple split by non-word chars
        tokens = set(re.split(r'[^\w]+', text.lower()))
        tokens.discard('')
        return tokens

    def _get_prefixes(self, text: str) -> Set[str]:
        """Generate all prefixes for a given text (min 1 char)."""
        if not text:
            return set()
        text = text.lower().strip()
        return {text[:i] for i in range(1, len(text) + 1)}

    async def add_item(self, item: SearchResultItem, keywords: List[str]):
        """
        Add an item to the index.
        """
        async with self._lock:
            self._items[item.id] = item
            self._keywords[item.id] = keywords
            
            # Tokenize all keywords and index prefixes of tokens
            all_tokens = set()
            for kw in keywords:
                all_tokens.update(self._tokenize(kw))
                # Also index the full keyword (useful for "TSMC" if tokens split it weirdly? usually not needed)
                if kw:
                    all_tokens.add(kw.lower())

            for token in all_tokens:
                prefixes = self._get_prefixes(token)
                for prefix in prefixes:
                    self._index[prefix].add(item.id)

    async def add_keywords(self, item_id: str, keywords: List[str]):
        """Add extra searchable keywords to an already-indexed item.

        Used to enrich an existing stock (e.g. a US ticker) with its zh-TW name and
        aliases without creating a duplicate item. No-op if the item is unknown.
        """
        async with self._lock:
            if item_id not in self._items:
                return
            existing = self._keywords[item_id]
            for kw in keywords:
                if not kw or kw in existing:
                    continue
                existing.append(kw)
                tokens = set(self._tokenize(kw))
                tokens.add(kw.lower())
                for token in tokens:
                    for prefix in self._get_prefixes(token):
                        self._index[prefix].add(item_id)

    async def clear(self):
        """Clear the index."""
        async with self._lock:
            self._items.clear()
            self._index.clear()
            self._keywords.clear()
            self._is_initialized = False

    def _calculate_score(self, query: str, item: SearchResultItem, keywords: List[str]) -> float:
        """
        Calculate match score.
        Higher is better.
        """
        score = 0
        q = query.lower()
        
        # Base score
        score += 10
        
        # Keyword matching
        for kw in keywords:
            k = kw.lower()
            if k == q:
                score += 100  # Exact match
            elif k.startswith(q):
                score += 50   # Prefix match
            elif q in k:
                score += 10   # Infix match (if we had infix indexing, but we only index prefixes of tokens)
        
        # Boost by type
        if item.type == 'stock':
            score += 5
        elif item.type == 'podcast':
            score += 3
        
        # Boost by available data (e.g. volume/mentions if we had it in metadata)
        # item.metadata is a dict
        if item.metadata:
            # Huge boost for popular items if 'mentions' count exists
            mentions = item.metadata.get('mentions')
            if isinstance(mentions, (int, float)):
                score += min(mentions, 20) # Cap boost

        return score

    def suggest(self, prefix: str, limit: int = 8) -> List[SearchResultItem]:
        """
        Get ranked suggestions.
        """
        if not prefix:
            return []
        
        prefix = prefix.lower().strip()
        
        # 1. Get candidate IDs from index (O(1))
        candidate_ids = self._index.get(prefix, set())
        
        # 2. Score and Rank candidates
        results = []
        for uid in candidate_ids:
            item = self._items.get(uid)
            if not item: continue
            
            score = self._calculate_score(prefix, item, self._keywords.get(uid, []))
            results.append((score, item))
            
        # 3. Sort by score desc, then by title length (shorter first)
        results.sort(key=lambda x: (x[0], -len(x[1].title)), reverse=True)
        
        return [r[1] for r in results[:limit]]

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def mark_initialized(self):
        self._is_initialized = True
