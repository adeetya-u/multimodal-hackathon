"""In-process pub/sub for Vapi → UI events (checklist, transcript, mode)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class VoiceEventHub:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, case_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[case_id].add(queue)
        return queue

    def unsubscribe(self, case_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues[case_id].discard(queue)

    def publish(self, case_id: str, topic: str, payload: dict[str, Any]) -> None:
        event = {"topic": topic, "payload": payload}
        for queue in list(self._queues.get(case_id, ())):
            try:
                queue.put_nowait(event)
            except Exception:
                pass


voice_events = VoiceEventHub()
