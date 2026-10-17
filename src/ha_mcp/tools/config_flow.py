"""Integration and helper setup through Home Assistant data entry flows.

Covers config flows (adding or reconfiguring an integration or a config-flow
helper), options flows (changing an existing entry's options) and subentry
flows (adding sub-items to an entry), plus ignoring discoveries and deleting
config entries.
"""

import json
import logging
from typing import Any

from fastmcp import Context

from ha_mcp.ha_client.models import HAError
from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)

SENSITIVE_KEY_PARTS = (
    "password", "passwd", "token", "secret", "api_key", "apikey",
    "access_key", "private_key", "client_secret", "pin",
)
REDACTED = "**REDACTED**"
FLOW_KINDS = ("config", "options", "subentry")

NEXT_STEP_HINTS = {
    "form": (
        "Fill in the fields from data_schema (respect 'required' and selector "
        "types) and call the matching continue_* tool with them as user_input. "
        "If 'errors' is set, fix those fields and resubmit."
    ),
    "menu": (
        "Pick one of menu_options and call the matching continue_* tool with "
        'user_input {"next_step_id": "<option>"}.'
    ),
    "create_entry": "Done: the entry was created/updated. Nothing more to submit.",
    "abort": "The flow ended without creating anything; see 'reason'.",
    "external": (
        "This step must be completed by the user in a browser (e.g. OAuth "
        "login) through the Home Assistant UI. Ask the user to finish it there, "
        "then call get_config_flow to check progress."
    ),
    "external_done": "The external step finished; call the continue_* tool with empty user_input.",
    "show_progress": "HA is working in the background; call get_config_flow again shortly.",
    "show_progress_done": "Progress finished; call the continue_* tool with empty user_input.",
}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Recursively mask values whose key looks like a credential."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _is_sensitive(k) and v not in (None, "") else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def _flow_response(result: Any) -> str:
    if isinstance(result, dict):
        result = redact(result)
        hint = NEXT_STEP_HINTS.get(str(result.get("type")))
        if hint:
            result["next_step_hint"] = hint
    return json.dumps(result, indent=2, default=str)


def _error(exc: Exception) -> str:
    return json.dumps({"error": str(exc)})


def _parse_input(user_input: str | None) -> dict:
    if not user_input:
        return {}
    parsed = json.loads(user_input)
    if not isinstance(parsed, dict):
        raise ValueError("user_input must be a JSON object.")
    return parsed


def _check_kind(flow_kind: str) -> None:
    if flow_kind not in FLOW_KINDS:
        raise ValueError(f"flow_kind must be one of: {', '.join(FLOW_KINDS)}")


def register_config_flow_tools(mcp_server):
    """Register data-entry-flow tools on the MCP server."""

    async def _continue(ctx: Context, flow_kind: str, flow_id: str, user_input: str | None) -> str:
        try:
            _check_kind(flow_kind)
            data = _parse_input(user_input)
        except (ValueError, json.JSONDecodeError) as exc:
            return _error(exc)

        if not await confirm_change(
            ctx, "SUBMIT", f"{flow_kind} flow step", flow_id, redact(data) or {"user_input": {}},
        ):
            return json.dumps({"status": "cancelled"})

        _ws, rest = get_clients(ctx)
        try:
            return _flow_response(await rest.continue_flow(flow_kind, flow_id, data))
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def list_config_flow_handlers(ctx: Context, handler_type: str = "integration") -> str:
        """List the domains that can be set up through a config flow.

        Args:
            handler_type: 'integration' for integrations, 'helper' for
                config-flow helpers (template, group, utility_meter, threshold,
                derivative, ...), or 'all'.

        Pass a returned domain as `handler` to start_config_flow.
        """
        _ws, rest = get_clients(ctx)
        try:
            handlers = await rest.get_flow_handlers(None if handler_type == "all" else handler_type)
        except HAError as exc:
            return _error(exc)
        return json.dumps({"count": len(handlers), "handlers": handlers}, indent=2)

    @mcp_server.tool()
    async def list_config_flows_in_progress(ctx: Context) -> str:
        """List config flows currently in progress, including discovered devices.

        Entries with context.source 'zeroconf', 'ssdp', 'dhcp', 'bluetooth',
        'usb', 'homekit', 'mqtt' etc. are discoveries waiting for setup: continue
        them with continue_config_flow (via their flow_id) or dismiss them with
        ignore_config_flow.
        """
        ws, _rest = get_clients(ctx)
        try:
            flows = await ws.send_command("config_entries/flow/progress")
        except HAError as exc:
            return _error(exc)
        return json.dumps(redact(flows), indent=2, default=str)

    @mcp_server.tool()
    async def start_config_flow(ctx: Context, handler: str, entry_id: str | None = None) -> str:
        """Start setting up an integration or config-flow helper.

        This is the first step of the setup loop:
          1. start_config_flow(handler) returns the first step.
          2. For type 'form', read data_schema (fields, required flags,
             selectors) and description_placeholders, then call
             continue_config_flow(flow_id, user_input) with the values.
             Ask the user for credentials rather than guessing them.
          3. Repeat until type is 'create_entry' (done) or 'abort' (see reason).
          Type 'menu' means choose a next_step_id; 'external' means the user
          must finish the step (e.g. OAuth) in the Home Assistant UI.

        Args:
            handler: Integration/helper domain from list_config_flow_handlers
                (e.g. 'hue', 'mqtt', 'template', 'utility_meter').
            entry_id: Pass an existing config entry id to start a reconfigure
                flow for that entry instead of adding a new one.
        """
        payload: dict[str, Any] = {"handler": handler}
        if entry_id:
            payload["entry_id"] = entry_id

        if not await confirm_change(
            ctx, "START", "config flow", handler, payload,
        ):
            return json.dumps({"status": "cancelled"})

        _ws, rest = get_clients(ctx)
        try:
            return _flow_response(await rest.start_flow("config", payload))
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def continue_config_flow(ctx: Context, flow_id: str, user_input: str | None = None) -> str:
        """Submit the current step of a config flow.

        Args:
            flow_id: The flow_id returned by start_config_flow or
                list_config_flows_in_progress.
            user_input: JSON object with the values for the current step's
                data_schema fields (e.g. '{"host": "192.168.1.20"}'). For a
                menu step use '{"next_step_id": "<option>"}'. Omit for steps
                without fields.

        Returns the next step; keep going until type is 'create_entry' or 'abort'.
        """
        return await _continue(ctx, "config", flow_id, user_input)

    @mcp_server.tool()
    async def get_config_flow(ctx: Context, flow_id: str, flow_kind: str = "config") -> str:
        """Get the current step of a flow without submitting anything.

        Args:
            flow_id: The flow id.
            flow_kind: 'config', 'options' or 'subentry'.
        """
        try:
            _check_kind(flow_kind)
        except ValueError as exc:
            return _error(exc)
        _ws, rest = get_clients(ctx)
        try:
            return _flow_response(await rest.get_flow(flow_kind, flow_id))
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def abort_config_flow(ctx: Context, flow_id: str, flow_kind: str = "config") -> str:
        """Cancel a flow in progress.

        Args:
            flow_id: The flow id.
            flow_kind: 'config', 'options' or 'subentry'.
        """
        try:
            _check_kind(flow_kind)
        except ValueError as exc:
            return _error(exc)

        if not await confirm_change(
            ctx, "ABORT", f"{flow_kind} flow", flow_id, {"flow_id": flow_id},
        ):
            return json.dumps({"status": "cancelled"})

        _ws, rest = get_clients(ctx)
        try:
            return json.dumps(await rest.abort_flow(flow_kind, flow_id), default=str)
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def start_options_flow(ctx: Context, entry_id: str) -> str:
        """Start changing the options of an existing integration/helper entry.

        Use list_integrations to find the entry_id (entries with
        supports_options true). Then loop with continue_options_flow exactly
        like a config flow until type is 'create_entry' or 'abort'.
        """
        payload = {"handler": entry_id}
        if not await confirm_change(
            ctx, "START", "options flow", entry_id, payload,
        ):
            return json.dumps({"status": "cancelled"})

        _ws, rest = get_clients(ctx)
        try:
            return _flow_response(await rest.start_flow("options", payload))
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def continue_options_flow(ctx: Context, flow_id: str, user_input: str | None = None) -> str:
        """Submit the current step of an options flow.

        Args:
            flow_id: The flow_id returned by start_options_flow.
            user_input: JSON object with values for the step's data_schema.
        """
        return await _continue(ctx, "options", flow_id, user_input)

    @mcp_server.tool()
    async def list_config_subentries(ctx: Context, entry_id: str) -> str:
        """List the subentries of a config entry (e.g. per-agent or per-location items).

        Returns subentry_id, subentry_type, title and unique_id for each.
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("config_entries/subentries/list", entry_id=entry_id)
        except HAError as exc:
            return _error(exc)
        return json.dumps(result, indent=2, default=str)

    @mcp_server.tool()
    async def start_subentry_flow(
        ctx: Context, entry_id: str, subentry_type: str, subentry_id: str | None = None
    ) -> str:
        """Start a flow that adds (or reconfigures) a subentry of a config entry.

        Args:
            entry_id: The parent config entry id.
            subentry_type: One of the entry's supported_subentry_types (see
                list_integrations / config entry details).
            subentry_id: Pass an existing subentry id to reconfigure it.

        Continue with continue_subentry_flow until 'create_entry' or 'abort'.
        """
        payload: dict[str, Any] = {"handler": [entry_id, subentry_type]}
        if subentry_id:
            payload["subentry_id"] = subentry_id

        if not await confirm_change(
            ctx, "START", "subentry flow", f"{entry_id}/{subentry_type}", payload,
        ):
            return json.dumps({"status": "cancelled"})

        _ws, rest = get_clients(ctx)
        try:
            return _flow_response(await rest.start_flow("subentry", payload))
        except HAError as exc:
            return _error(exc)

    @mcp_server.tool()
    async def continue_subentry_flow(ctx: Context, flow_id: str, user_input: str | None = None) -> str:
        """Submit the current step of a subentry flow.

        Args:
            flow_id: The flow_id returned by start_subentry_flow.
            user_input: JSON object with values for the step's data_schema.
        """
        return await _continue(ctx, "subentry", flow_id, user_input)

    @mcp_server.tool()
    async def ignore_config_flow(ctx: Context, flow_id: str, title: str) -> str:
        """Ignore a discovered device/integration so HA stops offering it.

        Only works for discovery flows that have a unique_id. The ignored entry
        can later be removed with delete_config_entry to rediscover it.

        Args:
            flow_id: The flow id from list_config_flows_in_progress.
            title: Title for the ignored entry (usually the discovery's title).
        """
        if not await confirm_change(
            ctx, "IGNORE", "discovered flow", flow_id, {"flow_id": flow_id, "title": title},
        ):
            return json.dumps({"status": "cancelled"})

        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("config_entries/ignore_flow", flow_id=flow_id, title=title)
        except HAError as exc:
            return _error(exc)
        return json.dumps({"status": "ignored", "result": result}, default=str)

    @mcp_server.tool()
    async def delete_config_entry(ctx: Context, entry_id: str) -> str:
        """Delete a config entry: removes the integration instance with its devices and entities.

        This cannot be undone; re-adding requires a new config flow. Use
        list_integrations to find the entry_id and confirm the title/domain
        with the user first.

        Returns HA's result, including require_restart when a restart is needed.
        """
        ws, rest = get_clients(ctx)
        preview: dict[str, Any] = {"entry_id": entry_id}
        try:
            entry = await ws.send_command("config_entries/get_single", entry_id=entry_id)
            if isinstance(entry, dict):
                entry = entry.get("config_entry", entry)
                preview.update({k: entry.get(k) for k in ("domain", "title", "state", "source")})
        except HAError as exc:
            logger.debug("Could not load config entry %s for preview: %s", entry_id, exc)

        if not await confirm_change(ctx, "DELETE", "config entry", entry_id, preview):
            return json.dumps({"status": "cancelled"})

        try:
            result = await rest.delete_config_entry(entry_id)
        except HAError as exc:
            return _error(exc)
        return json.dumps({"status": "deleted", "entry": preview, "result": result}, indent=2, default=str)
