"""Realtime broker for consensus update fanout."""

from __future__ import annotations

import logging
from asyncio import Lock
from collections import defaultdict
from datetime import UTC, date, datetime, timezone
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import WebSocket


class ConsensusRealtimeBroker:
    """In-memory topic broker keyed by file/date."""

    def __init__(self) -> None:
        self._topics: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = Lock()

    @staticmethod
    def _topic(file_id: int, analysis_date: date) -> str:
        return f"{file_id}:{analysis_date.isoformat()}"

    async def subscribe(self, websocket: WebSocket, *, file_id: int, analysis_date: date) -> None:
        topic = self._topic(file_id, analysis_date)
        async with self._lock:
            self._topics[topic].add(websocket)

    async def unsubscribe(self, websocket: WebSocket, *, file_id: int, analysis_date: date) -> None:
        topic = self._topic(file_id, analysis_date)
        async with self._lock:
            sockets = self._topics.get(topic)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._topics.pop(topic, None)

    async def publish(self, *, file_id: int, analysis_date: date, payload: dict[str, Any]) -> None:
        topic = self._topic(file_id, analysis_date)
        async with self._lock:
            subscribers = list(self._topics.get(topic, set()))

        if not subscribers:
            return

        stale: list[WebSocket] = []
        for ws in subscribers:
            try:
                await ws.send_json(payload)
            except Exception:
                logger.debug("WebSocket send failed for topic %s", topic, exc_info=True)
                stale.append(ws)

        if stale:
            async with self._lock:
                sockets = self._topics.get(topic)
                if sockets:
                    for ws in stale:
                        sockets.discard(ws)
                    if not sockets:
                        self._topics.pop(topic, None)


consensus_realtime_broker = ConsensusRealtimeBroker()


async def broadcast_consensus_update(
    *,
    file_id: int,
    analysis_date: date,
    event: str,
    username: str | None = None,
    candidate_id: int | None = None,
) -> None:
    """Broadcast a consensus-related change for a file/date topic."""
    payload: dict[str, Any] = {
        "type": "consensus_update",
        "file_id": file_id,
        "analysis_date": analysis_date.isoformat(),
        "event": event,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if username:
        payload["username"] = username
    if candidate_id is not None:
        payload["candidate_id"] = candidate_id

    await consensus_realtime_broker.publish(
        file_id=file_id,
        analysis_date=analysis_date,
        payload=payload,
    )
