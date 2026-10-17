"""Tests for helper and backup tools against a fake HA WebSocket client."""

import json

import pytest

from ha_mcp.tools.backup import register_backup_tools
from ha_mcp.tools.helper import register_helper_tools


class _Collector:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class _FakeWS:
    def __init__(self, responses):
        self.responses = responses
        self.sent = []

    async def send_command(self, msg_type, **kwargs):
        self.sent.append((msg_type, kwargs))
        response = self.responses.get(msg_type)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeRest:
    def __init__(self, states=None):
        self.states = states or []

    async def get_states(self):
        return self.states


class _Ctx:
    def __init__(self, ws, rest=None):
        self.lifespan_context = {"ws": ws, "rest": rest or _FakeRest()}


def _tools(register):
    collector = _Collector()
    register(collector)
    return collector.tools


COUNTER_ITEM = {"id": "visitors_1", "name": "Visitors", "initial": 5, "step": 2, "restore": True}


async def test_update_helper_resolves_storage_id_and_preserves_fields():
    ws = _FakeWS({
        "config/entity_registry/get": {"entity_id": "counter.visitors", "unique_id": "visitors_1"},
        "counter/list": [COUNTER_ITEM],
        "counter/update": {"id": "visitors_1", "name": "Guests"},
    })
    tools = _tools(register_helper_tools)

    result = json.loads(await tools["update_helper"](
        _Ctx(ws), "counter", "counter.visitors", '{"name": "Guests", "id": "evil", "type": "x"}'
    ))

    assert result["status"] == "updated"
    msg_type, payload = ws.sent[-1]
    assert msg_type == "counter/update"
    assert payload == {
        "name": "Guests", "initial": 5, "step": 2, "restore": True, "counter_id": "visitors_1",
    }


async def test_update_helper_rejects_yaml_helper():
    ws = _FakeWS({
        "config/entity_registry/get": {"entity_id": "input_boolean.yaml", "unique_id": None},
        "input_boolean/list": [{"id": "other"}],
    })
    tools = _tools(register_helper_tools)

    result = json.loads(await tools["update_helper"](
        _Ctx(ws), "input_boolean", "input_boolean.yaml", '{"name": "x"}'
    ))

    assert "YAML" in result["error"]
    assert not any(t == "input_boolean/update" for t, _ in ws.sent)


async def test_delete_helper_uses_storage_id():
    ws = _FakeWS({
        "config/entity_registry/get": {"unique_id": "visitors_1"},
        "counter/list": [COUNTER_ITEM],
        "counter/delete": None,
    })
    tools = _tools(register_helper_tools)

    result = json.loads(await tools["delete_helper"](_Ctx(ws), "counter", "counter.visitors"))

    assert result["status"] == "deleted"
    assert ws.sent[-1] == ("counter/delete", {"counter_id": "visitors_1"})


async def test_delete_helper_domain_mismatch():
    tools = _tools(register_helper_tools)
    result = json.loads(await tools["delete_helper"](_Ctx(_FakeWS({})), "timer", "counter.x"))
    assert "does not match" in result["error"]


async def test_create_helper_strips_reserved_keys():
    ws = _FakeWS({"timer/create": {"id": "t1"}})
    tools = _tools(register_helper_tools)

    await tools["create_helper"](
        _Ctx(ws), "timer", '{"name": "Tea", "duration": "00:04:00", "type": "auth", "id": "1"}'
    )

    assert ws.sent[-1] == ("timer/create", {"name": "Tea", "duration": "00:04:00"})


async def test_create_backup_uses_automatic_settings_when_configured():
    ws = _FakeWS({
        "backup/config/info": {"config": {"create_backup": {"agent_ids": ["backup.local"]}}},
        "backup/generate_with_automatic_settings": {"backup_job_id": "j1"},
    })
    tools = _tools(register_backup_tools)

    result = json.loads(await tools["create_backup"](_Ctx(ws)))

    assert result["status"] == "started"
    assert ws.sent[-1] == ("backup/generate_with_automatic_settings", {})


async def test_create_backup_falls_back_to_local_agent():
    ws = _FakeWS({
        "backup/config/info": {"config": {"create_backup": {"agent_ids": []}}},
        "backup/agents/info": {"agents": [
            {"agent_id": "cloud.cloud", "name": "Cloud"},
            {"agent_id": "backup.local", "name": "Local"},
        ]},
        "backup/generate": {"backup_job_id": "j2"},
    })
    tools = _tools(register_backup_tools)

    await tools["create_backup"](_Ctx(ws), name="pre-change")

    assert ws.sent[-1] == (
        "backup/generate",
        {"agent_ids": ["backup.local"], "include_database": True, "name": "pre-change"},
    )


async def test_create_backup_explicit_agents():
    ws = _FakeWS({"backup/generate": {"backup_job_id": "j3"}})
    tools = _tools(register_backup_tools)

    await tools["create_backup"](_Ctx(ws), agent_ids=["cloud.cloud"], include_database=False)

    assert ws.sent == [(
        "backup/generate", {"agent_ids": ["cloud.cloud"], "include_database": False},
    )]


async def test_get_backup_config_redacts_password():
    ws = _FakeWS({"backup/config/info": {"config": {
        "create_backup": {"agent_ids": ["backup.local"], "password": "hunter2"},
    }}})
    tools = _tools(register_backup_tools)

    result = await tools["get_backup_config"](_Ctx(ws))

    assert "hunter2" not in result
    assert json.loads(result)["config"]["create_backup"]["password"] == "***"


async def test_update_backup_config_sends_changes():
    ws = _FakeWS({"backup/config/update": None})
    tools = _tools(register_backup_tools)

    result = json.loads(await tools["update_backup_config"](
        _Ctx(ws), '{"retention": {"copies": 7}, "type": "x"}'
    ))

    assert result["status"] == "updated"
    assert ws.sent == [("backup/config/update", {"retention": {"copies": 7}})]


async def test_delete_backup_not_found():
    ws = _FakeWS({"backup/details": {"backup": None, "agent_errors": {}}})
    tools = _tools(register_backup_tools)

    result = json.loads(await tools["delete_backup"](_Ctx(ws), "abc"))

    assert "not found" in result["error"]
    assert not any(t == "backup/delete" for t, _ in ws.sent)


async def test_list_backups_summarizes():
    ws = _FakeWS({"backup/info": {
        "state": "idle",
        "backups": [{
            "backup_id": "b1", "name": "Nightly", "date": "2026-10-10T03:00:00",
            "agents": {"backup.local": {"size": 1024, "protected": False}},
        }],
        "agent_errors": {},
    }})
    tools = _tools(register_backup_tools)

    result = json.loads(await tools["list_backups"](_Ctx(ws)))

    assert result["state"] == "idle"
    assert result["backups"][0]["agents"]["backup.local"]["size"] == 1024


@pytest.mark.parametrize("bad", ["[1]", "not json"])
async def test_update_backup_config_rejects_bad_json(bad):
    tools = _tools(register_backup_tools)
    result = json.loads(await tools["update_backup_config"](_Ctx(_FakeWS({})), bad))
    assert "error" in result
