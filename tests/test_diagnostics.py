import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ha_mcp.tools.categories import register_category_tools
from ha_mcp.tools.diagnostics import register_diagnostics_tools, summarize_trace
from ha_mcp.tools import classify_tool
from ha_mcp.util.redact import redact, tail


class FakeWS:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def send_command(self, msg_type, **kwargs):
        self.calls.append((msg_type, kwargs))
        return self.responses.get(msg_type)


def _server(ws, rest=None):
    @asynccontextmanager
    async def lifespan(_server):
        yield {"ws": ws, "rest": rest}

    mcp = FastMCP("t", lifespan=lifespan)
    register_diagnostics_tools(mcp)
    register_category_tools(mcp)
    return mcp


async def _call(ws, tool, args, rest=None):
    async with Client(_server(ws, rest)) as client:
        result = await client.call_tool(tool, args)
    return json.loads(result.content[0].text)


class FakeRest:
    def __init__(self, states, config, history=None, logbook=None):
        self.states = states
        self.config = config
        self.history = history or {}
        self.logbook = logbook or []
        self.history_calls = []
        self.logbook_calls = []
        self.config_calls = []

    async def get_states(self):
        return self.states

    async def get_automation_config(self, automation_id):
        self.config_calls.append(automation_id)
        return self.config

    async def get_history(self, entity_id, start_time, end_time):
        self.history_calls.append((entity_id, start_time, end_time))
        return self.history.get(entity_id, [])

    async def get_logbook(self, entity_id, start_time, end_time):
        self.logbook_calls.append((entity_id, start_time, end_time))
        return self.logbook


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


async def test_automation_diagnosis_reports_trace_failure_and_evidence():
    run_start = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    ws = FakeWS({
        "trace/list": [{
            "run_id": "run-1",
            "timestamp": {"start": run_start},
        }],
        "trace/get": {
            "domain": "automation",
            "item_id": "garage_door",
            "run_id": "run-1",
            "state": "stopped",
            "script_execution": "error",
            "timestamp": {"start": run_start},
            "trace": {
                "condition/0": [{
                    "path": "condition/0",
                    "result": {"result": True},
                }],
                "action/0": [{
                    "path": "action/0",
                    "error": "Service failed",
                }],
            },
        },
    })
    rest = FakeRest(
        states=[{
            "entity_id": "automation.garage_door",
            "state": "on",
            "last_changed": "2026-10-18T04:00:00+00:00",
            "attributes": {"id": "garage_door", "friendly_name": "Garage door"},
        }],
        config={
            "id": "garage_door",
            "alias": "Garage door",
            "triggers": [{"trigger": "state", "entity_id": ["binary_sensor.garage"]}],
            "conditions": [{"condition": "state", "entity_id": "cover.garage"}],
            "actions": [{"action": "cover.open_cover", "target": {"entity_id": "cover.garage"}}],
        },
        history={
            "binary_sensor.garage": [[{
                "state": "on",
                "last_changed": "2026-10-18T04:59:00+00:00",
            }]],
        },
        logbook=[{
            "when": "2026-10-18T05:00:01+00:00",
            "name": "Garage door",
            "entity_id": "automation.garage_door",
            "message": "triggered",
        }],
    )

    data = await _call(
        ws,
        "get_automation_diagnosis",
        {"automation_id": "automation.garage_door"},
        rest,
    )

    assert data["assessment"]["status"] == "execution_error_observed"
    assert data["automation"]["config_id"] == "garage_door"
    assert data["automation"]["state"] == "on"
    assert data["evidence"]["traces_returned"][0]["failed_step"] == "action/0"
    assert data["evidence"]["trigger_entity_ids"] == ["binary_sensor.garage"]
    assert data["evidence"]["condition_entity_ids"] == ["cover.garage"]
    assert data["evidence"]["entity_history"][0]["change_count"] == 1
    assert data["evidence"]["logbook_entries"][0]["message"] == "triggered"
    assert any(
        item["source"] == "Home Assistant logbook"
        for item in data["observations"]
    )
    assert ws.calls[0] == (
        "trace/list",
        {"domain": "automation", "item_id": "garage_door"},
    )
    assert rest.config_calls == ["garage_door"]
    assert rest.logbook_calls[0][0] == "automation.garage_door"


async def test_automation_diagnosis_handles_no_trace_without_claiming_never_ran():
    ws = FakeWS({"trace/list": []})
    rest = FakeRest(
        states=[{
            "entity_id": "automation.garage_door",
            "state": "on",
            "attributes": {"id": "garage_door"},
        }],
        config={
            "id": "garage_door",
            "triggers": [{"trigger": "state", "entity_id": "binary_sensor.garage"}],
        },
        history={"binary_sensor.garage": []},
    )

    data = await _call(
        ws,
        "get_automation_diagnosis",
        {"automation_id": "garage_door"},
        rest,
    )

    assert data["assessment"]["status"] == "no_trace_in_window"
    assert "may not have triggered" in data["assessment"]["hypotheses"][0]
    assert any("cannot establish" in item for item in data["limitations"])
    assert any("No state changes" in item["fact"] for item in data["observations"])
    assert rest.history_calls[0][0] == "binary_sensor.garage"


async def test_automation_diagnosis_identifies_false_condition():
    run_start = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    ws = FakeWS({
        "trace/list": [{
            "run_id": "run-condition",
            "timestamp": {"start": run_start},
        }],
        "trace/get": {
            "domain": "automation",
            "item_id": "garage_door",
            "run_id": "run-condition",
            "script_execution": "failed_conditions",
            "timestamp": {"start": run_start},
            "trace": {
                "condition/0": [{
                    "path": "condition/0",
                    "result": {"result": False},
                }],
            },
        },
    })
    rest = FakeRest(
        states=[{
            "entity_id": "automation.garage_door",
            "state": "on",
            "attributes": {"id": "garage_door"},
        }],
        config={
            "id": "garage_door",
            "conditions": [{"condition": "state", "entity_id": "cover.garage"}],
        },
    )

    data = await _call(
        ws,
        "get_automation_diagnosis",
        {"automation_id": "automation.garage_door"},
        rest,
    )

    assert data["assessment"]["status"] == "condition_blocked"
    assert any(
        "evaluated false" in item["fact"] and item["source"] == "automation trace"
        for item in data["observations"]
    )


async def test_automation_diagnosis_reports_logbook_activity_without_trace():
    ws = FakeWS({"trace/list": []})
    rest = FakeRest(
        states=[{
            "entity_id": "automation.garage_door",
            "state": "on",
            "attributes": {"id": "garage_door"},
        }],
        config={"id": "garage_door", "triggers": [{"trigger": "time"}]},
        logbook=[{
            "when": "2026-10-18T05:00:00+00:00",
            "name": "Garage door",
            "entity_id": "automation.garage_door",
            "message": "triggered",
        }],
    )

    data = await _call(
        ws,
        "get_automation_diagnosis",
        {"automation_id": "automation.garage_door"},
        rest,
    )

    assert data["assessment"]["status"] == "logbook_activity_without_trace"
    assert any(
        item["source"] == "Home Assistant logbook"
        and "triggered" in item["fact"]
        for item in data["observations"]
    )


@pytest.mark.parametrize(
    ("automation_id", "lookback_minutes", "trace_limit", "message"),
    [
        ("", 60, 3, "non-empty"),
        ("automation.garage/door", 60, 3, "non-empty"),
        ("automation.garage_door", 0, 3, "lookback_minutes"),
        ("automation.garage_door", 1441, 3, "lookback_minutes"),
        ("automation.garage_door", 60, 0, "trace_limit"),
        ("automation.garage_door", 60, 6, "trace_limit"),
    ],
)
async def test_automation_diagnosis_validates_bounded_inputs(
    automation_id, lookback_minutes, trace_limit, message
):
    async with Client(_server(FakeWS({}), FakeRest([], {}))) as client:
        with pytest.raises(ToolError, match=message):
            await client.call_tool(
                "get_automation_diagnosis",
                {
                    "automation_id": automation_id,
                    "lookback_minutes": lookback_minutes,
                    "trace_limit": trace_limit,
                },
            )


async def test_automation_diagnosis_is_registered_as_read_only_tool():
    mcp = _server(FakeWS({}))
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(tool for tool in tools if tool.name == "get_automation_diagnosis")
    assert classify_tool(tool.name)["readOnlyHint"] is True


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
