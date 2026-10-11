import asyncio
import json

from app.api.events import event_stream
from app.jobs.events import EventBus


def test_event_stream_relays_events_and_pings():
    async def scenario():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())

        async def connected():
            return False

        stream = event_stream(bus, connected, ping_interval=0.05)
        assert await stream.__anext__() == ": connected\n\n"
        bus.publish({"type": "queued", "job": {"id": "x"}})
        chunk = await stream.__anext__()
        assert chunk.startswith("data: ") and json.loads(chunk[6:])["job"]["id"] == "x"
        assert await stream.__anext__() == ": ping\n\n"
        await stream.aclose()
        assert bus._subscribers == set()

    asyncio.run(scenario())
