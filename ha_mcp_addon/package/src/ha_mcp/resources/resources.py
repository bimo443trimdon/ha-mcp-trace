"""MCP Resources providing URI-addressable read-only data from Home Assistant.

Note: Most read-only data is also available via tools (list_devices, list_entities,
get_all_states, etc.). Resources provide an alternative URI-based access pattern.
Only resource templates (with URI parameters) are registered here, since FastMCP
static resources don't support accessing lifespan context.
"""

import json

from ha_mcp.util.context import get_clients


def register_resources(mcp_server):
    """Register MCP resource templates with the server."""

    @mcp_server.resource("ha://blueprints/{domain}")
    async def ha_blueprints(domain: str) -> str:
        """Blueprints available for a domain (automation, script).

        Use domain 'automation' or 'script' to list available blueprints.
        """
        # Note: This resource template doesn't use ctx since FastMCP
        # resource templates pass URI params as function args.
        # Blueprint listing is handled via the list_blueprints tool
        # for full functionality with client access.
        return json.dumps({
            "info": f"Use the list_blueprints tool with domain='{domain}' for full blueprint data.",
            "domain": domain,
        })
