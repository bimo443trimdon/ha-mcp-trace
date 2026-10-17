"""Validation of automation/script building blocks via HA's validate_config."""

import logging

logger = logging.getLogger(__name__)


def _pick(config: dict, plural: str, singular: str) -> list:
    value = config.get(plural, config.get(singular, []))
    return value if isinstance(value, list) else [value]


async def validate_config_parts(
    ws,
    *,
    triggers: list | None = None,
    conditions: list | None = None,
    actions: list | None = None,
) -> dict:
    """Return {"valid", "errors", "warnings"} for the given parts.

    HA answers per section ({"trigger": {"valid": bool, "error": str|None}, ...}),
    so validity is derived from every section rather than a top-level flag.
    """
    payload = {
        key: value
        for key, value in (("trigger", triggers), ("condition", conditions), ("action", actions))
        if value is not None
    }
    try:
        result = await ws.send_command("validate_config", **payload)
    except Exception as exc:
        logger.warning("validate_config failed: %s", exc)
        return {"valid": False, "errors": [f"Validation request failed: {exc}"], "warnings": []}

    errors = [
        f"{key}: {section.get('error') or 'invalid'}"
        for key, section in (result or {}).items()
        if isinstance(section, dict) and section.get("valid") is False
    ]
    return {"valid": not errors, "errors": errors, "warnings": []}


async def validate_automation(ws, config: dict) -> dict:
    return await validate_config_parts(
        ws,
        triggers=_pick(config, "triggers", "trigger"),
        conditions=_pick(config, "conditions", "condition"),
        actions=_pick(config, "actions", "action"),
    )

