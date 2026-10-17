"""Helper for extracting HA clients from FastMCP lifespan context."""


def get_clients(ctx) -> tuple:
    """Return the (ws_client, rest_client) tuple from the lifespan context."""
    lifespan = ctx.lifespan_context
    return lifespan["ws"], lifespan["rest"]
