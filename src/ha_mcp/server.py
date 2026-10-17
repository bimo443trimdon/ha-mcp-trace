import logging
from contextlib import asynccontextmanager
from fastmcp import FastMCP

from ha_mcp.auth import ApiKeyVerifier
from ha_mcp.config import settings
from ha_mcp.ha_client.websocket import HAWebSocketClient
from ha_mcp.ha_client.rest import HARestClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Create HA clients at startup, share via lifespan context, cleanup on shutdown."""
    ws_client = HAWebSocketClient(settings.ha_websocket_url, settings.ha_token)
    rest_client = HARestClient(settings.ha_base_url, settings.ha_token)

    logger.info("Connecting to Home Assistant at %s", settings.ha_base_url)
    await ws_client.connect()
    await rest_client.connect()
    logger.info("Connected to Home Assistant successfully")

    try:
        yield {"ws": ws_client, "rest": rest_client}
    finally:
        logger.info("Disconnecting from Home Assistant")
        await ws_client.disconnect()
        await rest_client.disconnect()


mcp = FastMCP(
    "Home Assistant MCP",
    instructions=(
        "This MCP server is for setting up and maintaining Home Assistant: "
        "adding and configuring integrations through config flows, organising "
        "devices and entities into areas, floors, labels and categories, "
        "building automations, scripts, scenes, helpers, dashboards and "
        "blueprints, fixing repairs, debugging automation traces, and "
        "managing backups. Prefer the dedicated configuration tools over "
        "call_service. Read the current state before changing it, and validate "
        "automation/script configs before saving them."
    ),
    lifespan=lifespan,
    auth=(
        ApiKeyVerifier(settings.api_key)
        if settings.transport != "stdio" and settings.api_key
        else None
    ),
    version="0.2.0",
)

# Re-export get_clients for backward compatibility
from ha_mcp.util.context import get_clients  # noqa: F401

# Register all tools, resources, and prompts
from ha_mcp.tools import register_all_tools
from ha_mcp.resources.resources import register_resources
from ha_mcp.prompts.prompts import register_prompts

register_all_tools(mcp)
register_resources(mcp)
register_prompts(mcp)
