"""Environment-specific podcast visibility without changing the shared registry."""
from src.config import settings

# 曼報: dropped 2026-10-15, too little stock talk (it lives behind 曼報 Pro); its
# ingested episodes stay in the DB, hidden everywhere.
HIDDEN_PODCAST_NAMES = frozenset({"曲博科技教室", "曼報"})
DEVELOPMENT_ONLY_PODCAST_NAMES = frozenset({"鈔錢部署｜盧燕俐"})


def hidden_podcast_names() -> frozenset[str]:
    if settings.environment == "development":
        return HIDDEN_PODCAST_NAMES
    return HIDDEN_PODCAST_NAMES | DEVELOPMENT_ONLY_PODCAST_NAMES


def visibility_cache_tag() -> str:
    return f"visibility-v1:{settings.environment}"
