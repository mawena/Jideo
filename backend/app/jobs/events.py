"""Diffusion des événements de tâches vers les flux SSE (depuis n'importe quel thread)."""
from __future__ import annotations

import asyncio
import threading


def _put(queue: asyncio.Queue, event: dict) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # client trop lent : il se resynchronisera via GET /api/jobs


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def publish(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                loop.call_soon_threadsafe(_put, queue, event)
            except RuntimeError:  # boucle arrêtée entre-temps
                return
