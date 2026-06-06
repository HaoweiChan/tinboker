"""
Cache configuration - TTL values and key prefixes
"""
from typing import Dict

# Base unit: 1 minute in seconds
MIN_LEN = 60

# TTL values in seconds (expressed as multiples of minutes)
CACHE_TTL: Dict[str, int] = {
    # Stock prices change frequently - short TTL
    "stock_info": MIN_LEN * 15,        # 5 minutes
    "stock_basic": MIN_LEN * 15,        # 5 minutes
    "stock_price": MIN_LEN * 15,         # 1 minute (most volatile)
    
    # Stock lists change often - very short TTL
    "stock_list": MIN_LEN * 20,          # 1 minute
    
    # Historical data rarely changes - long TTL
    "stock_ohlcv": MIN_LEN * 60 * 24,       # 1 day
    "stock_history": MIN_LEN * 60 * 24 ,    # 1 days (30 * 24 * 60 minutes)
    
    # Graph structure changes rarely - medium TTL
    "graph_data": MIN_LEN * 60 * 24,        # 30 minutes
    "graph_list": MIN_LEN * 60 * 24,         # 10 minutes
    
    # Visual graphs include prices - short TTL
    "visual_graph": MIN_LEN * 60 * 24,        # 30 minutes
    
    # News articles don't change - long TTL
    "news_item": MIN_LEN * 60,         # 1 hour
    "news_list": MIN_LEN * 60,          # 5 minutes
    "news_ticker": MIN_LEN * 60,       # 30 minutes
    
    # Session data
    "session": MIN_LEN * 60,           # 1 hour
    "ws_subscription": MIN_LEN * 5,     # 5 minutes
    
    # Podcast data
    "podcast_list": MIN_LEN * 60 * 3,       # 5 minutes
    "podcast_item": MIN_LEN * 60 * 3,      # 1 hour
    "podcast_episodes": MIN_LEN * 60 * 3,   # 5 minutes
    "podcast_episode": MIN_LEN * 60 * 3,   # 1 hour

    # Recommendation / ticker buzz (2 hours)
    "recommendation_by_ticker": 7200,
    "recommendation_by_podcaster": 7200,
    "recommendation_buzz": 7200,

    # Articles
    "article_item": MIN_LEN * 60,       # 1 hour
    "article_list": MIN_LEN * 5,        # 5 minutes
}

