"""State tools for reading Home Assistant entity states, history, logs, and templates."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.redact import redact, tail

logger = logging.getLogger(__name__)


def register_state_tools(mcp_server):
    """Register all state-reading tools on the MCP server."""

    @mcp_server.tool()
    async def get_all_states(ctx: Context, domain: str | None = None) -> str:
        """Get the current state of all entities in Home Assistant.

        Returns a JSON array of state objects, each containing entity_id, state,
        attributes, last_changed, and last_updated fields. Use the optional
        domain parameter to filter results to a specific integration domain
        (e.g. 'light', 'switch', 'sensor', 'climate', 'binary_sensor').

        This is useful for discovering what entities exist or getting a broad
        overview of the system state.
        """
        _ws, rest = get_clients(ctx)
        states = await rest.get_states()

        if domain:
            prefix = f"{domain}."
            states = [s for s in states if s.get("entity_id", "").startswith(prefix)]

        return json.dumps(states, indent=2)

    @mcp_server.tool()
    async def get_entity_state(ctx: Context, entity_id: str) -> str:
        """Get the full current state of a single Home Assistant entity.

        Returns a JSON object containing the entity's state value, all
        attributes (friendly_name, device_class, unit_of_measurement, etc.),
        last_changed, and last_updated timestamps.

        Use this when you need detailed information about one specific entity
        rather than listing all entities.
        """
        _ws, rest = get_clients(ctx)
        state = await rest.get_state(entity_id)
        return json.dumps(state, indent=2)

    @mcp_server.tool()
    async def get_entity_history(
        ctx: Context,
        entity_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        """Get the state change history of a Home Assistant entity.

        Returns a JSON array of state change records showing how the entity's
        state evolved over time. Each record includes the state value,
        attributes, and timestamps.

        Parameters:
            entity_id: The entity to retrieve history for (e.g. 'sensor.temperature').
            start_time: Optional ISO 8601 datetime string for the start of the
                period (e.g. '2024-01-15T08:00:00Z'). Defaults to 1 day ago.
            end_time: Optional ISO 8601 datetime string for the end of the period.
                Defaults to now.

        This is useful for analysing trends, debugging automations, or
        understanding how an entity's state has changed over a given period.
        """
        _ws, rest = get_clients(ctx)
        history = await rest.get_history(entity_id, start_time, end_time)
        return json.dumps(history, indent=2)

    @mcp_server.tool()
    async def get_logbook(
        ctx: Context,
        entity_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        """Get logbook entries from Home Assistant.

        Returns a JSON array of human-readable logbook entries describing events
        such as state changes, service calls, and automation triggers. Each
        entry includes a timestamp, entity name, and a description of what
        happened.

        Parameters:
            entity_id: Optional entity to filter logbook entries for.
            start_time: Optional ISO 8601 datetime string for the start of the
                period. Defaults to 1 day ago.
            end_time: Optional ISO 8601 datetime string for the end of the period.
                Defaults to now.

        This provides a more human-friendly view of events compared to raw
        state history. Useful for understanding what actions occurred and why.
        """
        _ws, rest = get_clients(ctx)
        logbook = await rest.get_logbook(entity_id, start_time, end_time)
        return json.dumps(logbook, indent=2)

    @mcp_server.tool()
    async def get_error_log(ctx: Context) -> str:
        """Get the Home Assistant error log.

        Returns the most recent ~20 KB of the raw Home Assistant log, with
        tokens, passwords, API keys and URL credentials redacted.

        Prefer get_system_log for a deduplicated, structured list of errors;
        use this when you need the raw surrounding log lines.
        """
        _ws, rest = get_clients(ctx)
        return redact(tail(str(await rest.get_error_log())))

    @mcp_server.tool()
    async def render_template(ctx: Context, template: str) -> str:
        """Render a Home Assistant Jinja2 template and return the result.

        Evaluates a Jinja2 template string on the Home Assistant server, giving
        access to all HA template functions, entity states, and helpers.

        Parameters:
            template: A Jinja2 template string (e.g.
                '{{ states(\"sensor.temperature\") }}' or
                '{{ now().strftime(\"%H:%M\") }}').

        This is useful for testing template expressions before using them in
        automations, for computing derived values from entity states, or for
        answering questions that require combining data from multiple entities.
        """
        _ws, rest = get_clients(ctx)
        return await rest.render_template(template)
