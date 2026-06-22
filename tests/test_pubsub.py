"""Tests for AsyncBroker pub/sub."""

from __future__ import annotations

import asyncio

import pytest

from venux_code.pubsub.broker import AsyncBroker


class TestAsyncBrokerPublishSubscribe:
    async def test_publish_to_one_subscriber(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as queue:
            delivered = await broker.publish("hello")
            assert delivered == 1
            msg = await queue.get()
            assert msg == "hello"

    async def test_publish_to_multiple_subscribers(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as q1, broker.subscribe() as q2:
            delivered = await broker.publish("broadcast")
            assert delivered == 2
            assert await q1.get() == "broadcast"
            assert await q2.get() == "broadcast"

    async def test_no_subscribers(self):
        broker: AsyncBroker[str] = AsyncBroker()
        delivered = await broker.publish("nobody")
        assert delivered == 0

    async def test_messages_queued_per_subscriber(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as queue:
            await broker.publish("a")
            await broker.publish("b")
            await broker.publish("c")
            assert queue.get_nowait() == "a"
            assert queue.get_nowait() == "b"
            assert queue.get_nowait() == "c"

    async def test_subscriber_isolation(self):
        """Each subscriber gets its own copy of the message."""
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as q1:
            async with broker.subscribe() as q2:
                await broker.publish("msg")
                assert await q1.get() == "msg"
                assert await q2.get() == "msg"

    async def test_subscribe_late_misses_prior(self):
        """Messages published before subscribe are not received."""
        broker: AsyncBroker[str] = AsyncBroker()
        await broker.publish("before")
        async with broker.subscribe() as queue:
            assert queue.empty()
            await broker.publish("after")
            assert await queue.get() == "after"


class TestAsyncBrokerUnsubscribe:
    async def test_auto_unsubscribe_on_context_exit(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as _queue:
            assert broker.subscriber_count == 1
        assert broker.subscriber_count == 0

    async def test_does_not_receive_after_exit(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe() as queue:
            pass
        # After exit, publish should have 0 subscribers
        delivered = await broker.publish("late")
        assert delivered == 0


class TestAsyncBrokerSubscriberCount:
    async def test_count_zero_initial(self):
        broker: AsyncBroker[str] = AsyncBroker()
        assert broker.subscriber_count == 0

    async def test_count_multiple(self):
        broker: AsyncBroker[str] = AsyncBroker()
        async with broker.subscribe():
            async with broker.subscribe():
                assert broker.subscriber_count == 2


class TestAsyncBrokerClose:
    async def test_close_sends_sentinel(self):
        broker: AsyncBroker[str] = AsyncBroker()
        ctx = broker.subscribe()
        queue = await ctx.__aenter__()
        await broker.close()
        msg = await queue.get()
        # close sends None as a sentinel
        assert msg is None
        assert broker.subscriber_count == 0
        # Suppress ValueError since close() already cleared subscribers
        try:
            await ctx.__aexit__(None, None, None)
        except ValueError:
            pass

    async def test_close_multiple_subscribers(self):
        broker: AsyncBroker[str] = AsyncBroker()
        ctx1 = broker.subscribe()
        ctx2 = broker.subscribe()
        q1_queue: asyncio.Queue = await ctx1.__aenter__()
        q2_queue: asyncio.Queue = await ctx2.__aenter__()

        assert broker.subscriber_count == 2
        await broker.close()
        assert q1_queue.get_nowait() is None
        assert q2_queue.get_nowait() is None
        assert broker.subscriber_count == 0

        # Cleanup context managers (already removed by close, so suppress ValueError)
        try:
            await ctx1.__aexit__(None, None, None)
        except ValueError:
            pass
        try:
            await ctx2.__aexit__(None, None, None)
        except ValueError:
            pass


class TestAsyncBrokerMaxsize:
    async def test_bounded_queue(self):
        broker: AsyncBroker[int] = AsyncBroker()
        async with broker.subscribe(maxsize=2) as queue:
            await broker.publish(1)
            await broker.publish(2)
            # Third publish should raise because queue is full
            with pytest.raises(asyncio.QueueFull):
                await broker.publish(3)
            assert await queue.get() == 1
            assert await queue.get() == 2


class TestAsyncBrokerGenericTypes:
    async def test_dict_messages(self):
        broker: AsyncBroker[dict] = AsyncBroker()
        async with broker.subscribe() as queue:
            data = {"event": "update", "value": 42}
            await broker.publish(data)
            received = await queue.get()
            assert received == data
            assert received["event"] == "update"

    async def test_int_messages(self):
        broker: AsyncBroker[int] = AsyncBroker()
        async with broker.subscribe() as queue:
            await broker.publish(99)
            assert await queue.get() == 99
