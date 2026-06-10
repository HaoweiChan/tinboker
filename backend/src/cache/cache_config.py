"""
Cache configuration - TTL values and key prefixes
"""
from typing import Dict

# Base unit: 1 minute in seconds
MIN_LEN = 60

# TTL values in seconds (expressed as multiples of minutes)
CACHE_TTL: Dict[str, int] = {
    # Stock data — external APIs (Massive, FinMind) have strict rate limits
    "stock_info": MIN_LEN * 60,          # 1 hour (company details rarely change)
    "stock_basic": MIN_LEN * 60,         # 1 hour
    "stock_price": MIN_LEN * 30,         # 30 minutes (current price)
    
    # Stock lists
    "stock_list": MIN_LEN * 60,          # 1 hour
    
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
    
    # Podcast data — pipeline pulls every 10 min, keep Redis ≤ pull interval
    "podcast_list": MIN_LEN * 30,            # 30 minutes (show list is stable)
    "podcast_item": MIN_LEN * 60,            # 1 hour (individual podcast metadata)
    "podcast_episodes": MIN_LEN * 10,        # 10 minutes (matches pipeline pull frequency)
    "podcast_episode": MIN_LEN * 60,         # 1 hour (individual episode detail)

    # Recommendation / ticker buzz (2 hours)
    "recommendation_by_ticker": 7200,
    "recommendation_by_podcaster": 7200,
    "recommendation_buzz": 7200,

    # Articles
    "article_item": MIN_LEN * 60,       # 1 hour
    "article_list": MIN_LEN * 5,        # 5 minutes
}

