from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class TraceHub:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, conversation_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subs[conversation_id].add(q)
        return q

    async def unsubscribe(self, conversation_id: int, q: asyncio.Queue) -> None:
        async with self._lock:
            s = self._subs.get(conversation_id)
            if not s:
                return
            s.discard(q)
            if not s:
                self._subs.pop(conversation_id, None)

    async def publish(self, conversation_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            subs = list(self._subs.get(conversation_id, set()))
        for q in subs:
            try:
                q.put_nowait(event)
            except Exception:
                continue


hub = TraceHub()

