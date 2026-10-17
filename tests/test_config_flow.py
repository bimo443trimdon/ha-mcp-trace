import json
from contextlib import asynccontextmanager

import pytest
from fastmcp import Client, FastMCP

from ha_mcp.ha_client.models import HAConnectionError
from ha_mcp.tools.config_flow import REDACTED, redact, register_config_flow_tools
from ha_mcp.tools.registry_remove import register_registry_remove_tools


class FakeRest:
    def __init__(self):
        self.calls = []

    async def get_flow_handlers(self, handler_type=None):
        self.calls.append(("handlers", handler_type))
        return ["hue", "mqtt"]

    async def start_flow(self, kind, payload):
        self.calls.append(("start", kind, payload))
        return {"type": "form", "flow_id": "f1", "step_id": "user", "data_schema": [{"name": "host", "required": True}]}

    async def continue_flow(self, kind, flow_id, user_input):
        self.calls.append(("continue", kind, flow_id, user_input))
        return {"type": "create_entry", "flow_id": flow_id, "result": {"entry_id": "e1", "data": {"password": "pw"}}}

    async def get_flow(self, kind, flow_id):
        return {"type": "external", "flow_id": flow_id}

    async def abort_flow(self, kind, flow_id):
        self.calls.append(("abort", kind, flow_id))
        return {"message": "Flow aborted"}

    async def delete_config_entry(self, entry_id):
        self.calls.append(("delete", entry_id))
        return {"require_restart": False}


class FakeWS:
    def __init__(self, unknown_remove=False):
        self.calls = []
        self.unknown_remove = unknown_remove

    async def send_command(self, msg_type, **kwargs):
        self.calls.append((msg_type, kwargs))
        if msg_type == "config_entries/get_single":
            return {"config_entry": {"domain": "hue", "title": "Hue", "state": "loaded", "source": "user"}}
        if msg_type == "config/entity_registry/get":
            return {"entity_id": kwargs["entity_id"], "platform": "demo"}
        if msg_type == "config/device_registry/list":
            return [{"id": "d1", "name": "Lamp", "config_entries": ["e1", "e2"]}]
        if msg_type == "config/device_registry/remove" and self.unknown_remove:
            raise HAConnectionError("Command config/device_registry/remove failed [unknown_command]: Unknown command.")
        return None


def make_server(ws, rest):
    @asynccontextmanager
    async def lifespan(server):
        yield {"ws": ws, "rest": rest}

    mcp = FastMCP("test", lifespan=lifespan)
    register_config_flow_tools(mcp)
    register_registry_remove_tools(mcp)
    return mcp


async def call(mcp, name, **args):
    async with Client(mcp) as client:
        result = await client.call_tool(name, args)
        return json.loads(result.content[0].text)


def test_redact_masks_nested_credentials():
    data = {"host": "h", "Password": "x", "nested": [{"api_key": "k", "port": 1}], "token": ""}
    assert redact(data) == {"host": "h", "Password": REDACTED, "nested": [{"api_key": REDACTED, "port": 1}], "token": ""}


async def test_flow_loop_start_and_continue():
    rest = FakeRest()
    mcp = make_server(FakeWS(), rest)

    started = await call(mcp, "start_config_flow", handler="hue")
    assert started["type"] == "form" and "next_step_hint" in started
    assert rest.calls[-1] == ("start", "config", {"handler": "hue"})

    done = await call(mcp, "continue_config_flow", flow_id="f1", user_input='{"host": "1.2.3.4", "password": "pw"}')
    assert rest.calls[-1] == ("continue", "config", "f1", {"host": "1.2.3.4", "password": "pw"})
    assert done["result"]["data"]["password"] == REDACTED


async def test_options_and_subentry_payloads():
    rest = FakeRest()
    mcp = make_server(FakeWS(), rest)
    await call(mcp, "start_options_flow", entry_id="e1")
    assert rest.calls[-1] == ("start", "options", {"handler": "e1"})
    await call(mcp, "start_subentry_flow", entry_id="e1", subentry_type="conversation")
    assert rest.calls[-1] == ("start", "subentry", {"handler": ["e1", "conversation"]})
    await call(mcp, "continue_subentry_flow", flow_id="f9", user_input="{}")
    assert rest.calls[-1][:3] == ("continue", "subentry", "f9")


async def test_invalid_user_input_rejected():
    mcp = make_server(FakeWS(), FakeRest())
    out = await call(mcp, "continue_config_flow", flow_id="f1", user_input="[1]")
    assert "error" in out


async def test_delete_config_entry_previews_and_deletes():
    rest = FakeRest()
    mcp = make_server(FakeWS(), rest)
    out = await call(mcp, "delete_config_entry", entry_id="e1")
    assert out["status"] == "deleted" and out["entry"]["domain"] == "hue"
    assert rest.calls[-1] == ("delete", "e1")


async def test_ignore_flow_ws_payload():
    ws = FakeWS()
    mcp = make_server(ws, FakeRest())
    await call(mcp, "ignore_config_flow", flow_id="f1", title="Hue Bridge")
    assert ws.calls[-1] == ("config_entries/ignore_flow", {"flow_id": "f1", "title": "Hue Bridge"})


async def test_remove_device_uses_new_command():
    ws = FakeWS()
    mcp = make_server(ws, FakeRest())
    out = await call(mcp, "remove_device", device_id="d1")
    assert out["status"] == "removed"
    assert ws.calls[-1] == ("config/device_registry/remove", {"device_id": "d1"})


async def test_remove_device_falls_back_on_older_ha():
    ws = FakeWS(unknown_remove=True)
    mcp = make_server(ws, FakeRest())
    out = await call(mcp, "remove_device", device_id="d1")
    assert out["status"] == "removed"
    fallback = [c for c in ws.calls if c[0] == "config/device_registry/remove_config_entry"]
    assert [c[1]["config_entry_id"] for c in fallback] == ["e1", "e2"]


async def test_remove_entity():
    ws = FakeWS()
    mcp = make_server(ws, FakeRest())
    out = await call(mcp, "remove_entity", entity_id="sensor.old")
    assert out["status"] == "removed"
    assert ws.calls[-1] == ("config/entity_registry/remove", {"entity_id": "sensor.old"})
