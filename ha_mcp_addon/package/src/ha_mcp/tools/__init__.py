"""MCP Tools for Home Assistant configuration management."""

from ha_mcp.config import settings
from ha_mcp.tools.registry import register_registry_tools
from ha_mcp.tools.registry_edit import register_registry_edit_tools
from ha_mcp.tools.state import register_state_tools
from ha_mcp.tools.automation import register_automation_tools
from ha_mcp.tools.script import register_script_tools
from ha_mcp.tools.scene import register_scene_tools
from ha_mcp.tools.helper import register_helper_tools
from ha_mcp.tools.dashboard import register_dashboard_tools
from ha_mcp.tools.blueprint import register_blueprint_tools
from ha_mcp.tools.config_validation import register_config_validation_tools
from ha_mcp.tools.suggestions import register_suggestion_tools
from ha_mcp.tools.system import register_system_tools
from ha_mcp.tools.integration import register_integration_tools
from ha_mcp.tools.backup import register_backup_tools
from ha_mcp.tools.control import register_control_tools
from ha_mcp.tools.events import register_event_tools
from ha_mcp.tools.config_flow import register_config_flow_tools
from ha_mcp.tools.registry_remove import register_registry_remove_tools
from ha_mcp.tools.diagnostics import register_diagnostics_tools
from ha_mcp.tools.categories import register_category_tools

READ_ONLY_PREFIXES = (
    "list_", "get_", "search_", "validate_", "render_", "analyze_",
    "suggest_", "detect_", "resolve_", "check_", "listen_", "find_",
)
DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "restart_", "restore_")
DEVICE_CONTROL_TOOLS = {"call_service"}


def classify_tool(name: str) -> dict:
    read_only = name.startswith(READ_ONLY_PREFIXES)
    return {
        "readOnlyHint": read_only,
        "destructiveHint": not read_only and (
            name.startswith(DESTRUCTIVE_PREFIXES) or name in DEVICE_CONTROL_TOOLS
        ),
        "openWorldHint": False,
    }


class _Registrar:
    """Applies annotations and the server's read-only/device-control policy to every tool."""

    def __init__(self, mcp) -> None:
        self._mcp = mcp

    def tool(self, *args, **kwargs):
        register = self._mcp.tool

        def decorator(fn):
            name = kwargs.get("name") or fn.__name__
            annotations = classify_tool(name)
            if settings.read_only and not annotations["readOnlyHint"]:
                return fn
            if name in DEVICE_CONTROL_TOOLS and not settings.enable_device_control:
                return fn
            return register(*args, annotations=annotations, **kwargs)(fn)

        return decorator


def register_all_tools(mcp):
    """Register all tool modules with the MCP server."""
    registrar = _Registrar(mcp)
    register_registry_tools(registrar)
    register_registry_edit_tools(registrar)
    register_state_tools(registrar)
    register_automation_tools(registrar)
    register_script_tools(registrar)
    register_scene_tools(registrar)
    register_helper_tools(registrar)
    register_dashboard_tools(registrar)
    register_blueprint_tools(registrar)
    register_config_validation_tools(registrar)
    register_suggestion_tools(registrar)
    register_system_tools(registrar)
    register_integration_tools(registrar)
    register_backup_tools(registrar)
    register_control_tools(registrar)
    register_event_tools(registrar)
    register_config_flow_tools(registrar)
    register_registry_remove_tools(registrar)
    register_diagnostics_tools(registrar)
    register_category_tools(registrar)
