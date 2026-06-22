"""Generic async Publish / Subscribe broker.

``AsyncBroker[T]`` is a lightweight, in-process pub/sub bus parameterised on
the message type.  Subscribers receive a copy of every published message on
their own ``asyncio.Queue``.

Usage::

    from venux_code.pubsub.broker import AsyncBroker

    broker: AsyncBroker[str] = AsyncBroker()

    async with broker.subscribe() as queue:
        await broker.publish("hello")
        msg = await queue.get()   # "hello"
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generic, TypeVar

T = TypeVar("T")


class AsyncBroker(Generic[T]):
    """In-process async pub/sub broker for messages of type ``T``.

    Each call to :meth:`subscribe` creates a new :class:`asyncio.Queue`
    that receives a *copy* of every message published after subscription.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[T]] = []

    # ── Publish ────────────────────────────────────────────────────────────

    async def publish(self, message: T) -> int:
        """Broadcast *message* to all current subscribers.

        Returns the number of subscribers that received the message.
        Non-blocking: messages are placed via ``put_nowait`` so a slow
        subscriber will *not* block the publisher (messages queue up).
        """
        delivered = 0
        for queue in self._subscribers:
            queue.put_nowait(message)
            delivered += 1
        return delivered

    # ── Subscribe ──────────────────────────────────────────────────────────

    @asynccontextmanager
    async def subscribe(
        self, maxsize: int = 0
    ) -> AsyncGenerator[asyncio.Queue[T], None]:
        """Context manager that yields an ``asyncio.Queue``.

        The queue is automatically removed from the subscriber list when
        the context exits.

        Parameters
        ----------
        maxsize:
            Maximum queue size.  ``0`` means unbounded.
        """
        queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        try:
            yield queue
        finally:
            self._subscribers.remove(queue)

    # ── Introspection ──────────────────────────────────────────────────────

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subscribers)

    async def close(self) -> None:
        """Remove all subscribers and send ``None`` sentinel to unblock waiters."""
        for queue in self._subscribers:
            # Type-ignore: None is used as a poison-pill sentinel.
            queue.put_nowait(None)  # type: ignore[arg-type]
        self._subscribers.clear()
