"""
WebSocket subscriber manager for Redis pub/sub
"""
import asyncio
import json
import logging
from typing import Set, Optional
from fastapi import WebSocket
from redis import asyncio as aioredis
from src.cache.redis_client import RedisClient
from src.cache.channels import stock_ohlcv_channel

logger = logging.getLogger(__name__)

class WebSocketSubscriber:
    """Manages WebSocket subscription to Redis channels"""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.subscribed_channels: Set[str] = set()
        self._listening = False
        self._listen_task: Optional[asyncio.Task] = None

    async def subscribe(self, ticker: str) -> bool:
        """
        Subscribe to stock updates for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if subscribed successfully
        """
        try:
            if not self.pubsub:
                self.pubsub = await RedisClient.create_subscriber()
                if not self.pubsub:
                    logger.error("Failed to create Redis subscriber")
                    return False

            channel = stock_ohlcv_channel(ticker)
            await RedisClient.subscribe_channel(self.pubsub, channel)
            self.subscribed_channels.add(channel)
            logger.debug(f"Subscribed to {channel} for WebSocket")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to {ticker}: {e}")
            return False

    async def unsubscribe(self, ticker: str) -> bool:
        """
        Unsubscribe from stock updates for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if unsubscribed successfully
        """
        try:
            if not self.pubsub:
                return False

            channel = stock_ohlcv_channel(ticker)
            if channel in self.subscribed_channels:
                await RedisClient.unsubscribe_channel(self.pubsub, channel)
                self.subscribed_channels.discard(channel)
                logger.debug(f"Unsubscribed from {channel}")
            return True

        except Exception as e:
            logger.error(f"Error unsubscribing from {ticker}: {e}")
            return False

    async def start_listening(self):
        """Start listening for messages and forwarding to WebSocket"""
        if self._listening:
            return

        if not self.pubsub:
            logger.error("Cannot start listening: no pubsub connection")
            return

        self._listening = True
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        """Internal loop that listens to Redis and forwards to WebSocket"""
        try:
            while self._listening and self.pubsub:
                try:
                    # get_message blocks up to `timeout`, so the loop re-checks _listening once a
                    # second. Its default timeout is 0 (return None at once), which turned this
                    # into a busy loop pinning prod's event loop at 100% CPU per subscriber.
                    message = await self.pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )

                    if message and message['type'] == 'message':
                        # Parse and forward to WebSocket
                        try:
                            data = json.loads(message['data'])
                            await self.websocket.send_json(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in message: {message['data']}")
                        except Exception as e:
                            logger.error(f"Error sending WebSocket message: {e}")
                            break  # Exit loop on WebSocket error

                except Exception as e:
                    logger.error(f"Error in listen loop: {e}")
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.debug("Listen loop cancelled")
        finally:
            self._listening = False

    async def stop(self):
        """Stop listening and cleanup"""
        self._listening = False

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from all channels
        for channel in list(self.subscribed_channels):
            ticker = channel.split(':')[1]  # Extract ticker from channel name
            await self.unsubscribe(ticker)

        # Close pubsub connection
        if self.pubsub:
            await RedisClient.close_pubsub(self.pubsub)
            self.pubsub = None

