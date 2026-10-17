"""Integration (config entry) tools: list, reload, enable/disable."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


def register_integration_tools(mcp_server):
    """Register integration / config-entry tools on the MCP server."""

    @mcp_server.tool()
    async def list_integrations(
        ctx: Context, domain: str | None = None
    ) -> str:
        """List configured integrations (config entries).

        Returns each config entry with its entry_id, domain, title, state, and
        whether it is disabled — useful for finding the entry_id needed to
        reload or enable/disable an integration.

        Args:
            domain: Optionally filter to a single integration domain (e.g. 'hue').
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("config_entries/get")
        except Exception as exc:  # noqa: BLE001
            return json.dumps({
                "error": f"Could not list integrations: {exc}",
                "hint": "Expected the 'config_entries/get' WebSocket command on this HA version.",
            })
        if domain:
            result = [e for e in result if e.get("domain") == domain]
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def reload_integration(
        ctx: Context, entry_id: str
    ) -> str:
        """Reload an integration (config entry) by its entry_id.

        Use ``list_integrations`` to find the entry_id. Reloading re-runs the
        integration's setup without restarting Home Assistant.

        Args:
            entry_id: The config entry id to reload.
        """
        _ws, rest = get_clients(ctx)
        if not await confirm_change(
            ctx=ctx, action="RELOAD", entity_type="integration",
            identifier=entry_id, config={"entry_id": entry_id},
        ):
            return json.dumps({"status": "cancelled", "message": "Reload cancelled."})

        try:
            result = await rest.reload_config_entry(entry_id)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({
                "error": f"Could not reload integration: {exc}",
                "hint": "Check the entry_id via list_integrations; the entry must be loaded.",
            })
        return json.dumps({"status": "reloaded", "entry_id": entry_id, "result": result})

    @mcp_server.tool()
    async def set_integration_enabled(
        ctx: Context, entry_id: str, enabled: bool
    ) -> str:
        """Enable or disable an integration (config entry).

        Disabling unloads the integration and its entities; enabling reloads it.

        Args:
            entry_id: The config entry id.
            enabled: True to enable, False to disable.
        """
        _ws, rest = get_clients(ctx)
        action = "ENABLE" if enabled else "DISABLE"
        if not await confirm_change(
            ctx=ctx, action=action, entity_type="integration",
            identifier=entry_id, config={"entry_id": entry_id, "enabled": enabled},
        ):
            return json.dumps({"status": "cancelled", "message": f"{action.title()} cancelled."})

        disabled_by = None if enabled else "user"
        try:
            result = await rest.set_config_entry_disabled(entry_id, disabled_by)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({
                "error": f"Could not change integration state: {exc}",
                "hint": (
                    "This uses POST /api/config/config_entries/entry/{id}/disable. "
                    "If unsupported on this HA version, toggle the integration in the UI."
                ),
            })
        return json.dumps({
            "status": "enabled" if enabled else "disabled",
            "entry_id": entry_id,
            "result": result,
        })
