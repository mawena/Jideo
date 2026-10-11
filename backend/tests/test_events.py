import asyncio
import threading

from app.jobs.events import EventBus


def test_event_bus_delivers_from_other_threads():
    async def scenario():
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        queue = bus.subscribe()
        threading.Thread(target=bus.publish, args=({"type": "x"},)).start()
        assert await asyncio.wait_for(queue.get(), 1) == {"type": "x"}
        bus.unsubscribe(queue)
        bus.publish({"type": "y"})
        await asyncio.sleep(0.05)
        assert queue.empty()

    asyncio.run(scenario())


def test_publish_without_loop_is_noop():
    EventBus().publish({"type": "x"})
