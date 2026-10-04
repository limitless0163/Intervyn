"""Exercise lock lifetime, contention, cancellation, and independent keys."""

import asyncio
import gc
import weakref

import pytest

from app.utils.locks import KeyedLocks


def test_idle_lock_is_reclaimed() -> None:
    locks = KeyedLocks()
    lock = locks.get("session")
    assert locks.get("session") is lock
    reference = weakref.ref(lock)
    del lock
    gc.collect()
    assert reference() is None


def test_waiters_keep_one_lock_and_cancellation_does_not_block_others() -> None:
    locks = KeyedLocks()

    async def run() -> None:
        entered = asyncio.Event()
        completed = []

        async def waiting(value: int) -> None:
            entered.set()
            async with locks.get("session"):
                completed.append(value)

        async with locks.get("session"):
            cancelled = asyncio.create_task(waiting(1))
            await entered.wait()
            entered.clear()
            remaining = asyncio.create_task(waiting(2))
            await entered.wait()
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            assert not completed
            # Another session proceeds while this session remains locked.
            async with locks.get("other"):
                assert not remaining.done()

        await remaining
        assert completed == [2]

    asyncio.run(run())
