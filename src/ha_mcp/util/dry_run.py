import logging

import yaml
from fastmcp import Context
from fastmcp.exceptions import ToolError

from ha_mcp.config import settings

logger = logging.getLogger(__name__)


def _format_preview(
    action: str, entity_type: str, identifier: str, config: dict, validation_result: dict | None
) -> str:
    yaml_preview = yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    parts = [f"## {action.upper()} {entity_type}: {identifier}", "", "```yaml", yaml_preview.rstrip(), "```"]
    if validation_result:
        parts += ["", f"### Validation: {'PASSED' if validation_result.get('valid', True) else 'FAILED'}"]
        parts += [f"- {w}" for w in validation_result.get("warnings", [])]
    parts += ["", "Apply this change?"]
    return "\n".join(parts)


async def confirm_change(
    ctx: Context,
    action: str,
    entity_type: str,
    identifier: str,
    config: dict,
    validation_result: dict | None = None,
) -> bool:
    """Gate a mutating action. Returns False only when the user declines.

    Raises ToolError when validation fails, when the server is read-only, or when
    elicitation is required but the client cannot answer it, so the model sees why.
    The confirmation policy is a server setting, never a tool argument, so a model
    cannot talk its way past it.
    """
    if settings.read_only:
        raise ToolError("This MCP server is in read-only mode; changes are disabled.")

    if validation_result and not validation_result.get("valid", True):
        errors = "; ".join(validation_result.get("errors", [])) or "unknown error"
        raise ToolError(f"Validation failed for {entity_type} {identifier}: {errors}")

    if settings.confirm_mode == "client":
        logger.info("%s %s: %s (approval delegated to client)", action, entity_type, identifier)
        return True

    message = _format_preview(action, entity_type, identifier, config, validation_result)
    try:
        response = await ctx.elicit(message=message, response_type=["confirm", "cancel"])
    except Exception as exc:
        logger.warning("Elicitation unavailable: %s", exc)
        raise ToolError(
            "This server requires an in-client confirmation (confirm_mode=elicit), but the "
            "connected MCP client cannot show one. Switch confirm_mode to 'client' to rely "
            "on the client's own tool-approval prompt instead."
        ) from exc

    confirmed = response.action == "accept" and getattr(response, "data", None) == "confirm"
    logger.info(
        "User %s %s %s: %s", "confirmed" if confirmed else "cancelled", action, entity_type, identifier
    )
    return confirmed
