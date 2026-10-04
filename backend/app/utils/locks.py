"""按键串行化同一事件循环内的操作，空闲锁不占用长期缓存。"""

from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary


class KeyedLocks:
    """调用方和等待者持有强引用，最后一个使用者退出后自动回收锁。

    仅用于同一进程、同一事件循环内的协调，不提供跨进程数据库锁。
    """

    def __init__(self) -> None:
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def get(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock
