from typing import List, Dict, Set
from src.schemas.search import SearchResultItem
import asyncio
import logging
from collections import defaultdict
import re

logger = logging.getLogger(__name__)

# Han, kana, and the CJK compatibility block. A CJK name has no spaces to tokenize on, so
# the whole thing is one token and prefix-only matching makes it findable *only* from its
# first character: "兆華" found 兆華與股惑仔 (446 episodes) but "股惑仔" found nothing, and
# "積電"/"台灣50"/"一路發"/"M平方" all answered empty against names that literally contain
# them. Indexing every suffix turns the existing prefix walk into substring matching.
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
# Beyond this a name is a sentence, not a name: n suffixes cost n(n+1)/2 index entries, so
# the cap is what keeps a long title from dominating the index. Measured on the real corpus
# (3,685 items / 8,056 keywords): 25.9k keys → 36.2k, 9.3 MB → 12.9 MB.
_MAX_SUFFIX_CHARS = 20


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

    def _index_forms(self, keyword: str) -> Set[str]:
        """Every string whose prefixes should point at this item.

        Latin text keeps the old behaviour (its tokens plus the whole keyword); a CJK
        token additionally contributes its suffixes, so a reader who remembers the middle
        of a name ("股惑仔", "積電") finds it just like one who remembers the start.
        """
        if not keyword:
            return set()
        forms = {t for t in self._tokenize(keyword) if t}
        forms.add(keyword.lower().strip())
        for token in list(forms):
            if _CJK_RE.search(token) and 1 < len(token) <= _MAX_SUFFIX_CHARS:
                forms.update(token[i:] for i in range(1, len(token)))
        forms.discard("")
        return forms

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
            # Drop empty/None keywords here, the one path every caller shares: a TW ETF with
            # no English name indexes as [ticker, None, zh, ...] (routers/search.py), and a
            # None reached _calculate_score's kw.lower() -> every suggest query whose prefix
            # matched that stock answered 500 (prod 2026-09-18: "981", "00646", "00685L").
            # add_keywords already filters; this makes add_item agree.
            self._keywords[item.id] = [kw for kw in keywords if kw]
            
            # Tokenize all keywords and index prefixes of tokens (CJK also by suffix)
            all_tokens = set()
            for kw in keywords:
                all_tokens.update(self._index_forms(kw))

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
                for token in self._index_forms(kw):
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
                score += 10   # Infix match — reachable since CJK names index by suffix too,
                              # and deliberately worth less than a prefix hit so 台積 still
                              # ranks 台積電 above a name that merely contains it.
        
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
    def size(self) -> int:
        """Indexed items — what a rebuild reports, so a caller can see it did something."""
        return len(self._items)

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def mark_initialized(self):
        self._is_initialized = True
