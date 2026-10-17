"""Registry mutation tools for areas, floors, labels, devices, and entities.

These complement the read-only registry tools in ``registry.py`` by allowing
creation, renaming, organisation (area/floor/label assignment), and removal of
registry entries via the Home Assistant WebSocket API. All mutations go through
the shared dry-run + confirm flow.
"""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


def _drop_none(data: dict) -> dict:
    """Return a copy of *data* without keys whose value is ``None``."""
    return {k: v for k, v in data.items() if v is not None}


def register_registry_edit_tools(mcp_server):
    """Register registry mutation tools on the MCP server."""

    # ------------------------------------------------------------------
    # Areas
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def create_area(
        ctx: Context,
        name: str,
        floor_id: str | None = None,
        icon: str | None = None,
        labels: list[str] | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Create a new area in the area registry.

        Args:
            name: Display name for the area (e.g. 'Living Room').
            floor_id: Optional floor to place the area on.
            icon: Optional MDI icon (e.g. 'mdi:sofa').
            labels: Optional list of label IDs to attach.
            aliases: Optional list of voice-assistant aliases.
        """
        ws, _rest = get_clients(ctx)
        payload = _drop_none(
            {
                "name": name,
                "floor_id": floor_id,
                "icon": icon,
                "labels": labels,
                "aliases": aliases,
            }
        )

        if not await confirm_change(
            ctx=ctx, action="CREATE", entity_type="area",
            identifier=name, config=payload,
        ):
            return json.dumps({"status": "cancelled", "message": "Area creation cancelled."})

        result = await ws.send_command("config/area_registry/create", **payload)
        return json.dumps({"status": "created", "area": result}, indent=2)

    @mcp_server.tool()
    async def update_area(
        ctx: Context,
        area_id: str,
        name: str | None = None,
        floor_id: str | None = None,
        icon: str | None = None,
        labels: list[str] | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Update an existing area (rename, move to a floor, set icon/labels).

        Args:
            area_id: The area to update.
            name: New display name.
            floor_id: New floor assignment.
            icon: New MDI icon.
            labels: Replacement list of label IDs.
            aliases: Replacement list of voice aliases.
        """
        ws, _rest = get_clients(ctx)
        changes = _drop_none(
            {
                "name": name,
                "floor_id": floor_id,
                "icon": icon,
                "labels": labels,
                "aliases": aliases,
            }
        )
        if not changes:
            return json.dumps({"error": "No fields provided to update."})

        if not await confirm_change(
            ctx=ctx, action="UPDATE", entity_type="area",
            identifier=area_id, config=changes,
        ):
            return json.dumps({"status": "cancelled", "message": "Area update cancelled."})

        result = await ws.send_command(
            "config/area_registry/update", area_id=area_id, **changes
        )
        return json.dumps({"status": "updated", "area": result}, indent=2)

    @mcp_server.tool()
    async def delete_area(
        ctx: Context, area_id: str
    ) -> str:
        """Delete an area from the registry.

        Args:
            area_id: The area to delete.
        """
        ws, _rest = get_clients(ctx)
        if not await confirm_change(
            ctx=ctx, action="DELETE", entity_type="area",
            identifier=area_id, config={"area_id": area_id},
        ):
            return json.dumps({"status": "cancelled", "message": "Area deletion cancelled."})

        await ws.send_command("config/area_registry/delete", area_id=area_id)
        return json.dumps({"status": "deleted", "area_id": area_id})

    # ------------------------------------------------------------------
    # Floors
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def create_floor(
        ctx: Context,
        name: str,
        level: int | None = None,
        icon: str | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Create a new floor in the floor registry.

        Args:
            name: Display name (e.g. 'Ground Floor').
            level: Optional numeric level for ordering (0 = ground).
            icon: Optional MDI icon.
            aliases: Optional list of voice aliases.
        """
        ws, _rest = get_clients(ctx)
        payload = _drop_none(
            {"name": name, "level": level, "icon": icon, "aliases": aliases}
        )
        if not await confirm_change(
            ctx=ctx, action="CREATE", entity_type="floor",
            identifier=name, config=payload,
        ):
            return json.dumps({"status": "cancelled", "message": "Floor creation cancelled."})

        result = await ws.send_command("config/floor_registry/create", **payload)
        return json.dumps({"status": "created", "floor": result}, indent=2)

    @mcp_server.tool()
    async def update_floor(
        ctx: Context,
        floor_id: str,
        name: str | None = None,
        level: int | None = None,
        icon: str | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Update an existing floor (rename, set level/icon/aliases).

        Args:
            floor_id: The floor to update.
            name: New display name.
            level: New numeric level.
            icon: New MDI icon.
            aliases: Replacement list of voice aliases.
        """
        ws, _rest = get_clients(ctx)
        changes = _drop_none(
            {"name": name, "level": level, "icon": icon, "aliases": aliases}
        )
        if not changes:
            return json.dumps({"error": "No fields provided to update."})

        if not await confirm_change(
            ctx=ctx, action="UPDATE", entity_type="floor",
            identifier=floor_id, config=changes,
        ):
            return json.dumps({"status": "cancelled", "message": "Floor update cancelled."})

        result = await ws.send_command(
            "config/floor_registry/update", floor_id=floor_id, **changes
        )
        return json.dumps({"status": "updated", "floor": result}, indent=2)

    @mcp_server.tool()
    async def delete_floor(
        ctx: Context, floor_id: str
    ) -> str:
        """Delete a floor from the registry.

        Args:
            floor_id: The floor to delete.
        """
        ws, _rest = get_clients(ctx)
        if not await confirm_change(
            ctx=ctx, action="DELETE", entity_type="floor",
            identifier=floor_id, config={"floor_id": floor_id},
        ):
            return json.dumps({"status": "cancelled", "message": "Floor deletion cancelled."})

        await ws.send_command("config/floor_registry/delete", floor_id=floor_id)
        return json.dumps({"status": "deleted", "floor_id": floor_id})

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def create_label(
        ctx: Context,
        name: str,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a new label in the label registry.

        Args:
            name: Display name (e.g. 'Security').
            color: Optional color name (e.g. 'red', 'blue') or theme color.
            icon: Optional MDI icon.
            description: Optional free-text description.
        """
        ws, _rest = get_clients(ctx)
        payload = _drop_none(
            {"name": name, "color": color, "icon": icon, "description": description}
        )
        if not await confirm_change(
            ctx=ctx, action="CREATE", entity_type="label",
            identifier=name, config=payload,
        ):
            return json.dumps({"status": "cancelled", "message": "Label creation cancelled."})

        result = await ws.send_command("config/label_registry/create", **payload)
        return json.dumps({"status": "created", "label": result}, indent=2)

    @mcp_server.tool()
    async def update_label(
        ctx: Context,
        label_id: str,
        name: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> str:
        """Update an existing label (rename, set color/icon/description).

        Args:
            label_id: The label to update.
            name: New display name.
            color: New color.
            icon: New MDI icon.
            description: New description.
        """
        ws, _rest = get_clients(ctx)
        changes = _drop_none(
            {"name": name, "color": color, "icon": icon, "description": description}
        )
        if not changes:
            return json.dumps({"error": "No fields provided to update."})

        if not await confirm_change(
            ctx=ctx, action="UPDATE", entity_type="label",
            identifier=label_id, config=changes,
        ):
            return json.dumps({"status": "cancelled", "message": "Label update cancelled."})

        result = await ws.send_command(
            "config/label_registry/update", label_id=label_id, **changes
        )
        return json.dumps({"status": "updated", "label": result}, indent=2)

    @mcp_server.tool()
    async def delete_label(
        ctx: Context, label_id: str
    ) -> str:
        """Delete a label from the registry.

        Args:
            label_id: The label to delete.
        """
        ws, _rest = get_clients(ctx)
        if not await confirm_change(
            ctx=ctx, action="DELETE", entity_type="label",
            identifier=label_id, config={"label_id": label_id},
        ):
            return json.dumps({"status": "cancelled", "message": "Label deletion cancelled."})

        await ws.send_command("config/label_registry/delete", label_id=label_id)
        return json.dumps({"status": "deleted", "label_id": label_id})

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def update_entity(
        ctx: Context,
        entity_id: str,
        name: str | None = None,
        icon: str | None = None,
        area_id: str | None = None,
        new_entity_id: str | None = None,
        labels: list[str] | None = None,
        hidden: bool | None = None,
        disabled: bool | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Update an entity in the entity registry.

        Lets you rename an entity, change its entity_id, assign it to an area,
        attach labels, set a custom icon, and hide or disable it.

        Args:
            entity_id: The entity to update (e.g. 'light.living_room').
            name: Custom friendly name (overrides the integration-provided name).
            icon: Custom MDI icon.
            area_id: Area to assign the entity to (overrides the device's area).
            new_entity_id: Rename the entity_id itself (e.g. 'light.lounge').
            labels: Replacement list of label IDs.
            hidden: True to hide, False to unhide.
            disabled: True to disable, False to enable.
            aliases: Replacement list of voice-assistant aliases.

        Note: ``hidden``/``disabled`` map to HA's ``hidden_by``/``disabled_by``
        fields ('user' when set, null when cleared).
        """
        ws, _rest = get_clients(ctx)

        changes: dict = _drop_none(
            {
                "name": name,
                "icon": icon,
                "area_id": area_id,
                "new_entity_id": new_entity_id,
                "labels": labels,
                "aliases": aliases,
            }
        )
        if hidden is not None:
            changes["hidden_by"] = "user" if hidden else None
        if disabled is not None:
            changes["disabled_by"] = "user" if disabled else None

        if not changes:
            return json.dumps({"error": "No fields provided to update."})

        preview = {"entity_id": entity_id, **changes}
        if not await confirm_change(
            ctx=ctx, action="UPDATE", entity_type="entity",
            identifier=entity_id, config=preview,
        ):
            return json.dumps({"status": "cancelled", "message": "Entity update cancelled."})

        result = await ws.send_command(
            "config/entity_registry/update", entity_id=entity_id, **changes
        )
        return json.dumps({"status": "updated", "entity": result}, indent=2)

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def update_device(
        ctx: Context,
        device_id: str,
        name_by_user: str | None = None,
        area_id: str | None = None,
        labels: list[str] | None = None,
        disabled: bool | None = None,
    ) -> str:
        """Update a device in the device registry (rename, assign area, label).

        Args:
            device_id: The device to update.
            name_by_user: Custom name for the device (overrides the default).
            area_id: Area to assign the device (and its entities) to.
            labels: Replacement list of label IDs.
            disabled: True to disable, False to enable.
        """
        ws, _rest = get_clients(ctx)
        changes: dict = _drop_none(
            {"name_by_user": name_by_user, "area_id": area_id, "labels": labels}
        )
        if disabled is not None:
            changes["disabled_by"] = "user" if disabled else None

        if not changes:
            return json.dumps({"error": "No fields provided to update."})

        preview = {"device_id": device_id, **changes}
        if not await confirm_change(
            ctx=ctx, action="UPDATE", entity_type="device",
            identifier=device_id, config=preview,
        ):
            return json.dumps({"status": "cancelled", "message": "Device update cancelled."})

        result = await ws.send_command(
            "config/device_registry/update", device_id=device_id, **changes
        )
        return json.dumps({"status": "updated", "device": result}, indent=2)
