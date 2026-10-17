"""Automation CRUD tools for Home Assistant."""

import json
import logging
import uuid

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change
from ha_mcp.util.validation import validate_automation
from ha_mcp.util.yaml_util import to_yaml, diff_configs

logger = logging.getLogger(__name__)


def register_automation_tools(mcp_server):
    """Register all automation management tools on the MCP server."""

    @mcp_server.tool()
    async def list_automations(ctx: Context) -> str:
        """List all automations in Home Assistant.

        Returns a JSON array of automation summaries, each containing:
        - id: The automation entity_id (e.g. 'automation.morning_lights')
        - alias: The human-readable name (friendly_name attribute)
        - state: Whether the automation is 'on' or 'off'
        - last_triggered: Timestamp of the last time this automation fired

        Use this to discover existing automations before creating or modifying them.
        """
        _ws, rest = get_clients(ctx)
        states = await rest.get_states()

        automations = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith("automation."):
                continue
            attrs = state.get("attributes", {})
            automations.append({
                "id": entity_id,
                "alias": attrs.get("friendly_name", ""),
                "state": state.get("state", "unknown"),
                "last_triggered": attrs.get("last_triggered"),
            })

        return json.dumps(automations, indent=2)

    @mcp_server.tool()
    async def get_automation(ctx: Context, automation_id: str) -> str:
        """Get the full configuration of a single automation.

        Parameters:
            automation_id: The automation's internal ID (not the entity_id).
                This is the ID used in the HA config store, typically a UUID
                or slug found in the automation entity's attributes.

        Returns the complete automation configuration as JSON, including
        alias, description, triggers, conditions, actions, and mode.
        """
        _ws, rest = get_clients(ctx)
        config = await rest.get_automation_config(automation_id)
        return json.dumps(config, indent=2)

    @mcp_server.tool()
    async def create_automation(
        ctx: Context, config: str
    ) -> str:
        """Create a new automation in Home Assistant.

        Parameters:
            config: A JSON string containing the automation configuration.
                Must include at minimum an 'alias' and 'actions' (or 'action').
                Supported keys: alias, description, triggers, conditions,
                actions, mode. An 'id' field is optional; one will be
                generated if not provided.

        The automation config is validated against the Home Assistant config
        validator before applying.

        Returns a success message with the new automation ID, or a
        cancellation/error message.
        """
        ws, rest = get_clients(ctx)

        try:
            auto_config = json.loads(config)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON in config: {e}"
        if not isinstance(auto_config, dict):
            return "Error: config must be a JSON object."

        # Generate an ID if not provided
        auto_id = auto_config.pop("id", None) or str(uuid.uuid4())
        alias = auto_config.get("alias", auto_id)

        # Validate the automation config via WebSocket
        validation_result = await validate_automation(ws, auto_config)

        # Dry-run confirmation
        confirmed = await confirm_change(
            ctx, "CREATE", "automation", alias, auto_config,
            validation_result,
        )
        if not confirmed:
            return "Automation creation cancelled."

        # Save the automation
        await rest.save_automation_config(auto_id, auto_config)

        # Reload automations so HA picks up the new config
        await ws.send_command(
            "call_service", domain="automation", service="reload",
        )

        return f"Automation created successfully. ID: {auto_id}, Alias: {alias}"

    @mcp_server.tool()
    async def update_automation(
        ctx: Context, automation_id: str, config: str
    ) -> str:
        """Update an existing automation's configuration.

        Parameters:
            automation_id: The automation's internal ID (config store ID).
            config: A JSON string containing the new automation configuration.
                This replaces the entire configuration; include all desired
                fields (alias, triggers, conditions, actions, mode, etc.).

        Shows a diff between the current and proposed configuration for
        review. The new config is validated before applying.

        Returns a success message or a cancellation/error message.
        """
        ws, rest = get_clients(ctx)

        # Fetch existing config
        try:
            old_config = await rest.get_automation_config(automation_id)
        except Exception as e:
            return f"Error: Could not retrieve automation {automation_id}: {e}"

        try:
            new_config = json.loads(config)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON in config: {e}"
        if not isinstance(new_config, dict):
            return "Error: config must be a JSON object."

        # Remove 'id' from new config if present (it's the URL path param)
        new_config.pop("id", None)
        alias = new_config.get("alias", old_config.get("alias", automation_id))

        # Validate the new config via WebSocket
        validation_result = await validate_automation(ws, new_config)

        # Build a confirmation message that includes the diff
        diff_text = diff_configs(old_config, new_config)
        confirm_config = {
            "proposed": new_config,
            "diff": diff_text,
        }

        confirmed = await confirm_change(
            ctx, "UPDATE", "automation", alias, confirm_config,
            validation_result,
        )
        if not confirmed:
            return "Automation update cancelled."

        # Save the updated config
        await rest.save_automation_config(automation_id, new_config)

        # Reload automations
        await ws.send_command(
            "call_service", domain="automation", service="reload",
        )

        return f"Automation '{alias}' (ID: {automation_id}) updated successfully."

    @mcp_server.tool()
    async def delete_automation(
        ctx: Context, automation_id: str
    ) -> str:
        """Delete an automation from Home Assistant.

        Parameters:
            automation_id: The automation's internal ID (config store ID).

        Shows the current automation configuration for review before
        deletion. This action is irreversible.

        Returns a success message or a cancellation message.
        """
        ws, rest = get_clients(ctx)

        # Fetch current config for preview
        try:
            current_config = await rest.get_automation_config(automation_id)
        except Exception as e:
            return f"Error: Could not retrieve automation {automation_id}: {e}"

        confirmed = await confirm_change(
            ctx, "DELETE", "automation", automation_id, current_config,
        )
        if not confirmed:
            return "Automation deletion cancelled."

        # Delete the automation
        await rest.delete_automation_config(automation_id)

        # Reload automations
        await ws.send_command(
            "call_service", domain="automation", service="reload",
        )

        return f"Automation '{automation_id}' deleted successfully."

    @mcp_server.tool()
    async def toggle_automation(ctx: Context, entity_id: str, enabled: bool) -> str:
        """Enable or disable an automation.

        Parameters:
            entity_id: The full entity ID (e.g. 'automation.morning_lights').
            enabled: True to enable (turn on) the automation, False to
                disable (turn off).

        This is a non-destructive operation that does not require
        confirmation. It only changes whether the automation is active,
        without modifying its configuration.

        Returns a status message confirming the change.
        """
        _ws, rest = get_clients(ctx)
        service = "turn_on" if enabled else "turn_off"
        await rest.call_service("automation", service, {"entity_id": entity_id})
        state_label = "enabled" if enabled else "disabled"
        return f"Automation '{entity_id}' {state_label} successfully."

    @mcp_server.tool()
    async def duplicate_automation(
        ctx: Context, automation_id: str, new_alias: str | None = None
    ) -> str:
        """Duplicate an existing automation with a new ID.

        Parameters:
            automation_id: The internal ID of the automation to copy.
            new_alias: Optional alias for the new automation. If not
                provided, ' (Copy)' is appended to the original alias.

        Creates a copy of the source automation's configuration with a
        new UUID. The new automation is saved and automations are reloaded.
        No confirmation is required since this does not modify or delete
        existing configurations.

        Returns the new automation's ID.
        """
        ws, rest = get_clients(ctx)

        # Get source config
        try:
            source_config = await rest.get_automation_config(automation_id)
        except Exception as e:
            return f"Error: Could not retrieve automation {automation_id}: {e}"

        # Generate new ID
        new_id = str(uuid.uuid4())

        # Set alias
        if new_alias:
            source_config["alias"] = new_alias
        else:
            original_alias = source_config.get("alias", automation_id)
            source_config["alias"] = f"{original_alias} (Copy)"

        # Remove any existing id field from the config body
        source_config.pop("id", None)

        # Save as new automation
        await rest.save_automation_config(new_id, source_config)

        # Reload automations
        await ws.send_command(
            "call_service", domain="automation", service="reload",
        )

        return (
            f"Automation duplicated successfully. "
            f"New ID: {new_id}, Alias: {source_config['alias']}"
        )
