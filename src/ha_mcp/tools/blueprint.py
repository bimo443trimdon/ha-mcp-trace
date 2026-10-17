"""Blueprint management tools for Home Assistant."""

import json
import logging
import uuid

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


def register_blueprint_tools(mcp_server):
    """Register all blueprint management tools on the MCP server."""

    @mcp_server.tool()
    async def list_blueprints(ctx: Context, domain: str | None = None) -> str:
        """List available blueprints in Home Assistant.

        Parameters:
            domain: Filter by domain - "automation" or "script".
                If not provided, blueprints from both domains are returned.

        Returns a JSON object keyed by domain, each containing a dict of
        blueprint paths and their metadata (e.g. name, description).

        Use this to discover available blueprints before creating entities
        from them or to see which community blueprints have been imported.
        """
        ws, _rest = get_clients(ctx)

        if domain is not None:
            if domain not in ("automation", "script"):
                return json.dumps({
                    "success": False,
                    "error": f"Invalid domain '{domain}'. Must be 'automation' or 'script'.",
                })
            result = await ws.send_command("blueprint/list", domain=domain)
            return json.dumps({"domain": domain, "blueprints": result}, indent=2)

        # Query both domains and merge results
        blueprints = {}
        for d in ("automation", "script"):
            try:
                result = await ws.send_command("blueprint/list", domain=d)
                blueprints[d] = result
            except Exception as e:
                logger.warning("Failed to list blueprints for domain '%s': %s", d, e)
                blueprints[d] = {"error": str(e)}

        return json.dumps(blueprints, indent=2)

    @mcp_server.tool()
    async def get_blueprint(ctx: Context, domain: str, path: str) -> str:
        """Get the full configuration of a specific blueprint.

        Parameters:
            domain: The blueprint domain - "automation" or "script".
            path: The blueprint path (e.g. 'homeassistant/motion_light.yaml'
                or a community blueprint path as shown in list_blueprints).

        Returns the complete blueprint configuration as JSON, including
        the blueprint metadata (name, description, domain) and the inputs
        schema that defines what parameters the blueprint accepts.
        """
        ws, _rest = get_clients(ctx)

        if domain not in ("automation", "script"):
            return json.dumps({
                "success": False,
                "error": f"Invalid domain '{domain}'. Must be 'automation' or 'script'.",
            })

        result = await ws.send_command("blueprint/get", domain=domain, path=path)
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def import_blueprint(
        ctx: Context, url: str
    ) -> str:
        """Import a community blueprint from a URL into Home Assistant.

        Parameters:
            url: The URL of the blueprint to import. Typically a GitHub URL
                or a Home Assistant community forum blueprint URL.

        The blueprint is fetched from the URL and its configuration is shown
        for review before saving. Once imported, it can be used to create
        automations or scripts via create_from_blueprint.

        Returns the imported blueprint's path and domain on success.
        """
        if not url.lower().startswith("https://"):
            return json.dumps({"success": False, "error": "Only https:// blueprint URLs are allowed."})

        ws, _rest = get_clients(ctx)

        # First, import the blueprint to retrieve its configuration
        try:
            result = await ws.send_command("blueprint/import", url=url)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to import blueprint from URL: {e}",
            })

        # The import command returns the blueprint config for confirmation
        suggested_filename = result.get("suggested_filename", "unknown.yaml")
        blueprint_config = result.get("raw_data", result)
        blueprint_domain = result.get("blueprint", {}).get("domain", "automation")

        # Confirm the import with the user
        confirmed = await confirm_change(
            ctx,
            action="IMPORT",
            entity_type="blueprint",
            identifier=f"{blueprint_domain}/{suggested_filename}",
            config=blueprint_config if isinstance(blueprint_config, dict) else {"raw_data": blueprint_config},
        )

        if not confirmed:
            return json.dumps({
                "success": False,
                "error": "Blueprint import cancelled by user.",
            })

        # Save the imported blueprint
        try:
            save_result = await ws.send_command(
                "blueprint/save",
                domain=blueprint_domain,
                path=suggested_filename,
                yaml=result.get("raw_data", ""),
                source_url=url,
            )
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to save imported blueprint: {e}",
            })

        return json.dumps({
            "success": True,
            "domain": blueprint_domain,
            "path": suggested_filename,
            "message": (
                f"Blueprint imported successfully as "
                f"'{blueprint_domain}/{suggested_filename}'."
            ),
        }, indent=2)

    @mcp_server.tool()
    async def create_from_blueprint(
        ctx: Context,
        domain: str,
        blueprint_path: str,
        inputs: str,
    ) -> str:
        """Create an automation or script from an existing blueprint.

        Parameters:
            domain: The target domain - "automation" or "script".
            blueprint_path: The blueprint path as shown in list_blueprints
                (e.g. 'homeassistant/motion_light.yaml').
            inputs: A JSON string containing the blueprint input values.
                These correspond to the 'input' schema defined in the
                blueprint. May also include 'alias' and 'description' keys
                to set the entity's display name and description.

        Builds the appropriate configuration using the blueprint reference
        and input values, then saves and reloads the domain.

        Returns the created entity's ID and details on success.
        """
        ws, rest = get_clients(ctx)

        if domain not in ("automation", "script"):
            return json.dumps({
                "success": False,
                "error": f"Invalid domain '{domain}'. Must be 'automation' or 'script'.",
            })

        # Parse the inputs JSON
        try:
            inputs_dict = json.loads(inputs)
        except json.JSONDecodeError as e:
            return json.dumps({
                "success": False,
                "error": f"Invalid JSON in inputs: {e}",
            })

        if not isinstance(inputs_dict, dict):
            return json.dumps({
                "success": False,
                "error": "Inputs must be a JSON object.",
            })

        # Extract optional top-level config fields from inputs
        alias = inputs_dict.pop("alias", None)
        description = inputs_dict.pop("description", None)

        # Build the entity config with the blueprint reference
        config = {
            "use_blueprint": {
                "path": blueprint_path,
                "input": inputs_dict,
            },
        }

        if alias:
            config["alias"] = alias
        if description:
            config["description"] = description

        # Generate an ID for the new entity
        entity_id_slug = alias.lower().replace(" ", "_").replace("-", "_") if alias else str(uuid.uuid4())
        # Clean the slug to only valid characters
        entity_id_slug = "".join(
            c for c in entity_id_slug if c.isalnum() or c == "_"
        )
        if not entity_id_slug or not entity_id_slug[0].isalpha():
            entity_id_slug = f"bp_{entity_id_slug}" if entity_id_slug else str(uuid.uuid4())

        identifier = alias or f"{domain}/{blueprint_path}"

        # Confirm the change with the user
        confirmed = await confirm_change(
            ctx,
            action="CREATE",
            entity_type=f"{domain} (from blueprint)",
            identifier=identifier,
            config=config,
        )

        if not confirmed:
            return json.dumps({
                "success": False,
                "error": f"{domain.capitalize()} creation from blueprint cancelled by user.",
            })

        # Save via the appropriate REST endpoint and reload
        try:
            if domain == "automation":
                await rest.save_automation_config(entity_id_slug, config)
                await ws.send_command(
                    "call_service", domain="automation", service="reload",
                )
            else:
                await rest.save_script_config(entity_id_slug, config)
                await ws.send_command(
                    "call_service", domain="script", service="reload",
                )
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to create {domain} from blueprint: {e}",
            })

        entity_id = f"{domain}.{entity_id_slug}"
        logger.info("Created %s from blueprint: %s", domain, entity_id)

        return json.dumps({
            "success": True,
            "domain": domain,
            "entity_id": entity_id,
            "slug": entity_id_slug,
            "blueprint_path": blueprint_path,
            "message": (
                f"{domain.capitalize()} created from blueprint "
                f"'{blueprint_path}' as '{entity_id}'."
            ),
        }, indent=2)
