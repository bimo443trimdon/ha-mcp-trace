"""Registry tools for querying Home Assistant device, entity, area, floor, and label registries."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients

logger = logging.getLogger(__name__)


def register_registry_tools(mcp_server):
    """Register all registry-related tools with the MCP server."""

    @mcp_server.tool()
    async def list_devices(
        ctx: Context,
        area_id: str | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
    ) -> str:
        """List all devices registered in Home Assistant with optional filters.

        Args:
            area_id: Filter by area ID.
            manufacturer: Filter by manufacturer name (case-insensitive).
            model: Filter by device model (case-insensitive).
        """
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/device_registry/list")
        devices = result

        if area_id:
            devices = [d for d in devices if d.get("area_id") == area_id]
        if manufacturer:
            devices = [
                d
                for d in devices
                if (d.get("manufacturer") or "").lower() == manufacturer.lower()
            ]
        if model:
            devices = [
                d
                for d in devices
                if (d.get("model") or "").lower() == model.lower()
            ]

        return json.dumps(devices, indent=2)

    @mcp_server.tool()
    async def list_entities(
        ctx: Context,
        domain: str | None = None,
        device_id: str | None = None,
        area_id: str | None = None,
    ) -> str:
        """List all entities registered in Home Assistant with optional filters.

        Args:
            domain: Filter by domain (prefix match on entity_id, e.g. 'light', 'switch').
            device_id: Filter by device ID.
            area_id: Filter by area ID.
        """
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/entity_registry/list")
        entities = result

        if domain:
            prefix = domain if domain.endswith(".") else domain + "."
            entities = [
                e for e in entities if (e.get("entity_id") or "").startswith(prefix)
            ]
        if device_id:
            entities = [e for e in entities if e.get("device_id") == device_id]
        if area_id:
            entities = [e for e in entities if e.get("area_id") == area_id]

        return json.dumps(entities, indent=2)

    @mcp_server.tool()
    async def list_areas(ctx: Context) -> str:
        """List all areas registered in Home Assistant."""
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/area_registry/list")
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def list_floors(ctx: Context) -> str:
        """List all floors registered in Home Assistant."""
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/floor_registry/list")
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def list_labels(ctx: Context) -> str:
        """List all labels registered in Home Assistant."""
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/label_registry/list")
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def get_entity_details(ctx: Context, entity_id: str) -> str:
        """Get detailed information about a specific entity combining registry data and live state.

        Args:
            entity_id: The entity ID to look up (e.g. 'light.living_room').
        """
        ws, rest = get_clients(ctx)

        # Get registry info for all entities and find the matching one
        registry_list = await ws.send_command("config/entity_registry/list")
        registry_entry = None
        for entry in registry_list:
            if entry.get("entity_id") == entity_id:
                registry_entry = entry
                break

        # Get live state via REST API
        live_state = await rest.get_state(entity_id)

        combined = {
            "entity_id": entity_id,
            "registry": registry_entry,
            "state": live_state,
        }

        return json.dumps(combined, indent=2)

    @mcp_server.tool()
    async def search_entities(
        ctx: Context,
        query: str,
        domain: str | None = None,
    ) -> str:
        """Search entities by name, ID, or attributes using case-insensitive substring matching.

        Args:
            query: Search string to match against entity IDs, names, and attributes.
            domain: Optionally restrict search to a specific domain (e.g. 'light', 'switch').
        """
        ws, rest = get_clients(ctx)
        result = await ws.send_command("config/entity_registry/list")
        entities = result

        # Optionally filter by domain first
        if domain:
            prefix = domain if domain.endswith(".") else domain + "."
            entities = [
                e for e in entities if (e.get("entity_id") or "").startswith(prefix)
            ]

        # Fuzzy search: case-insensitive substring match on entity_id, name, and
        # original_name fields
        query_lower = query.lower()
        matches = []
        for entity in entities:
            entity_id = (entity.get("entity_id") or "").lower()
            name = (entity.get("name") or "").lower()
            original_name = (entity.get("original_name") or "").lower()

            if (
                query_lower in entity_id
                or query_lower in name
                or query_lower in original_name
            ):
                matches.append(entity)

        return json.dumps(matches, indent=2)
