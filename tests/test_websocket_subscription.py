"""Tests for the WebSocket client's event-subscription routing.

These exercise the novel routing logic added for ``listen_events`` without a
live Home Assistant: a fake WebSocket feeds messages through the real
``_listener`` loop and we assert acks resolve futures while events route to the
correct subscription queue.
"""

import asyncio

import aiohttp
import pytest

from ha_mcp.ha_client.websocket import HAWebSocketClient


class _FakeMsg:
    def __init__(self, data):
        self.type = aiohttp.WSMsgType.TEXT
        self._data = data

    def json(self):
        return self._data


class _FakeWS:
    """Async-iterable fake that yields a fixed list of messages then stops."""

    def __init__(self, messages):
        self._messages = messages
        self.closed = False

    def __aiter__(self):
        async def _gen():
            for message in self._messages:
                yield _FakeMsg(message)

        return _gen()


async def test_listener_routes_ack_and_events():
    client = HAWebSocketClient("ws://test/api/websocket", "token")
    client._connected = True
    client._should_reconnect = False  # don't attempt reconnect when the feed ends

    loop = asyncio.get_running_loop()
    ack_future: asyncio.Future = loop.create_future()
    queue: asyncio.Queue = asyncio.Queue()
    # Simulate that subscribe() has already sent message id=1.
    client._pending[1] = ack_future
    client._subscriptions[1] = queue

    client._ws = _FakeWS(
        [
            {"id": 1, "type": "result", "success": True, "result": None},
            {"id": 1, "type": "event", "event": {"event_type": "state_changed",
                                                  "data": {"entity_id": "light.k"}}},
            {"id": 1, "type": "event", "event": {"event_type": "state_changed",
                                                  "data": {"entity_id": "light.l"}}},
            {"id": 99, "type": "event", "event": {"event_type": "orphan"}},
        ]
    )

    await client._listener()

    assert ack_future.done() and ack_future.result()["success"] is True

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert [e["data"]["entity_id"] for e in events] == ["light.k", "light.l"]


async def test_unsubscribe_is_failure_tolerant():
    """unsubscribe() should swallow errors (e.g. after a reconnect drop)."""
    client = HAWebSocketClient("ws://test/api/websocket", "token")
    client._subscriptions[5] = asyncio.Queue()
    # Not connected -> send_command raises -> unsubscribe must not propagate.
    await client.unsubscribe(5)
    assert 5 not in client._subscriptions


@pytest.mark.parametrize("connected", [False])
async def test_subscribe_requires_connection(connected):
    client = HAWebSocketClient("ws://test/api/websocket", "token")
    client._connected = connected
    with pytest.raises(Exception):
        await client.subscribe("subscribe_events", event_type="state_changed")
