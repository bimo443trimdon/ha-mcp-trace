import json
from contextlib import asynccontextmanager

import pytest
from fastmcp import Client, FastMCP

from ha_mcp.tools.categories import register_category_tools
from ha_mcp.tools.diagnostics import register_diagnostics_tools, summarize_trace
from ha_mcp.util.redact import redact, tail


class FakeWS:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def send_command(self, msg_type, **kwargs):
        self.calls.append((msg_type, kwargs))
        return self.responses.get(msg_type)


def _server(ws):
    @asynccontextmanager
    async def lifespan(_server):
        yield {"ws": ws, "rest": None}

    mcp = FastMCP("t", lifespan=lifespan)
    register_diagnostics_tools(mcp)
    register_category_tools(mcp)
    return mcp


async def _call(ws, tool, args):
    async with Client(_server(ws)) as client:
        result = await client.call_tool(tool, args)
    return json.loads(result.content[0].text)


def test_redact_patterns():
    text = (
        "Authorization: Bearer abc.def-ghi\n"
        "url=https://user:hunter2@example.com/x token=abcd1234 password: s3cret "
        '"api_key": "k-123"'
    )
    out = redact(text)
    for secret in ("abc.def-ghi", "hunter2", "abcd1234", "s3cret", "k-123"):
        assert secret not in out


def test_tail_truncates():
    text = "\n".join(f"line {i}" for i in range(10_000))
    out = tail(text, 1_000)
    assert len(out) < 1_100
    assert out.startswith("[... truncated")
    assert out.endswith("line 9999")


async def test_list_repairs_filters_ignored():
    ws = FakeWS({"repairs/list_issues": {"issues": [
        {"domain": "a", "issue_id": "1", "ignored": False, "dismissed_version": None},
        {"domain": "b", "issue_id": "2", "ignored": True, "dismissed_version": "2026.1.0"},
    ]}})
    data = await _call(ws, "list_repairs", {})
    assert [i["issue_id"] for i in data["issues"]] == ["1"]
    data = await _call(ws, "list_repairs", {"include_ignored": True})
    assert data["count"] == 2


async def test_ignore_repair_payload():
    ws = FakeWS({})
    await _call(ws, "ignore_repair", {"domain": "hue", "issue_id": "x", "ignore": True})
    assert ws.calls == [("repairs/ignore_issue", {"domain": "hue", "issue_id": "x", "ignore": True})]


async def test_system_log_redacts_and_filters():
    ws = FakeWS({"system_log/list": [
        {"name": "homeassistant.components.mqtt", "message": ["login failed password=topsecret"],
         "level": "ERROR", "source": ["x.py", 1], "timestamp": 2, "exception": "", "count": 3,
         "first_occurred": 1},
        {"name": "homeassistant.components.zha", "message": ["meh"], "level": "WARNING",
         "source": ["y.py", 2], "timestamp": 1, "exception": "", "count": 1, "first_occurred": 1},
    ]})
    data = await _call(ws, "get_system_log", {"level": "error"})
    assert data["count"] == 1
    assert "topsecret" not in json.dumps(data)


async def test_list_traces_rejects_bad_domain():
    data = await _call(FakeWS({}), "list_traces", {"domain": "scene"})
    assert "error" in data


async def test_find_triggers_normalizes_target():
    ws = FakeWS({"get_triggers_for_target": ["light.turned_on"]})
    data = await _call(ws, "find_triggers_for_target", {"target": '{"area_id": "kitchen"}'})
    assert data == ["light.turned_on"]
    assert ws.calls[0] == ("get_triggers_for_target", {"target": {"area_id": ["kitchen"]}, "expand_group": True})


async def test_find_triggers_rejects_unknown_key():
    data = await _call(FakeWS({}), "find_triggers_for_target", {"target": '{"zone": ["x"]}'})
    assert "error" in data


def test_summarize_trace_finds_failure():
    trace = {
        "domain": "automation", "item_id": "abc", "run_id": "r1", "state": "stopped",
        "script_execution": "error", "error": "boom", "trigger": "state of sensor.x",
        "trace": {
            "trigger/0": [{"path": "trigger/0"}],
            "condition/0": [{"path": "condition/0", "result": {"result": True}}],
            "action/0": [{"path": "action/0", "result": {}}],
            "action/1": [{"path": "action/1", "error": "Entity not found"}],
        },
    }
    summary = summarize_trace(trace)
    assert summary["failed_step"] == "action/1"
    assert summary["condition_results"] == [{"path": "condition/0", "result": True}]
    assert summary["trigger"] == "state of sensor.x"


async def test_category_crud_payloads():
    ws = FakeWS({
        "config/category_registry/create": {"category_id": "c1", "name": "Lights"},
        "config/entity_registry/update": {"entity_entry": {"categories": {"automation": "c1"}}},
    })
    await _call(ws, "create_category", {"scope": "automation", "name": "Lights"})
    data = await _call(ws, "assign_category", {"entity_id": "automation.x", "scope": "automation", "category_id": "c1"})
    assert data["categories"] == {"automation": "c1"}
    await _call(ws, "assign_category", {"entity_id": "automation.x", "scope": "automation"})
    assert ws.calls[0] == ("config/category_registry/create", {"scope": "automation", "name": "Lights"})
    assert ws.calls[1][1]["categories"] == {"automation": "c1"}
    assert ws.calls[2][1]["categories"] == {"automation": None}


async def test_category_rejects_bad_scope():
    data = await _call(FakeWS({}), "list_categories", {"scope": "../x"})
    assert "error" in data
