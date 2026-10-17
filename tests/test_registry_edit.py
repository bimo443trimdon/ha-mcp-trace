import json
from contextlib import asynccontextmanager

from fastmcp import Client, FastMCP

from ha_mcp.tools.registry_edit import register_registry_edit_tools


class FakeWS:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def send_command(self, msg_type, **kwargs):
        self.calls.append((msg_type, kwargs))
        return self.responses.get(msg_type)


async def _call(ws, args):
    @asynccontextmanager
    async def lifespan(_server):
        yield {"ws": ws, "rest": None}

    mcp = FastMCP("t", lifespan=lifespan)
    register_registry_edit_tools(mcp)
    async with Client(mcp) as client:
        result = await client.call_tool("update_entity", args)
    return json.loads(result.content[0].text)


async def test_display_precision_merges_existing_sensor_options():
    ws = FakeWS({
        "config/entity_registry/get": {"options": {"sensor": {"unit_of_measurement": "°F"}}},
        "config/entity_registry/update": {"entity_entry": {}},
    })
    data = await _call(ws, {"entity_id": "sensor.temp", "display_precision": 1})
    assert data["status"] == "updated"
    msg_type, payload = ws.calls[-1]
    assert msg_type == "config/entity_registry/update"
    assert payload["options_domain"] == "sensor"
    assert payload["options"] == {"unit_of_measurement": "°F", "display_precision": 1}


async def test_display_precision_rejects_non_sensor():
    ws = FakeWS({})
    data = await _call(ws, {"entity_id": "light.x", "display_precision": 1})
    assert "error" in data
    assert ws.calls == []


async def test_display_precision_rejects_out_of_range():
    data = await _call(FakeWS({}), {"entity_id": "sensor.x", "display_precision": 11})
    assert "error" in data
