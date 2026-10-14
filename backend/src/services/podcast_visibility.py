"""Environment-specific podcast visibility without changing the shared registry."""
from src.config import settings

HIDDEN_PODCAST_NAMES = frozenset({"曲博科技教室"})
DEVELOPMENT_ONLY_PODCAST_NAMES = frozenset({"曼報", "鈔錢部署｜盧燕俐"})


def hidden_podcast_names() -> frozenset[str]:
    if settings.environment == "development":
        return HIDDEN_PODCAST_NAMES
    return HIDDEN_PODCAST_NAMES | DEVELOPMENT_ONLY_PODCAST_NAMES


def visibility_cache_tag() -> str:
    return f"visibility-v1:{settings.environment}"
