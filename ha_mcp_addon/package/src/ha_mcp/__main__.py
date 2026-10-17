import logging
import sys
from ha_mcp.config import settings
from ha_mcp.server import mcp


def main():
    """Run the HA MCP server with the configured transport."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    if not settings.ha_token:
        logger.error("HA_MCP_HA_TOKEN is required. Set it as an environment variable.")
        sys.exit(1)

    if settings.transport != "stdio" and not settings.api_key:
        if not settings.allow_unauthenticated:
            logger.error(
                "HA_MCP_API_KEY is required for the %s transport. Anyone who can "
                "reach the port gets admin access to Home Assistant. Set "
                "HA_MCP_ALLOW_UNAUTHENTICATED=true only on a trusted loopback setup.",
                settings.transport,
            )
            sys.exit(1)
        logger.warning("Running the %s transport WITHOUT authentication.", settings.transport)

    logger.info("Starting Home Assistant MCP Server (transport=%s)", settings.transport)

    if settings.transport == "stdio":
        mcp.run(transport="stdio")
    elif settings.transport == "http":
        mcp.run(transport="http", host=settings.host, port=settings.port)
    elif settings.transport == "sse":
        mcp.run(transport="sse", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
