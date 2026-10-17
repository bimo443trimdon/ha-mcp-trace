"""Script CRUD tools for managing Home Assistant scripts with dry-run + confirm."""

import json
import logging
import re

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change
from ha_mcp.util.validation import validate_config_parts

logger = logging.getLogger(__name__)

# Pattern for valid HA script IDs: lowercase letters, digits, underscores only.
_VALID_SCRIPT_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def register_script_tools(mcp_server):
    """Register all script CRUD tools on the MCP server."""

    @mcp_server.tool()
    async def list_scripts(ctx: Context) -> str:
        """List all scripts registered in Home Assistant.

        Returns a JSON array of script summaries, each containing:
        - entity_id: The full entity ID (e.g. 'script.morning_routine')
        - friendly_name: Human-readable name from attributes
        - state: Current state ('on' if running, 'off' otherwise)
        - last_triggered: Timestamp of the last time the script was triggered

        Use this to discover existing scripts before creating or modifying them.
        """
        _ws, rest = get_clients(ctx)
        states = await rest.get_states()

        scripts = []
        for s in states:
            entity_id = s.get("entity_id", "")
            if not entity_id.startswith("script."):
                continue
            attrs = s.get("attributes", {})
            scripts.append({
                "entity_id": entity_id,
                "friendly_name": attrs.get("friendly_name", ""),
                "state": s.get("state", "unknown"),
                "last_triggered": attrs.get("last_triggered"),
            })

        return json.dumps(scripts, indent=2)

    @mcp_server.tool()
    async def get_script(ctx: Context, script_id: str) -> str:
        """Get the full configuration of a Home Assistant script.

        Args:
            script_id: The script object ID (the part after 'script.', e.g.
                'morning_routine' not 'script.morning_routine').

        Returns the complete script configuration as JSON, including alias,
        sequence, fields, mode, and any other configured options.
        """
        _ws, rest = get_clients(ctx)
        config = await rest.get_script_config(script_id)
        return json.dumps(config, indent=2)

    @mcp_server.tool()
    async def create_script(
        ctx: Context,
        script_id: str,
        config: str,
    ) -> str:
        """Create a new Home Assistant script.

        Args:
            script_id: The script object ID (lowercase letters, digits, and
                underscores only, must start with a letter). For example
                'morning_routine' — do NOT include the 'script.' prefix.
            config: JSON string with the script configuration. Must include at
                minimum 'sequence' (list of actions). Common fields:
                - alias: Human-readable name
                - sequence: List of action steps (required)
                - fields: Input fields/variables for the script
                - mode: Execution mode ('single', 'restart', 'queued', 'parallel')
                - icon: MDI icon string
                - description: Description of the script

        The script configuration is validated against Home Assistant before saving.
        """
        ws, rest = get_clients(ctx)

        # Validate script_id format
        if not _VALID_SCRIPT_ID.match(script_id):
            return json.dumps({
                "success": False,
                "error": (
                    f"Invalid script_id '{script_id}'. Must contain only lowercase "
                    "letters, digits, and underscores, and must start with a letter."
                ),
            })

        # Parse config JSON
        try:
            script_config = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "success": False,
                "error": f"Invalid JSON in config: {exc}",
            })

        if not isinstance(script_config, dict):
            return json.dumps({
                "success": False,
                "error": "Config must be a JSON object.",
            })

        # Validate the action sequence via WebSocket
        sequence = script_config.get("sequence", [])
        validation_result = await validate_config_parts(ws, actions=sequence)

        # Dry-run confirmation
        confirmed = await confirm_change(
            ctx,
            action="CREATE",
            entity_type="script",
            identifier=script_id,
            config=script_config,
            validation_result=validation_result,
        )

        if not confirmed:
            return json.dumps({
                "success": False,
                "error": "Change cancelled by user.",
            })

        # Save the script config via REST API
        await rest.save_script_config(script_id, script_config)

        # Reload scripts so HA picks up the change
        await ws.send_command(
            "call_service",
            domain="script",
            service="reload",
        )

        logger.info("Created script: %s", script_id)
        return json.dumps({
            "success": True,
            "script_id": script_id,
            "entity_id": f"script.{script_id}",
            "message": f"Script '{script_id}' created and reloaded successfully.",
        })

    @mcp_server.tool()
    async def update_script(
        ctx: Context,
        script_id: str,
        config: str,
    ) -> str:
        """Update an existing Home Assistant script.

        Args:
            script_id: The script object ID (e.g. 'morning_routine').
            config: JSON string with the complete updated script configuration.
                This replaces the entire script config — include all fields, not
                just the ones being changed. Must include 'sequence' at minimum.

        Fetches the current config for reference, validates the new config, shows
        a dry-run preview for confirmation, then saves and reloads.
        """
        ws, rest = get_clients(ctx)

        # Verify the script exists by fetching current config
        try:
            _current = await rest.get_script_config(script_id)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"Script '{script_id}' not found: {exc}",
            })

        # Parse new config JSON
        try:
            script_config = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "success": False,
                "error": f"Invalid JSON in config: {exc}",
            })

        if not isinstance(script_config, dict):
            return json.dumps({
                "success": False,
                "error": "Config must be a JSON object.",
            })

        # Validate the action sequence via WebSocket
        sequence = script_config.get("sequence", [])
        validation_result = await validate_config_parts(ws, actions=sequence)

        # Dry-run confirmation
        confirmed = await confirm_change(
            ctx,
            action="UPDATE",
            entity_type="script",
            identifier=script_id,
            config=script_config,
            validation_result=validation_result,
        )

        if not confirmed:
            return json.dumps({
                "success": False,
                "error": "Change cancelled by user.",
            })

        # Save the updated script config
        await rest.save_script_config(script_id, script_config)

        # Reload scripts
        await ws.send_command(
            "call_service",
            domain="script",
            service="reload",
        )

        logger.info("Updated script: %s", script_id)
        return json.dumps({
            "success": True,
            "script_id": script_id,
            "entity_id": f"script.{script_id}",
            "message": f"Script '{script_id}' updated and reloaded successfully.",
        })

    @mcp_server.tool()
    async def delete_script(
        ctx: Context,
        script_id: str,
    ) -> str:
        """Delete an existing Home Assistant script.

        Args:
            script_id: The script object ID (e.g. 'morning_routine').

        Fetches the current config for a deletion preview, asks for confirmation,
        then deletes the script and reloads the script domain.
        """
        ws, rest = get_clients(ctx)

        # Fetch current config for the deletion preview
        try:
            current_config = await rest.get_script_config(script_id)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"Script '{script_id}' not found: {exc}",
            })

        # Dry-run confirmation with current config as preview
        confirmed = await confirm_change(
            ctx,
            action="DELETE",
            entity_type="script",
            identifier=script_id,
            config=current_config,
        )

        if not confirmed:
            return json.dumps({
                "success": False,
                "error": "Change cancelled by user.",
            })

        # Delete the script
        await rest.delete_script_config(script_id)

        # Reload scripts
        await ws.send_command(
            "call_service",
            domain="script",
            service="reload",
        )

        logger.info("Deleted script: %s", script_id)
        return json.dumps({
            "success": True,
            "script_id": script_id,
            "message": f"Script '{script_id}' deleted and reloaded successfully.",
        })
