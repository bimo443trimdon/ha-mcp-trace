"""Remove entities and devices from the Home Assistant registries."""

import json
import logging
from typing import Any

from fastmcp import Context

from ha_mcp.ha_client.models import HAError
from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)

ENTITY_PREVIEW_KEYS = ("entity_id", "name", "original_name", "platform", "device_id", "config_entry_id", "disabled_by")
DEVICE_PREVIEW_KEYS = ("id", "name", "name_by_user", "manufacturer", "model", "area_id", "config_entry_id", "config_entries")


def _device_entry_ids(device: dict) -> list[str]:
    if device.get("config_entries"):
        return list(device["config_entries"])
    return [device["config_entry_id"]] if device.get("config_entry_id") else []


def register_registry_remove_tools(mcp_server):
    """Register registry removal tools on the MCP server."""

    @mcp_server.tool()
    async def remove_entity(ctx: Context, entity_id: str) -> str:
        """Remove an entity from the entity registry.

        Intended for orphaned/stale entities (integration removed, entity shown
        as unavailable/"not provided"). An entity that is still provided by a
        loaded integration will simply be re-created by it; to get rid of those,
        disable the entity (update_entity) or delete the integration's config
        entry (delete_config_entry). HA's error is returned verbatim on failure.

        Args:
            entity_id: The entity id, e.g. 'sensor.old_temperature'.
        """
        ws, _rest = get_clients(ctx)
        try:
            entry = await ws.send_command("config/entity_registry/get", entity_id=entity_id)
        except HAError as exc:
            return json.dumps({"error": str(exc)})
        entry = entry if isinstance(entry, dict) else {}
        preview = {k: entry.get(k) for k in ENTITY_PREVIEW_KEYS}

        if not await confirm_change(ctx, "REMOVE", "entity", entity_id, preview):
            return json.dumps({"status": "cancelled"})

        try:
            await ws.send_command("config/entity_registry/remove", entity_id=entity_id)
        except HAError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "removed", "entity": preview}, indent=2, default=str)

    @mcp_server.tool()
    async def remove_device(ctx: Context, device_id: str) -> str:
        """Remove a device and its entities from Home Assistant.

        Only works when the owning integration supports device removal (the
        "Delete" button in the device page); otherwise HA rejects it, and the
        alternative is deleting the integration's config entry. Use
        list_devices / search to find the device_id.

        Args:
            device_id: The device registry id.
        """
        ws, _rest = get_clients(ctx)
        try:
            devices = await ws.send_command("config/device_registry/list")
        except HAError as exc:
            return json.dumps({"error": str(exc)})
        device = next((d for d in devices or [] if d.get("id") == device_id), None)
        if device is None:
            return json.dumps({"error": f"Device {device_id} not found"})
        preview: dict[str, Any] = {k: device.get(k) for k in DEVICE_PREVIEW_KEYS if k in device}

        if not await confirm_change(ctx, "REMOVE", "device", device.get("name_by_user") or device.get("name") or device_id, preview):
            return json.dumps({"status": "cancelled"})

        try:
            await ws.send_command("config/device_registry/remove", device_id=device_id)
        except HAError as exc:
            if "unknown_command" not in str(exc):
                return json.dumps({"error": str(exc)})
            # Before HA 2026.9 only the per-config-entry removal exists; the device
            # is deleted once its last config entry is detached.
            try:
                for entry_id in _device_entry_ids(device):
                    await ws.send_command(
                        "config/device_registry/remove_config_entry",
                        device_id=device_id,
                        config_entry_id=entry_id,
                    )
            except HAError as fallback_exc:
                return json.dumps({"error": str(fallback_exc)})
        return json.dumps({"status": "removed", "device": preview}, indent=2, default=str)
