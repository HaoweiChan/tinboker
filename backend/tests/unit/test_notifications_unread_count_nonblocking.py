"""Regression test for the /api/notifications/unread-count event-loop-blocking bug.

get_unread_count() does a synchronous Firestore .stream() call. Calling it directly
inside the async route handler blocks the whole uvicorn event loop for the duration
of that network round trip, stalling every other in-flight request on the worker.
The fix offloads it via asyncio.to_thread (src/routers/notifications.py).

This test races the handler against a concurrent asyncio task. If the handler
blocks the loop, the two 0.3s waits run back-to-back (~0.6s total); if it's
correctly offloaded to a thread, they run concurrently (~0.3s total).
"""
import asyncio
import time

from src.routers import notifications as notifications_router


class _FakeUser:
    id = "test-user-id"


def test_unread_count_handler_does_not_block_event_loop(monkeypatch):
    def _slow_get_unread_count(user_id):
        time.sleep(0.3)  # stand-in for a blocking Firestore .stream() round trip
        return 7

    monkeypatch.setattr(notifications_router, "get_unread_count", _slow_get_unread_count)

    async def _run():
        start = time.monotonic()
        result, _ = await asyncio.gather(
            notifications_router.get_unread_notification_count(user=_FakeUser()),
            asyncio.sleep(0.3),  # concurrent event-loop work that must keep progressing
        )
        elapsed = time.monotonic() - start
        return result, elapsed

    result, elapsed = asyncio.run(_run())

    assert result == {"unread_count": 7}
    # Offloaded (fixed): both 0.3s waits overlap -> ~0.3s total.
    # Inline on the loop (bug): the sync sleep blocks everything -> ~0.6s total.
    assert elapsed < 0.5, f"event loop appears blocked — gather took {elapsed:.2f}s (expected ~0.3s)"
