"""GET /api/events : flux SSE unique pour toutes les tâches."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


async def event_stream(
    bus, is_disconnected: Callable[[], Awaitable[bool]], ping_interval: float = 15.0
) -> AsyncIterator[str]:
    queue = bus.subscribe()
    try:
        yield ": connected\n\n"
        while not await is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=ping_interval)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        bus.unsubscribe(queue)


@router.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        event_stream(request.app.state.bus, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
