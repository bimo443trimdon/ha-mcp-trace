"""Helper tools for UI-managed (storage collection) helpers via the WebSocket API."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)

VALID_HELPER_TYPES = (
    "input_boolean",
    "input_number",
    "input_text",
    "input_select",
    "input_datetime",
    "input_button",
    "counter",
    "timer",
    "schedule",
)

_RESERVED_KEYS = ("id", "type")


class HelperError(Exception):
    pass


def _validate_helper_type(helper_type: str) -> None:
    """Raise ValueError if helper_type is not one of the supported types."""
    if helper_type not in VALID_HELPER_TYPES:
        raise ValueError(
            f"Invalid helper_type '{helper_type}'. "
            f"Must be one of: {', '.join(VALID_HELPER_TYPES)}"
        )


def _parse_config(config: str) -> dict:
    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HelperError(f"Invalid JSON in config: {exc}") from exc
    if not isinstance(config_dict, dict):
        raise HelperError("config must be a JSON object")
    return {k: v for k, v in config_dict.items() if k not in _RESERVED_KEYS and not k.endswith("_id")}


def _check_domain(helper_type: str, entity_id: str) -> None:
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if domain != helper_type:
        raise HelperError(
            f"entity_id domain '{domain}' does not match helper_type '{helper_type}'"
        )


async def _resolve_storage_item(ws, helper_type: str, entity_id: str) -> dict:
    """Return the storage collection item backing entity_id.

    Storage helpers register their collection item id as the entity's unique_id.
    YAML-defined helpers are absent from ``<type>/list`` and cannot be edited here.
    """
    try:
        entry = await ws.send_command("config/entity_registry/get", entity_id=entity_id)
    except Exception as exc:
        raise HelperError(
            f"{entity_id} is not in the entity registry ({exc}); it is probably "
            "defined in YAML and must be edited in configuration.yaml."
        ) from exc

    item_id = (entry or {}).get("unique_id")
    items = await ws.send_command(f"{helper_type}/list") or []
    for item in items:
        if item.get("id") == item_id:
            return item
    raise HelperError(
        f"{entity_id} is not a UI-managed {helper_type} helper (no storage item with id "
        f"{item_id!r}); it is probably defined in YAML."
    )


def register_helper_tools(mcp_server):
    """Register all helper tools on the MCP server."""

    @mcp_server.tool()
    async def list_helpers(
        ctx: Context,
        helper_type: str | None = None,
    ) -> str:
        """List helper entities (input_*, counter, timer, schedule) and their states.

        Args:
            helper_type: Optional filter to one helper type, e.g. 'input_boolean'
                or 'counter'. When omitted, all supported helper types are returned.

        To see the stored configuration of UI-managed helpers (min/max, options,
        schedule blocks, ...), call with a helper_type and read ``storage_items``.
        """
        if helper_type is not None:
            _validate_helper_type(helper_type)

        ws, rest = get_clients(ctx)
        states = await rest.get_states()
        types = (helper_type,) if helper_type else VALID_HELPER_TYPES
        helpers = [
            s for s in states
            if s.get("entity_id", "").split(".", 1)[0] in types
        ]
        if not helper_type:
            return json.dumps(helpers, indent=2)

        try:
            storage_items = await ws.send_command(f"{helper_type}/list")
        except Exception as exc:
            storage_items = {"error": str(exc)}
        return json.dumps({"states": helpers, "storage_items": storage_items}, indent=2)

    @mcp_server.tool()
    async def create_helper(
        ctx: Context,
        helper_type: str,
        config: str,
    ) -> str:
        """Create a new UI-managed helper in Home Assistant.

        Args:
            helper_type: One of input_boolean, input_number, input_text,
                input_select, input_datetime, input_button, counter, timer,
                schedule.
            config: JSON object with the helper configuration. 'name' is
                required; 'icon' is optional. Type-specific fields:
                - input_number: min, max, step, mode, unit_of_measurement
                - input_text: min, max, pattern, mode
                - input_select: options (list of strings)
                - input_datetime: has_date, has_time
                - counter: initial, minimum, maximum, step, restore
                - timer: duration ("HH:MM:SS"), restore
                - schedule: monday..sunday, each a list of
                  {"from": "HH:MM:SS", "to": "HH:MM:SS"} blocks

        Template, group, utility_meter and other config-entry helpers are set up
        through config flows instead.
        """
        _validate_helper_type(helper_type)
        try:
            config_dict = _parse_config(config)
        except HelperError as exc:
            return json.dumps({"error": str(exc)})

        name = config_dict.get("name", helper_type)
        if not await confirm_change(
            ctx, action="CREATE", entity_type=helper_type, identifier=name, config=config_dict,
        ):
            return json.dumps({"status": "cancelled", "message": "Create cancelled by user"})

        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command(f"{helper_type}/create", **config_dict)
        except Exception as exc:
            logger.error("Failed to create %s helper '%s': %s", helper_type, name, exc)
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "created", "result": result}, indent=2)

    @mcp_server.tool()
    async def update_helper(
        ctx: Context,
        helper_type: str,
        entity_id: str,
        config: str,
    ) -> str:
        """Update a UI-managed helper.

        Args:
            helper_type: The helper type; must match the entity_id domain.
            entity_id: Full entity ID, e.g. 'input_boolean.my_toggle'.
            config: JSON object with only the fields to change, e.g.
                '{"name": "New Name"}'. Unchanged fields are preserved.

        Only helpers created in the UI (storage helpers) can be updated;
        YAML-defined helpers return an error.
        """
        _validate_helper_type(helper_type)
        ws, _rest = get_clients(ctx)
        try:
            _check_domain(helper_type, entity_id)
            changes = _parse_config(config)
            current = await _resolve_storage_item(ws, helper_type, entity_id)
        except HelperError as exc:
            return json.dumps({"error": str(exc)})

        item_id = current["id"]
        merged = {k: v for k, v in current.items() if k not in _RESERVED_KEYS} | changes

        if not await confirm_change(
            ctx, action="UPDATE", entity_type=helper_type, identifier=entity_id,
            config={"entity_id": entity_id, "current": current, "changes": changes},
        ):
            return json.dumps({"status": "cancelled", "message": "Update cancelled by user"})

        try:
            result = await ws.send_command(
                f"{helper_type}/update", **merged, **{f"{helper_type}_id": item_id}
            )
        except Exception as exc:
            logger.error("Failed to update %s '%s': %s", helper_type, entity_id, exc)
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "updated", "result": result}, indent=2)

    @mcp_server.tool()
    async def delete_helper(
        ctx: Context,
        helper_type: str,
        entity_id: str,
    ) -> str:
        """Delete a UI-managed helper permanently.

        Args:
            helper_type: The helper type; must match the entity_id domain.
            entity_id: Full entity ID, e.g. 'counter.visitors'.

        Irreversible: the helper and its entity are removed. YAML-defined
        helpers return an error.
        """
        _validate_helper_type(helper_type)
        ws, _rest = get_clients(ctx)
        try:
            _check_domain(helper_type, entity_id)
            current = await _resolve_storage_item(ws, helper_type, entity_id)
        except HelperError as exc:
            return json.dumps({"error": str(exc)})

        if not await confirm_change(
            ctx, action="DELETE", entity_type=helper_type, identifier=entity_id,
            config={"entity_id": entity_id, "item": current},
        ):
            return json.dumps({"status": "cancelled", "message": "Delete cancelled by user"})

        try:
            result = await ws.send_command(
                f"{helper_type}/delete", **{f"{helper_type}_id": current["id"]}
            )
        except Exception as exc:
            logger.error("Failed to delete %s '%s': %s", helper_type, entity_id, exc)
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "deleted", "entity_id": entity_id, "result": result}, indent=2)
