"""The pubsub listen loop must block in get_message, not spin (prod CPU 100%, 2026-11)."""
import asyncio

from src.services.websocket_subscriber import WebSocketSubscriber


def test_listen_loop_blocks_in_get_message():
    calls = []

    class FakePubSub:
        async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
            calls.append(timeout)
            await asyncio.sleep(timeout)  # what redis does: wait up to timeout, then None
            return None

    async def run():
        sub = WebSocketSubscriber.__new__(WebSocketSubscriber)
        sub.pubsub, sub.websocket, sub._listening = FakePubSub(), None, True
        task = asyncio.create_task(sub._listen_loop())
        await asyncio.sleep(0.05)
        sub._listening = False
        task.cancel()

    asyncio.run(run())
    # With timeout=0 the old loop ran get_message thousands of times in 50 ms.
    assert calls and all(t and t > 0 for t in calls) and len(calls) < 5, calls[:5]
