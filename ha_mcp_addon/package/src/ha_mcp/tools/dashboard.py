"""Lovelace dashboard management tools for Home Assistant."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


async def _get_dashboard_config(ws, dashboard_id: str | None = None) -> dict:
    """Fetch the full Lovelace config for a dashboard.

    Args:
        ws: The WebSocket client.
        dashboard_id: URL path of the dashboard, or None for the default dashboard.

    Returns:
        The dashboard configuration dict.
    """
    if dashboard_id:
        return await ws.send_command("lovelace/config", url_path=dashboard_id)
    return await ws.send_command("lovelace/config")


async def _save_dashboard_config(
    ws, config: dict, dashboard_id: str | None = None
) -> None:
    """Save a full Lovelace config for a dashboard.

    Args:
        ws: The WebSocket client.
        config: The complete dashboard configuration to save.
        dashboard_id: URL path of the dashboard, or None for the default dashboard.
    """
    if dashboard_id:
        await ws.send_command(
            "lovelace/config/save", config=config, url_path=dashboard_id
        )
    else:
        await ws.send_command("lovelace/config/save", config=config)


def register_dashboard_tools(mcp_server):
    """Register all Lovelace dashboard management tools on the MCP server."""

    @mcp_server.tool()
    async def list_dashboards(ctx: Context) -> str:
        """List all Lovelace dashboards configured in Home Assistant.

        Returns a JSON array of dashboard summaries, each containing fields
        such as id, url_path, title, mode, and require_admin.
        Use this to discover available dashboards before retrieving their
        full configuration.
        """
        ws, _rest = get_clients(ctx)
        dashboards = await ws.send_command("lovelace/dashboards/list")
        return json.dumps(dashboards, indent=2)

    @mcp_server.tool()
    async def get_dashboard_config(
        ctx: Context, dashboard_id: str | None = None
    ) -> str:
        """Get the full Lovelace configuration of a dashboard.

        Args:
            dashboard_id: The URL path of the dashboard (e.g. 'energy',
                'my-custom-dashboard'). Omit or pass None to get the
                default/overview dashboard configuration.

        Returns the complete Lovelace configuration as JSON, including
        the views array and any top-level dashboard settings.
        """
        ws, _rest = get_clients(ctx)
        config = await _get_dashboard_config(ws, dashboard_id)
        return json.dumps(config, indent=2)

    @mcp_server.tool()
    async def save_dashboard_config(
        ctx: Context,
        config: str,
        dashboard_id: str | None = None,
    ) -> str:
        """Save a complete Lovelace dashboard configuration.

        Args:
            config: JSON string containing the full Lovelace configuration.
                Must include a 'views' array. Example:
                {
                    "title": "My Home",
                    "views": [
                        {
                            "title": "Living Room",
                            "cards": [{"type": "entities", "entities": ["light.lamp"]}]
                        }
                    ]
                }
            dashboard_id: The URL path of the dashboard to save. Omit or
                pass None to save the default/overview dashboard.

        Replaces the entire dashboard configuration. Use with care.
        """
        ws, _rest = get_clients(ctx)

        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in config: {exc}"})

        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="UPDATE",
            entity_type="dashboard",
            identifier=identifier,
            config=config_dict,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Dashboard config save cancelled by user.",
            })

        await _save_dashboard_config(ws, config_dict, dashboard_id)

        return json.dumps({
            "status": "saved",
            "dashboard_id": identifier,
        })

    @mcp_server.tool()
    async def get_view(
        ctx: Context, view_index: int, dashboard_id: str | None = None
    ) -> str:
        """Get the configuration of a single view from a dashboard.

        Args:
            view_index: Zero-based index of the view to retrieve.
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.

        Returns the view configuration as JSON, including its title,
        cards, and any other view-level settings.
        """
        ws, _rest = get_clients(ctx)
        config = await _get_dashboard_config(ws, dashboard_id)

        views = config.get("views", [])
        if view_index < 0 or view_index >= len(views):
            return json.dumps({
                "error": f"View index {view_index} out of range. "
                         f"Dashboard has {len(views)} view(s) (0-{len(views) - 1}).",
            })

        return json.dumps(views[view_index], indent=2)

    @mcp_server.tool()
    async def add_view(
        ctx: Context,
        view_config: str,
        dashboard_id: str | None = None,
        position: int | None = None,
    ) -> str:
        """Add a new view to a Lovelace dashboard.

        Args:
            view_config: JSON string containing the view configuration.
                Example:
                {
                    "title": "Kitchen",
                    "cards": [
                        {"type": "entities", "entities": ["light.kitchen"]}
                    ]
                }
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.
            position: Zero-based index where the view should be inserted.
                If omitted, the view is appended at the end.

        Fetches the current dashboard config, inserts the new view, and
        saves the updated config back.
        """
        ws, _rest = get_clients(ctx)

        try:
            new_view = json.loads(view_config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in view_config: {exc}"})

        config = await _get_dashboard_config(ws, dashboard_id)
        views = config.get("views", [])

        if position is not None:
            if position < 0 or position > len(views):
                return json.dumps({
                    "error": f"Position {position} out of range. "
                             f"Valid range is 0-{len(views)}.",
                })
            views.insert(position, new_view)
        else:
            views.append(new_view)

        config["views"] = views
        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="ADD VIEW",
            entity_type="dashboard",
            identifier=f"{identifier} - {new_view.get('title', 'Untitled')}",
            config=config,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Add view cancelled by user.",
            })

        await _save_dashboard_config(ws, config, dashboard_id)

        actual_position = position if position is not None else len(views) - 1
        return json.dumps({
            "status": "added",
            "view_title": new_view.get("title", "Untitled"),
            "view_index": actual_position,
            "total_views": len(views),
        })

    @mcp_server.tool()
    async def update_view(
        ctx: Context,
        view_index: int,
        view_config: str,
        dashboard_id: str | None = None,
    ) -> str:
        """Replace a view in a Lovelace dashboard.

        Args:
            view_index: Zero-based index of the view to replace.
            view_config: JSON string containing the new view configuration.
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.

        Fetches the current dashboard config, replaces the view at the
        specified index, and saves the updated config back.
        """
        ws, _rest = get_clients(ctx)

        try:
            new_view = json.loads(view_config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in view_config: {exc}"})

        config = await _get_dashboard_config(ws, dashboard_id)
        views = config.get("views", [])

        if view_index < 0 or view_index >= len(views):
            return json.dumps({
                "error": f"View index {view_index} out of range. "
                         f"Dashboard has {len(views)} view(s) (0-{len(views) - 1}).",
            })

        views[view_index] = new_view
        config["views"] = views
        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="UPDATE VIEW",
            entity_type="dashboard",
            identifier=f"{identifier} - view[{view_index}]",
            config=config,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Update view cancelled by user.",
            })

        await _save_dashboard_config(ws, config, dashboard_id)

        return json.dumps({
            "status": "updated",
            "view_index": view_index,
            "view_title": new_view.get("title", "Untitled"),
        })

    @mcp_server.tool()
    async def delete_view(
        ctx: Context,
        view_index: int,
        dashboard_id: str | None = None,
    ) -> str:
        """Delete a view from a Lovelace dashboard.

        Args:
            view_index: Zero-based index of the view to delete.
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.

        Fetches the current dashboard config, removes the view at the
        specified index, and saves the updated config back. This action
        is irreversible.
        """
        ws, _rest = get_clients(ctx)

        config = await _get_dashboard_config(ws, dashboard_id)
        views = config.get("views", [])

        if view_index < 0 or view_index >= len(views):
            return json.dumps({
                "error": f"View index {view_index} out of range. "
                         f"Dashboard has {len(views)} view(s) (0-{len(views) - 1}).",
            })

        removed_view = views.pop(view_index)
        config["views"] = views
        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="DELETE VIEW",
            entity_type="dashboard",
            identifier=f"{identifier} - {removed_view.get('title', 'Untitled')}",
            config=removed_view,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Delete view cancelled by user.",
            })

        await _save_dashboard_config(ws, config, dashboard_id)

        return json.dumps({
            "status": "deleted",
            "deleted_view_title": removed_view.get("title", "Untitled"),
            "deleted_view_index": view_index,
            "remaining_views": len(views),
        })

    @mcp_server.tool()
    async def add_card(
        ctx: Context,
        view_index: int,
        card_config: str,
        dashboard_id: str | None = None,
    ) -> str:
        """Add a card to a view in a Lovelace dashboard.

        Args:
            view_index: Zero-based index of the view to add the card to.
            card_config: JSON string containing the card configuration.
                Example:
                {
                    "type": "light",
                    "entity": "light.living_room"
                }
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.

        Fetches the current dashboard config, appends the card to the
        specified view's cards list, and saves the updated config back.
        """
        ws, _rest = get_clients(ctx)

        try:
            new_card = json.loads(card_config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in card_config: {exc}"})

        config = await _get_dashboard_config(ws, dashboard_id)
        views = config.get("views", [])

        if view_index < 0 or view_index >= len(views):
            return json.dumps({
                "error": f"View index {view_index} out of range. "
                         f"Dashboard has {len(views)} view(s) (0-{len(views) - 1}).",
            })

        view = views[view_index]
        cards = view.get("cards", [])
        cards.append(new_card)
        view["cards"] = cards
        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="ADD CARD",
            entity_type="dashboard",
            identifier=f"{identifier} - view[{view_index}]",
            config=new_card,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Add card cancelled by user.",
            })

        await _save_dashboard_config(ws, config, dashboard_id)

        return json.dumps({
            "status": "added",
            "card_type": new_card.get("type", "unknown"),
            "card_index": len(cards) - 1,
            "view_index": view_index,
        })

    @mcp_server.tool()
    async def update_card(
        ctx: Context,
        view_index: int,
        card_index: int,
        card_config: str,
        dashboard_id: str | None = None,
    ) -> str:
        """Replace a card in a view of a Lovelace dashboard.

        Args:
            view_index: Zero-based index of the view containing the card.
            card_index: Zero-based index of the card to replace within the view.
            card_config: JSON string containing the new card configuration.
            dashboard_id: The URL path of the dashboard. Omit for the
                default dashboard.

        Fetches the current dashboard config, replaces the card at the
        specified position, and saves the updated config back.
        """
        ws, _rest = get_clients(ctx)

        try:
            new_card = json.loads(card_config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in card_config: {exc}"})

        config = await _get_dashboard_config(ws, dashboard_id)
        views = config.get("views", [])

        if view_index < 0 or view_index >= len(views):
            return json.dumps({
                "error": f"View index {view_index} out of range. "
                         f"Dashboard has {len(views)} view(s) (0-{len(views) - 1}).",
            })

        view = views[view_index]
        cards = view.get("cards", [])

        if card_index < 0 or card_index >= len(cards):
            return json.dumps({
                "error": f"Card index {card_index} out of range. "
                         f"View has {len(cards)} card(s) (0-{len(cards) - 1}).",
            })

        cards[card_index] = new_card
        view["cards"] = cards
        identifier = dashboard_id or "default"

        confirmed = await confirm_change(
            ctx=ctx,
            action="UPDATE CARD",
            entity_type="dashboard",
            identifier=f"{identifier} - view[{view_index}]/card[{card_index}]",
            config=new_card,
        )

        if not confirmed:
            return json.dumps({
                "status": "cancelled",
                "message": "Update card cancelled by user.",
            })

        await _save_dashboard_config(ws, config, dashboard_id)

        return json.dumps({
            "status": "updated",
            "card_type": new_card.get("type", "unknown"),
            "card_index": card_index,
            "view_index": view_index,
        })
