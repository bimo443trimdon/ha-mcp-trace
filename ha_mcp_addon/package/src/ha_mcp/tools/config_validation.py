"""Config validation tools for checking HA configurations, automation configs, and YAML syntax."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.validation import validate_automation
from ha_mcp.util.yaml_util import validate_yaml_syntax, from_yaml

logger = logging.getLogger(__name__)


def register_config_validation_tools(mcp_server):
    """Register all config-validation tools on the MCP server."""

    @mcp_server.tool()
    async def validate_automation_config(ctx: Context, config: str) -> str:
        """Validate an automation configuration against Home Assistant.

        Sends the trigger, condition, and action arrays from the provided
        configuration to Home Assistant's validate_config WebSocket command
        and returns the validation result.

        Parameters:
            config: A JSON string containing an automation object (or part of
                one) with 'triggers', 'conditions' and 'actions' arrays. The
                legacy singular keys 'trigger', 'condition', 'action' also work.

        Returns a JSON object with:
            valid: bool indicating whether the configuration is valid.
            errors: list of error messages.
            warnings: list of warning messages.
        """
        ws, _rest = get_clients(ctx)

        try:
            parsed = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "valid": False,
                "errors": [f"Invalid JSON: {exc}"],
                "warnings": [],
            }, indent=2)

        if not isinstance(parsed, dict):
            return json.dumps({"valid": False, "errors": ["Config must be a JSON object."], "warnings": []})

        return json.dumps(await validate_automation(ws, parsed), indent=2)

    @mcp_server.tool()
    async def check_config(ctx: Context) -> str:
        """Check the Home Assistant core configuration for errors.

        Triggers a full configuration check on the Home Assistant server by
        calling the /api/config/core/check_config REST endpoint. This is the
        same check that runs when you click 'Check Configuration' in the HA UI.

        Returns a JSON object with the check result, typically containing
        'result' ('valid' or 'invalid') and 'errors' fields as reported by
        Home Assistant.
        """
        _ws, rest = get_clients(ctx)

        try:
            result = await rest.check_config()
        except Exception as exc:
            logger.error("check_config REST call failed: %s", exc)
            return json.dumps({
                "result": "error",
                "errors": str(exc),
            }, indent=2)

        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def validate_yaml(ctx: Context, yaml_text: str) -> str:
        """Validate YAML syntax without connecting to Home Assistant.

        Performs a pure syntax check on the provided YAML text and, if valid,
        also returns the parsed data structure.

        Parameters:
            yaml_text: The raw YAML string to validate.

        Returns a JSON object with:
            valid: bool indicating whether the YAML syntax is correct.
            error: error message string if invalid, null if valid.
            parsed: the parsed YAML data structure if valid, null if invalid.
        """
        is_valid, error_msg = validate_yaml_syntax(yaml_text)

        if not is_valid:
            return json.dumps({
                "valid": False,
                "error": error_msg,
                "parsed": None,
            }, indent=2)

        try:
            parsed = from_yaml(yaml_text)
        except Exception as exc:
            return json.dumps({
                "valid": False,
                "error": str(exc),
                "parsed": None,
            }, indent=2)

        return json.dumps({
            "valid": True,
            "error": None,
            "parsed": parsed,
        }, indent=2)
