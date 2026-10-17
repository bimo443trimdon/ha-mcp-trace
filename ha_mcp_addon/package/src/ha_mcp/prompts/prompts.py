"""MCP Prompt templates for guided Home Assistant workflows."""


def register_prompts(mcp_server):
    """Register all MCP prompt templates with the server."""

    @mcp_server.prompt()
    def create_automation_wizard(description: str, area: str = "") -> str:
        """Guided workflow to create a Home Assistant automation from a natural language description."""
        area_instruction = ""
        if area:
            area_instruction = (
                f"\n2. List the available devices and entities in the '{area}' area "
                f"by reading the ha://areas resource, then filtering ha://entities and "
                f"ha://devices to that area. Present a summary so the user can confirm "
                f"which entities to use."
            )
        else:
            area_instruction = (
                "\n2. If the description mentions a room or area, list the available "
                "devices and entities there by reading ha://areas, ha://entities, and "
                "ha://devices. Otherwise, identify the relevant entities from the "
                "description and look them up via ha://states."
            )

        return (
            f"Help me create a Home Assistant automation based on this description:\n"
            f"\"{description}\"\n\n"
            f"Follow these steps carefully:\n\n"
            f"1. Parse the description above and identify the intended trigger(s), "
            f"condition(s), and action(s). Summarize your understanding and ask for "
            f"confirmation before proceeding."
            f"{area_instruction}\n"
            f"3. Build the complete automation configuration with proper trigger, "
            f"condition, and action sections. Use the correct entity IDs discovered "
            f"in the previous step. Choose appropriate trigger platforms (state, time, "
            f"numeric_state, event, etc.) based on the description.\n"
            f"4. Validate the automation configuration using the validate_automation_config "
            f"tool to catch any errors before creating it.\n"
            f"5. Create the automation using the create_automation tool. Present the "
            f"dry-run result and ask for confirmation before finalizing.\n\n"
            f"Important: At each step, explain what you are doing and why. If anything "
            f"is ambiguous in the description, ask for clarification rather than guessing."
        )

    @mcp_server.prompt()
    def optimize_automations() -> str:
        """Analyze all existing automations and suggest improvements, detect conflicts, and identify gaps."""
        return (
            "Perform a comprehensive review of all Home Assistant automations and "
            "suggest improvements.\n\n"
            "Follow these steps:\n\n"
            "1. List all existing automations by reading the ha://automations resource. "
            "For each automation, retrieve its full configuration using the "
            "get_automation tool.\n"
            "2. Run the detect_automation_conflicts tool to identify any automations "
            "that may conflict with each other (overlapping triggers acting on the "
            "same entities, contradictory actions, race conditions). Present any "
            "conflicts found with explanations.\n"
            "3. Analyze automation coverage using the analyze_automation_coverage tool. "
            "Identify areas or devices that have no automations, entities that are "
            "used in triggers but never in actions (or vice versa), and common "
            "automation patterns that are missing.\n"
            "4. For each automation, suggest specific improvements such as:\n"
            "   - Adding conditions to prevent unnecessary runs\n"
            "   - Consolidating duplicate or near-duplicate automations\n"
            "   - Improving trigger specificity to reduce false activations\n"
            "   - Adding error handling or fallback actions\n"
            "   - Optimizing execution order\n\n"
            "Present a prioritized summary of all findings with actionable "
            "recommendations. For each suggestion, explain the benefit and offer "
            "to implement it."
        )

    @mcp_server.prompt()
    def build_dashboard(area: str = "") -> str:
        """Guided workflow to design and build a Lovelace dashboard."""
        area_filter = ""
        if area:
            area_filter = (
                f" Focus specifically on the '{area}' area. Filter entities "
                f"and devices to only those assigned to this area."
            )

        return (
            f"Help me design and build a Lovelace dashboard for Home Assistant."
            f"{area_filter}\n\n"
            f"Follow these steps:\n\n"
            f"1. List the relevant entities by reading ha://entities and ha://states."
            f"{' Filter to entities in the specified area.' if area else ''} "
            f"Group them by domain (lights, sensors, climate, media_player, etc.) "
            f"and present a summary of what is available.\n"
            f"2. Based on the available entities, suggest a dashboard layout. Consider:\n"
            f"   - A status overview section with key sensors and states\n"
            f"   - Control cards for lights, switches, and climate devices\n"
            f"   - Sensor history graphs for temperature, humidity, energy, etc.\n"
            f"   - Media player controls if applicable\n"
            f"   - Camera feeds if available\n"
            f"   Present the proposed layout and ask for feedback before proceeding.\n"
            f"3. Build the complete Lovelace dashboard YAML configuration using "
            f"appropriate card types (entities, glance, history-graph, "
            f"media-control, picture-entity, thermostat, etc.). Use proper views "
            f"and organize cards logically.\n"
            f"4. Save the dashboard using the create_dashboard tool. Present the "
            f"dry-run result for review and ask for confirmation before finalizing.\n\n"
            f"Aim for a clean, functional layout. Ask about preferences (dark theme, "
            f"compact layout, specific card styles) before building."
        )

    @mcp_server.prompt()
    def setup_helper_and_automation(helper_type: str, purpose: str) -> str:
        """Create an input helper entity and an automation that uses it together."""
        return (
            f"Help me create a '{helper_type}' input helper for the following purpose: "
            f"\"{purpose}\"\n\n"
            f"Then create an automation that uses this helper.\n\n"
            f"Follow these steps:\n\n"
            f"1. Create the appropriate input helper using the create_helper tool. "
            f"Based on the helper type '{helper_type}', configure it with:\n"
            f"   - A descriptive name and entity ID derived from the purpose\n"
            f"   - Appropriate options, min/max values, or defaults for the helper type\n"
            f"   - An icon that matches the purpose\n"
            f"   Present the helper configuration for review before creating it.\n"
            f"2. Create an automation that uses this helper as a trigger, condition, "
            f"or part of its action logic. The automation should:\n"
            f"   - Trigger when the helper value changes (or at a time set by the "
            f"helper, if it is a datetime/time helper)\n"
            f"   - Perform actions that align with the stated purpose\n"
            f"   - Use the helper's value in templates where appropriate\n"
            f"   Present the automation configuration for review before creating it.\n"
            f"3. Verify both the helper and automation were created successfully by:\n"
            f"   - Checking the helper state via ha://states\n"
            f"   - Retrieving the automation config with get_automation\n"
            f"   - Confirming the automation references the helper entity correctly\n\n"
            f"Explain at each step how the helper and automation work together."
        )

    @mcp_server.prompt()
    def import_and_configure_blueprint(url: str = "") -> str:
        """Import a community blueprint and configure it into a working automation or script."""
        if url:
            import_step = (
                f"1. Import the blueprint from the provided URL:\n"
                f"   {url}\n"
                f"   Use the import_blueprint tool to fetch and install it. "
                f"Report whether the import succeeded and show the blueprint metadata."
            )
        else:
            import_step = (
                "1. List existing blueprints by reading the ha://blueprints/automation "
                "and ha://blueprints/script resources. Present them in a clear list "
                "with their names, descriptions, and domains. Ask the user which "
                "blueprint they want to configure, or if they want to import a new "
                "one by URL."
            )

        return (
            f"Help me import and configure a Home Assistant blueprint.\n\n"
            f"Follow these steps:\n\n"
            f"{import_step}\n"
            f"2. Retrieve and display the blueprint's input schema. For each input, "
            f"show:\n"
            f"   - The input name and description\n"
            f"   - Whether it is required or optional\n"
            f"   - The expected type (entity, device, area, number, text, etc.)\n"
            f"   - Any default values or selectors\n"
            f"3. Help the user configure each input by:\n"
            f"   - Suggesting appropriate entities/devices from ha://entities and "
            f"ha://devices that match the input's selector type\n"
            f"   - Explaining what each input does in plain language\n"
            f"   - Validating that chosen values are compatible\n"
            f"4. Create the automation or script from the blueprint using the "
            f"appropriate creation tool with the configured inputs. Present the "
            f"dry-run result and ask for confirmation.\n\n"
            f"Make sure to explain what the blueprint does overall before diving "
            f"into configuration details."
        )

    @mcp_server.prompt()
    def troubleshoot_automation(automation_id: str) -> str:
        """Debug and troubleshoot a broken or misbehaving automation."""
        return (
            f"Help me troubleshoot the automation '{automation_id}'.\n\n"
            f"Follow these diagnostic steps:\n\n"
            f"1. Retrieve the full automation configuration using the get_automation "
            f"tool with entity_id '{automation_id}'. Display the trigger(s), "
            f"condition(s), and action(s) in a readable format.\n"
            f"2. Validate the automation configuration using validate_automation_config "
            f"to check for structural errors, missing required fields, or invalid "
            f"values. Report any validation errors found.\n"
            f"3. Check the current state of all entities referenced in the automation's "
            f"triggers and conditions. For each entity:\n"
            f"   - Show its current state and attributes\n"
            f"   - Verify the entity exists and is available\n"
            f"   - Check if the trigger conditions could currently be met\n"
            f"4. Check the logbook for recent executions of this automation using the "
            f"get_logbook tool. Look for:\n"
            f"   - When it last ran (or if it has never run)\n"
            f"   - Whether runs completed successfully or failed\n"
            f"   - The frequency of runs (too often may indicate a trigger issue)\n"
            f"5. Check the Home Assistant error log using the get_error_log tool for "
            f"any errors or warnings related to this automation or its referenced "
            f"entities. Filter for relevant entries.\n"
            f"6. Based on all findings, provide a diagnosis:\n"
            f"   - Identify the most likely cause of the problem\n"
            f"   - Suggest specific fixes with updated configuration if needed\n"
            f"   - Offer to apply the fixes using the update_automation tool\n\n"
            f"Be thorough and check each step even if an earlier step reveals an "
            f"obvious issue -- there may be multiple problems."
        )
