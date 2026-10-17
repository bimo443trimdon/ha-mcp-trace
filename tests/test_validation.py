import asyncio

from ha_mcp.util.validation import validate_automation


class FakeWS:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def send_command(self, msg_type, **kwargs):
        self.calls.append((msg_type, kwargs))
        return self.response


def test_validate_automation_sends_plural_keys():
    ws = FakeWS(
        {
            "triggers": {"valid": True, "error": None},
            "conditions": {"valid": True, "error": None},
            "actions": {"valid": True, "error": None},
        }
    )
    config = {"trigger": [{"trigger": "event"}], "conditions": [], "actions": [{"delay": 1}]}

    result = asyncio.run(validate_automation(ws, config))

    assert result["valid"] is True
    msg_type, payload = ws.calls[0]
    assert msg_type == "validate_config"
    assert set(payload) == {"triggers", "conditions", "actions"}
    assert payload["triggers"] == [{"trigger": "event"}]


def test_validate_automation_reports_section_errors():
    ws = FakeWS({"triggers": {"valid": True, "error": None}, "actions": {"valid": False, "error": "bad"}})

    result = asyncio.run(validate_automation(ws, {"triggers": [], "actions": []}))

    assert result["valid"] is False
    assert result["errors"] == ["actions: bad"]
