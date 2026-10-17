"""Tests for reading stored Home Assistant automation traces."""

import json

import pytest
from fastmcp import FastMCP

from ha_mcp.tools import register_all_tools
from ha_mcp.tools import traces


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class _FakeWebSocket:
    def __init__(self):
        self.commands = []

    async def send_command(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command == "trace/list":
            return [{"run_id": "run-1"}, {"run_id": "run-2"}, {"run_id": "run-3"}]
        return {"run_id": kwargs["run_id"], "trace": "details"}


@pytest.mark.asyncio
async def test_get_automation_traces_returns_limited_recent_traces(monkeypatch):
    websocket = _FakeWebSocket()
    server = _FakeMCP()
    traces.register_trace_tools(server)
    monkeypatch.setattr(traces, "get_clients", lambda _ctx: (websocket, None))

    result = json.loads(
        await server.tools["get_automation_traces"](
            object(), "automation.garage_door", limit=2
        )
    )

    assert result == {
        "automation_id": "automation.garage_door",
        "count": 2,
        "traces": [
            {"run_id": "run-1", "trace": "details"},
            {"run_id": "run-2", "trace": "details"},
        ],
    }
    assert websocket.commands == [
        ("trace/list", {"domain": "automation", "item_id": "garage_door"}),
        (
            "trace/get",
            {"domain": "automation", "item_id": "garage_door", "run_id": "run-1"},
        ),
        (
            "trace/get",
            {"domain": "automation", "item_id": "garage_door", "run_id": "run-2"},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("automation_id", "limit", "message"),
    [
        ("script.garage_door", 3, "automation entity ID"),
        ("automation.", 3, "automation entity ID"),
        ("automation.garage_door", 0, "between 1 and 10"),
        ("automation.garage_door", 11, "between 1 and 10"),
    ],
)
async def test_get_automation_traces_rejects_invalid_arguments(
    automation_id, limit, message
):
    server = _FakeMCP()
    traces.register_trace_tools(server)

    with pytest.raises(ValueError, match=message):
        await server.tools["get_automation_traces"](
            object(), automation_id, limit=limit
        )


@pytest.mark.asyncio
async def test_trace_tool_is_registered_on_server():
    server = FastMCP("test")
    register_all_tools(server)

    registered_names = {tool.name for tool in await server.list_tools()}

    assert "get_automation_traces" in registered_names
