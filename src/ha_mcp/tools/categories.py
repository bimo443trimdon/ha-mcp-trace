"""Category registry tools: per-scope categories for automations, scripts, scenes, helpers."""

import json
import logging
import re

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)

_SCOPE_RE = re.compile(r"^[a-z0-9_]+$")
_SCOPE_HINT = "Scope is the settings page the category belongs to, e.g. 'automation', 'script', 'scene' or 'helpers'."


def _check_scope(scope: str) -> str | None:
    if not _SCOPE_RE.match(scope or ""):
        return json.dumps({"error": f"Invalid scope {scope!r}. {_SCOPE_HINT}"})
    return None


def register_category_tools(mcp_server):
    """Register category registry tools."""

    @mcp_server.tool()
    async def list_categories(ctx: Context, scope: str) -> str:
        """List the categories defined for one scope.

        Categories group items on a single settings page (unlike labels, which
        are global). Args:
            scope: 'automation', 'script', 'scene' or 'helpers'.
        """
        if err := _check_scope(scope):
            return err
        ws, _rest = get_clients(ctx)
        return json.dumps(await ws.send_command("config/category_registry/list", scope=scope), indent=2)

    @mcp_server.tool()
    async def create_category(ctx: Context, scope: str, name: str, icon: str | None = None) -> str:
        """Create a category in a scope.

        Args:
            scope: 'automation', 'script', 'scene' or 'helpers'.
            name: Display name (must be unique within the scope).
            icon: Optional MDI icon, e.g. 'mdi:lightbulb'.
        """
        if err := _check_scope(scope):
            return err
        payload = {"scope": scope, "name": name}
        if icon is not None:
            payload["icon"] = icon
        if not await confirm_change(ctx, "CREATE", "category", f"{scope}/{name}", payload):
            return json.dumps({"status": "cancelled"})
        ws, _rest = get_clients(ctx)
        result = await ws.send_command("config/category_registry/create", **payload)
        return json.dumps({"status": "created", "category": result}, indent=2)

    @mcp_server.tool()
    async def update_category(
        ctx: Context, scope: str, category_id: str, name: str | None = None, icon: str | None = None
    ) -> str:
        """Rename a category or change its icon.

        Args:
            scope: Scope the category belongs to.
            category_id: From list_categories.
            name: New name.
            icon: New MDI icon.
        """
        if err := _check_scope(scope):
            return err
        changes = {k: v for k, v in (("name", name), ("icon", icon)) if v is not None}
        if not changes:
            return json.dumps({"error": "Nothing to update; pass name and/or icon."})
        if not await confirm_change(ctx, "UPDATE", "category", f"{scope}/{category_id}", changes):
            return json.dumps({"status": "cancelled"})
        ws, _rest = get_clients(ctx)
        result = await ws.send_command(
            "config/category_registry/update", scope=scope, category_id=category_id, **changes
        )
        return json.dumps({"status": "updated", "category": result}, indent=2)

    @mcp_server.tool()
    async def delete_category(ctx: Context, scope: str, category_id: str) -> str:
        """Delete a category. Items in it become uncategorised.

        Args:
            scope: Scope the category belongs to.
            category_id: From list_categories.
        """
        if err := _check_scope(scope):
            return err
        if not await confirm_change(
            ctx, "DELETE", "category", f"{scope}/{category_id}", {"scope": scope, "category_id": category_id}
        ):
            return json.dumps({"status": "cancelled"})
        ws, _rest = get_clients(ctx)
        await ws.send_command("config/category_registry/delete", scope=scope, category_id=category_id)
        return json.dumps({"status": "deleted", "scope": scope, "category_id": category_id})

    @mcp_server.tool()
    async def assign_category(ctx: Context, entity_id: str, scope: str, category_id: str | None = None) -> str:
        """Put an entity (automation, script, scene, helper) in a category.

        Args:
            entity_id: e.g. 'automation.hallway_motion'.
            scope: Scope of the category, e.g. 'automation'.
            category_id: From list_categories, or omit/null to remove the
                entity from its category in that scope.
        """
        if err := _check_scope(scope):
            return err
        categories = {scope: category_id}
        if not await confirm_change(
            ctx, "ASSIGN", "category", entity_id, {"entity_id": entity_id, "categories": categories}
        ):
            return json.dumps({"status": "cancelled"})
        ws, _rest = get_clients(ctx)
        result = await ws.send_command(
            "config/entity_registry/update", entity_id=entity_id, categories=categories
        )
        entry = result.get("entity_entry", result) if isinstance(result, dict) else result
        return json.dumps({
            "status": "assigned" if category_id else "unassigned",
            "entity_id": entity_id,
            "categories": entry.get("categories") if isinstance(entry, dict) else None,
        }, indent=2)
