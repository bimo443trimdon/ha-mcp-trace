# Prompts reference

Home Assistant MCP Server includes six prompt templates that
guide AI assistants through common multi-step workflows. Each
prompt generates a structured set of instructions that the
assistant follows to complete the task.

Prompts are different from tools. While tools perform a single
operation, prompts orchestrate a series of tool calls with
user interaction at each step.

## `create_automation_wizard`

A guided workflow for creating a Home Assistant automation from a
natural language description. The assistant parses your
description, identifies the right entities, builds the
configuration, validates it, and creates the automation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `description` | `string` | Yes | Natural language description of the desired automation |
| `area` | `string` | No | Area to focus on (for example, `living_room`) |

The workflow follows these steps:

1. Parse the description to identify triggers, conditions, and
   actions. Summarize the interpretation and ask for confirmation.
2. Discover relevant entities and devices. If an area is specified,
   filter to that area.
3. Build the complete automation configuration with correct entity
   IDs and appropriate trigger platforms.
4. Validate the configuration using `validate_automation_config`.
5. Create the automation using `create_automation` with a dry-run
   preview.

## `optimize_automations`

A comprehensive review of all existing automations that suggests
improvements, detects conflicts, and identifies coverage gaps.

No parameters.

The workflow follows these steps:

1. List all automations and retrieve each one's full
   configuration.
2. Run `detect_automation_conflicts` to find overlapping triggers,
   contradictory actions, and race conditions.
3. Run `analyze_automation_coverage` (via `analyze_devices`) to
   find areas and devices without automation coverage.
4. Suggest specific improvements for each automation, such as
   adding conditions, consolidating duplicates, improving trigger
   specificity, and adding error handling.

## `build_dashboard`

A guided workflow for designing and building a Lovelace dashboard.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `area` | `string` | No | Focus the dashboard on a specific area |

The workflow follows these steps:

1. List relevant entities and group them by domain (lights,
   sensors, climate, media players, and more).
2. Suggest a dashboard layout with status overviews, control
   cards, sensor history graphs, media controls, and camera feeds.
3. Build the complete Lovelace YAML configuration with appropriate
   card types.
4. Save the dashboard using `create_dashboard` (via
   `save_dashboard_config`) with a dry-run preview.

## `setup_helper_and_automation`

Create an input helper entity and an automation that uses it
together as a coordinated pair.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `helper_type` | `string` | Yes | Type of helper (for example, `input_boolean`, `input_number`) |
| `purpose` | `string` | Yes | Natural language description of what the helper is for |

The workflow follows these steps:

1. Create the input helper with a descriptive name, appropriate
   defaults, and a matching icon.
2. Create an automation that triggers on the helper's value
   changes and performs actions aligned with the stated purpose.
3. Verify both were created correctly and that the automation
   references the helper entity.

## `import_and_configure_blueprint`

Import a community blueprint and configure it into a working
automation or script.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `url` | `string` | No | URL of a blueprint to import. If omitted, lists existing blueprints instead. |

The workflow follows these steps:

1. Import the blueprint from the URL, or list existing blueprints
   and ask which one to configure.
2. Display the blueprint's input schema with descriptions,
   required/optional status, expected types, and defaults.
3. Help configure each input by suggesting matching entities and
   devices from your Home Assistant instance.
4. Create the automation or script from the blueprint with the
   configured inputs.

## `troubleshoot_automation`

Debug and troubleshoot a broken or misbehaving automation through
a systematic diagnostic process.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `automation_id` | `string` | Yes | Entity ID of the automation to troubleshoot |

The workflow follows these steps:

1. Retrieve the automation's full configuration and display its
   triggers, conditions, and actions.
2. Validate the configuration for structural errors or invalid
   values.
3. Check the current state of all referenced entities to verify
   they exist and are available.
4. Check the logbook for recent executions, failures, and
   frequency patterns.
5. Check the error log for related warnings or errors.
6. Provide a diagnosis with the most likely cause and offer
   specific fixes.
