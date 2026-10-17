"""Event tools: subscribe to live Home Assistant events for a bounded window.

MCP is request/response, so rather than a streaming subscription this tool
opens a short-lived subscription, collects events for a bounded duration (or
until a max count), then unsubscribes and returns the collected events.
"""

import asyncio
import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients

logger = logging.getLogger(__name__)

# Hard caps so a tool call can never block the server indefinitely.
_MAX_DURATION = 60.0
_MAX_EVENTS = 200


def register_event_tools(mcp_server):
    """Register event-listening tools on the MCP server."""

    @mcp_server.tool()
    async def listen_events(
        ctx: Context,
        event_type: str = "state_changed",
        duration_seconds: float = 10.0,
        entity_id: str | None = None,
        max_events: int = 50,
    ) -> str:
        """Listen for live Home Assistant events for a bounded time window.

        Opens a subscription, collects matching events until either
        ``duration_seconds`` elapses or ``max_events`` are captured, then
        unsubscribes and returns what it saw. Handy for watching what happens
        when a device is triggered, or confirming an automation fires.

        Args:
            event_type: Event type to subscribe to (e.g. 'state_changed',
                'call_service', 'automation_triggered'). Default 'state_changed'.
            duration_seconds: How long to listen, capped at 60 seconds.
            entity_id: For 'state_changed', only keep events for this entity.
            max_events: Stop after this many matching events (capped at 200).

        Returns a JSON object with the captured events and a count.
        """
        ws, _rest = get_clients(ctx)

        duration = max(0.0, min(duration_seconds, _MAX_DURATION))
        limit = max(1, min(max_events, _MAX_EVENTS))

        try:
            sub_id, queue = await ws.subscribe(
                "subscribe_events", event_type=event_type
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Could not subscribe: {exc}"})

        events: list[dict] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration

        try:
            while len(events) < limit:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break

                if entity_id and event_type == "state_changed":
                    if event.get("data", {}).get("entity_id") != entity_id:
                        continue
                events.append(event)
        finally:
            await ws.unsubscribe(sub_id)

        return json.dumps({
            "event_type": event_type,
            "listened_seconds": duration,
            "count": len(events),
            "events": events,
        }, indent=2)
