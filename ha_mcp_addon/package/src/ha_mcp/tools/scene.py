"""Scene CRUD tools for managing Home Assistant scenes."""

import json
import logging
import uuid

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


def register_scene_tools(mcp_server):
    """Register all scene management tools on the MCP server."""

    @mcp_server.tool()
    async def list_scenes(ctx: Context) -> str:
        """List all scenes registered in Home Assistant.

        Returns a JSON array of scene summaries, each containing entity_id,
        friendly_name, and current state. Use this to discover available scenes
        before retrieving full configuration details.
        """
        _ws, rest = get_clients(ctx)
        states = await rest.get_states()

        scenes = []
        for s in states:
            entity_id = s.get("entity_id", "")
            if entity_id.startswith("scene."):
                scenes.append({
                    "entity_id": entity_id,
                    "friendly_name": s.get("attributes", {}).get("friendly_name", ""),
                    "state": s.get("state", ""),
                })

        return json.dumps(scenes, indent=2)

    @mcp_server.tool()
    async def get_scene(ctx: Context, scene_id: str) -> str:
        """Get the full configuration of a Home Assistant scene.

        Args:
            scene_id: The scene identifier (the part after 'scene.' in the
                entity_id, or the internal UUID/slug used in the config store).

        Returns the complete scene configuration as JSON, including name,
        entities, icon, and any other stored fields.
        """
        _ws, rest = get_clients(ctx)
        config = await rest.get_scene_config(scene_id)
        return json.dumps(config, indent=2)

    @mcp_server.tool()
    async def create_scene(
        ctx: Context, config: str
    ) -> str:
        """Create a new Home Assistant scene.

        Args:
            config: JSON string containing the scene configuration. Must include
                at least 'name' and 'entities'. Optional fields: 'id' (auto-
                generated UUID if omitted), 'icon'.

                Example:
                {
                    "name": "Movie Night",
                    "entities": {
                        "light.living_room": {"state": "on", "brightness": 50},
                        "media_player.tv": {"state": "on"}
                    },
                    "icon": "mdi:movie"
                }

        The scene is saved and then the scene integration is reloaded so the
        new scene appears immediately.
        """
        ws, rest = get_clients(ctx)

        try:
            scene_config = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in config: {exc}"})
        if not isinstance(scene_config, dict):
            return json.dumps({"error": "config must be a JSON object."})

        # Generate an id if not provided
        scene_id = scene_config.pop("id", None) or uuid.uuid4().hex

        confirmed = await confirm_change(
            ctx=ctx,
            action="CREATE",
            entity_type="scene",
            identifier=scene_config.get("name", scene_id),
            config=scene_config,
        )

        if not confirmed:
            return json.dumps({"status": "cancelled", "message": "Scene creation cancelled by user."})

        await rest.save_scene_config(scene_id, scene_config)

        # Reload the scene integration so the new scene is available immediately
        await ws.send_command(
            "call_service", domain="scene", service="reload"
        )

        return json.dumps({
            "status": "created",
            "scene_id": scene_id,
            "name": scene_config.get("name", ""),
        })

    @mcp_server.tool()
    async def update_scene(
        ctx: Context, scene_id: str, config: str
    ) -> str:
        """Update an existing Home Assistant scene.

        Args:
            scene_id: The scene identifier to update.
            config: JSON string containing the updated scene configuration.
                Only the fields provided will be merged into the existing
                configuration. Must be a valid JSON object.

        Fetches the current configuration, merges the provided changes,
        shows a dry-run preview, and then saves + reloads on confirmation.
        """
        ws, rest = get_clients(ctx)

        # Fetch current config
        try:
            current_config = await rest.get_scene_config(scene_id)
        except Exception as exc:
            return json.dumps({"error": f"Failed to get scene config: {exc}"})

        try:
            updates = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in config: {exc}"})
        if not isinstance(updates, dict):
            return json.dumps({"error": "config must be a JSON object."})

        # Merge updates into current config
        merged_config = {**current_config, **updates}
        # Remove 'id' from the payload if present – it's used as the URL key
        merged_config.pop("id", None)

        confirmed = await confirm_change(
            ctx=ctx,
            action="UPDATE",
            entity_type="scene",
            identifier=scene_id,
            config=merged_config,
        )

        if not confirmed:
            return json.dumps({"status": "cancelled", "message": "Scene update cancelled by user."})

        await rest.save_scene_config(scene_id, merged_config)

        # Reload the scene integration so changes take effect immediately
        await ws.send_command(
            "call_service", domain="scene", service="reload"
        )

        return json.dumps({
            "status": "updated",
            "scene_id": scene_id,
            "name": merged_config.get("name", ""),
        })

    @mcp_server.tool()
    async def delete_scene(
        ctx: Context, scene_id: str
    ) -> str:
        """Delete a Home Assistant scene.

        Args:
            scene_id: The scene identifier to delete.

        Fetches the current configuration for a preview, asks for confirmation,
        and then deletes the scene and reloads the integration.
        """
        ws, rest = get_clients(ctx)

        # Fetch current config so we can show it in the confirmation preview
        try:
            current_config = await rest.get_scene_config(scene_id)
        except Exception as exc:
            return json.dumps({"error": f"Failed to get scene config: {exc}"})

        confirmed = await confirm_change(
            ctx=ctx,
            action="DELETE",
            entity_type="scene",
            identifier=scene_id,
            config=current_config,
        )

        if not confirmed:
            return json.dumps({"status": "cancelled", "message": "Scene deletion cancelled by user."})

        await rest.delete_scene_config(scene_id)

        # Reload the scene integration so the deletion is reflected immediately
        await ws.send_command(
            "call_service", domain="scene", service="reload"
        )

        return json.dumps({
            "status": "deleted",
            "scene_id": scene_id,
            "name": current_config.get("name", ""),
        })
