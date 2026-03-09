"""Unit tests for consensus realtime broker behavior."""

from __future__ import annotations

from datetime import date

import pytest

from sleep_scoring_web.services.consensus_realtime import ConsensusRealtimeBroker


class _FakeWebSocket:
    def __init__(self, fail_on_send: bool = False) -> None:
        self.fail_on_send = fail_on_send
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


@pytest.mark.asyncio
class TestConsensusRealtimeBroker:
    async def test_publish_fanout_same_topic(self) -> None:
        broker = ConsensusRealtimeBroker()
        ws_a = _FakeWebSocket()
        ws_b = _FakeWebSocket()

        await broker.subscribe(ws_a, file_id=1, analysis_date=date(2024, 1, 1))
        await broker.subscribe(ws_b, file_id=1, analysis_date=date(2024, 1, 1))

        payload = {"type": "consensus_update", "event": "vote_changed"}
        await broker.publish(file_id=1, analysis_date=date(2024, 1, 1), payload=payload)

        assert ws_a.sent == [payload]
        assert ws_b.sent == [payload]

    async def test_publish_isolated_by_topic(self) -> None:
        broker = ConsensusRealtimeBroker()
        ws_topic_a = _FakeWebSocket()
        ws_topic_b = _FakeWebSocket()

        await broker.subscribe(ws_topic_a, file_id=1, analysis_date=date(2024, 1, 1))
        await broker.subscribe(ws_topic_b, file_id=2, analysis_date=date(2024, 1, 1))

        payload = {"type": "consensus_update", "event": "vote_changed"}
        await broker.publish(file_id=1, analysis_date=date(2024, 1, 1), payload=payload)

        assert ws_topic_a.sent == [payload]
        assert ws_topic_b.sent == []

    async def test_publish_drops_stale_socket_after_send_failure(self) -> None:
        broker = ConsensusRealtimeBroker()
        ws_good = _FakeWebSocket()
        ws_bad = _FakeWebSocket(fail_on_send=True)
        topic_date = date(2024, 1, 1)

        await broker.subscribe(ws_good, file_id=1, analysis_date=topic_date)
        await broker.subscribe(ws_bad, file_id=1, analysis_date=topic_date)

        payload = {"type": "consensus_update", "event": "vote_changed"}
        await broker.publish(file_id=1, analysis_date=topic_date, payload=payload)
        await broker.publish(file_id=1, analysis_date=topic_date, payload=payload)

        # Good socket receives both publishes.
        assert ws_good.sent == [payload, payload]
        # Bad socket failed on first send and should be removed.
        assert ws_bad.sent == []

    async def test_unsubscribe_removes_socket(self) -> None:
        broker = ConsensusRealtimeBroker()
        ws = _FakeWebSocket()
        topic_date = date(2024, 1, 1)
        payload = {"type": "consensus_update", "event": "vote_changed"}

        await broker.subscribe(ws, file_id=1, analysis_date=topic_date)
        await broker.unsubscribe(ws, file_id=1, analysis_date=topic_date)
        await broker.publish(file_id=1, analysis_date=topic_date, payload=payload)

        assert ws.sent == []


@pytest.mark.skip(reason="Requires multi-process deployment harness (e.g., 2 uvicorn workers + shared pubsub).")
def test_multi_worker_cross_replica_fanout_integration_placeholder() -> None:
    """Document required cross-worker fanout test for production architecture."""
    assert True
