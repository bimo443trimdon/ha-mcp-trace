"""Proactive intelligence tools that leverage the entity analysis engine."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.entity_analysis import (
    analyze_coverage,
    generate_suggestions,
    detect_conflicts,
    suggest_dashboard_layout,
)

logger = logging.getLogger(__name__)


def register_suggestion_tools(mcp_server):
    """Register all suggestion / proactive-intelligence tools on the MCP server."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_entities(ws):
        """Fetch the full entity registry via WebSocket."""
        return await ws.send_command("config/entity_registry/list")

    async def _fetch_areas(ws):
        """Fetch the area registry via WebSocket."""
        return await ws.send_command("config/area_registry/list")

    async def _fetch_automation_states(rest):
        """Fetch all automation.* states from the REST API."""
        states = await rest.get_states()
        return [s for s in states if s.get("entity_id", "").startswith("automation.")]

    async def _fetch_automation_configs(rest, automation_states):
        """Fetch full configs for a list of automation states.

        Iterates over each automation state and attempts to retrieve its
        config from the REST API.  YAML-only automations (or those without
        a stored config) are silently skipped.

        Returns a list of dicts, each containing ``state`` (the original
        state object) and ``config`` (the retrieved configuration, or
        ``None`` if unavailable).
        """
        results = []
        for state in automation_states:
            attrs = state.get("attributes", {})
            auto_id = attrs.get("id")
            config = None
            if auto_id:
                try:
                    config = await rest.get_automation_config(auto_id)
                except Exception:
                    # YAML-only or otherwise inaccessible -- skip gracefully
                    logger.debug(
                        "Could not fetch config for automation %s (id=%s), skipping",
                        state.get("entity_id"),
                        auto_id,
                    )
            results.append({"state": state, "config": config})
        return results

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @mcp_server.tool()
    async def analyze_devices(ctx: Context, area_id: str | None = None) -> str:
        """Analyse device and entity coverage across areas.

        Examines all registered entities and existing automations to
        identify gaps in automation coverage -- devices that have no
        automations acting on them, areas with limited coverage, and
        sensor types that are not being monitored.

        Parameters:
            area_id: Optional area ID to restrict analysis to a single area.
                When provided, only entities assigned to this area are
                included in the report.

        Returns a JSON object with coverage statistics and details.
        """
        ws, rest = get_clients(ctx)

        entities = await _fetch_entities(ws)
        automation_states = await _fetch_automation_states(rest)
        areas = await _fetch_areas(ws)

        coverage = analyze_coverage(entities, automation_states, areas)

        # If a specific area was requested, filter the results down
        if area_id:
            area_coverage = {}
            for key, value in coverage.items():
                if isinstance(value, dict) and "areas" in value:
                    filtered_areas = {
                        k: v for k, v in value["areas"].items() if k == area_id
                    }
                    area_coverage[key] = {**value, "areas": filtered_areas}
                elif isinstance(value, list):
                    area_coverage[key] = [
                        item for item in value
                        if isinstance(item, dict) and item.get("area_id") == area_id
                    ]
                else:
                    area_coverage[key] = value
            coverage = area_coverage

        return json.dumps(coverage, indent=2, default=str)

    @mcp_server.tool()
    async def suggest_automations(
        ctx: Context, entity_id: str | None = None, area_id: str | None = None
    ) -> str:
        """Suggest new automations based on existing devices and entities.

        Analyses the current entity registry and existing automations to
        recommend useful automations that are missing. Suggestions may
        include motion-activated lighting, climate schedules, leak alerts,
        notification rules, and more.

        Parameters:
            entity_id: Optional entity ID to generate suggestions
                specifically for this entity and related devices.
            area_id: Optional area ID to restrict suggestions to entities
                in a particular area.

        Returns a JSON array of automation suggestions, each with a
        description, rationale, and a proposed configuration skeleton.
        """
        ws, rest = get_clients(ctx)

        entities = await _fetch_entities(ws)
        automation_states = await _fetch_automation_states(rest)
        areas = await _fetch_areas(ws)

        # Fetch full configs for richer analysis
        automations = await _fetch_automation_configs(rest, automation_states)

        suggestions = generate_suggestions(
            entities,
            automations,
            areas,
            target_area_id=area_id,
            target_entity_id=entity_id,
        )

        return json.dumps(suggestions, indent=2, default=str)

    @mcp_server.tool()
    async def detect_automation_conflicts(ctx: Context) -> str:
        """Detect potential conflicts or redundancies between automations.

        Analyses all automation configurations to find:
        - Automations with overlapping triggers that may fire simultaneously
        - Contradictory actions (e.g., one automation turns a light on while
          another turns it off at the same time)
        - Duplicate automations that perform the same task
        - Race conditions between automations targeting the same entities

        Returns a JSON array of detected conflicts, each describing the
        involved automations, the type of conflict, and a recommendation.
        """
        _ws, rest = get_clients(ctx)

        automation_states = await _fetch_automation_states(rest)
        automations = await _fetch_automation_configs(rest, automation_states)

        conflicts = detect_conflicts(automations)

        return json.dumps(conflicts, indent=2, default=str)

    @mcp_server.tool()
    async def suggest_dashboard(
        ctx: Context, area_id: str | None = None
    ) -> str:
        """Suggest a Lovelace dashboard layout based on registered entities.

        Analyses all entities (grouped by area and domain) and proposes a
        Lovelace dashboard configuration with sensible card types, entity
        groupings, and layout structure.

        Parameters:
            area_id: Optional area ID to generate a dashboard layout for a
                single area rather than the whole home.

        Returns a JSON object representing the suggested Lovelace
        configuration, ready to be used as a starting point for a custom
        dashboard.
        """
        ws, _rest = get_clients(ctx)

        entities = await _fetch_entities(ws)
        areas = await _fetch_areas(ws)

        layout = suggest_dashboard_layout(entities, areas, target_area_id=area_id)

        return json.dumps(layout, indent=2, default=str)
