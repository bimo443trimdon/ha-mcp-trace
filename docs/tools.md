# Tools reference

Home Assistant MCP Server exposes tools organized into 10 categories.
The available tools depend on the server version and enabled features.
Each tool accepts a `ctx` parameter automatically provided by the MCP
framework -- you don't need to supply it. All tools return JSON strings.

Each tool is tagged with MCP tool annotations, so clients can tell
read-only tools from ones that change things:

- *read-only* -- never modifies Home Assistant.
- *writes* -- creates or updates configuration.
- *destructive* -- deletes something, restarts core, or controls devices.

Changes are gated by the server's `confirm_mode` setting, not by a tool
argument (see [configuration](configuration.md#confirmation)). Automation
and script configs are always validated against Home Assistant before
they are saved, and a failed validation blocks the change.

This file is generated from the live tool registry.

## Integration setup (config flows)

> New in 0.2.0. Not yet verified against a live Home Assistant.

### `abort_config_flow`

*writes*. Cancel a flow in progress.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `flow_kind` | `string` | No |

### `continue_config_flow`

*writes*. Submit the current step of a config flow.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `user_input` | `string` | No |

### `continue_options_flow`

*writes*. Submit the current step of an options flow.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `user_input` | `string` | No |

### `continue_subentry_flow`

*writes*. Submit the current step of a subentry flow.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `user_input` | `string` | No |

### `delete_config_entry`

*destructive*. Delete a config entry: removes the integration instance with its devices and entities.

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |

### `get_config_flow`

*read-only*. Get the current step of a flow without submitting anything.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `flow_kind` | `string` | No |

### `ignore_config_flow`

*writes*. Ignore a discovered device/integration so HA stops offering it.

| Parameter | Type | Required |
|---|---|---|
| `flow_id` | `string` | Yes |
| `title` | `string` | Yes |

### `list_config_flow_handlers`

*read-only*. List the domains that can be set up through a config flow.

| Parameter | Type | Required |
|---|---|---|
| `handler_type` | `string` | No |

### `list_config_flows_in_progress`

*read-only*. List config flows currently in progress, including discovered devices.

### `list_config_subentries`

*read-only*. List the subentries of a config entry (e.g. per-agent or per-location items).

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |

### `start_config_flow`

*writes*. Start setting up an integration or config-flow helper.

| Parameter | Type | Required |
|---|---|---|
| `handler` | `string` | Yes |
| `entry_id` | `string` | No |

### `start_options_flow`

*writes*. Start changing the options of an existing integration/helper entry.

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |

### `start_subentry_flow`

*writes*. Start a flow that adds (or reconfigures) a subentry of a config entry.

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |
| `subentry_type` | `string` | Yes |
| `subentry_id` | `string` | No |

## Integrations

### `list_integrations`

*read-only*. List configured integrations (config entries).

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |

### `reload_integration`

*writes*. Reload an integration (config entry) by its entry_id.

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |

### `set_integration_enabled`

*writes*. Enable or disable an integration (config entry).

| Parameter | Type | Required |
|---|---|---|
| `entry_id` | `string` | Yes |
| `enabled` | `boolean` | Yes |

## Registry queries

### `get_entity_details`

*read-only*. Get detailed information about a specific entity combining registry data and live state.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |

### `list_areas`

*read-only*. List all areas registered in Home Assistant.

### `list_devices`

*read-only*. List all devices registered in Home Assistant with optional filters.

| Parameter | Type | Required |
|---|---|---|
| `area_id` | `string` | No |
| `manufacturer` | `string` | No |
| `model` | `string` | No |

### `list_entities`

*read-only*. List all entities registered in Home Assistant with optional filters.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |
| `device_id` | `string` | No |
| `area_id` | `string` | No |

### `list_floors`

*read-only*. List all floors registered in Home Assistant.

### `list_labels`

*read-only*. List all labels registered in Home Assistant.

### `search_entities`

*read-only*. Search entities by name, ID, or attributes using case-insensitive substring matching.

| Parameter | Type | Required |
|---|---|---|
| `query` | `string` | Yes |
| `domain` | `string` | No |

## Registry editing

### `create_area`

*writes*. Create a new area in the area registry.

| Parameter | Type | Required |
|---|---|---|
| `name` | `string` | Yes |
| `floor_id` | `string` | No |
| `icon` | `string` | No |
| `labels` | `array` | No |
| `aliases` | `array` | No |

### `create_floor`

*writes*. Create a new floor in the floor registry.

| Parameter | Type | Required |
|---|---|---|
| `name` | `string` | Yes |
| `level` | `integer` | No |
| `icon` | `string` | No |
| `aliases` | `array` | No |

### `create_label`

*writes*. Create a new label in the label registry.

| Parameter | Type | Required |
|---|---|---|
| `name` | `string` | Yes |
| `color` | `string` | No |
| `icon` | `string` | No |
| `description` | `string` | No |

### `delete_area`

*destructive*. Delete an area from the registry.

| Parameter | Type | Required |
|---|---|---|
| `area_id` | `string` | Yes |

### `delete_floor`

*destructive*. Delete a floor from the registry.

| Parameter | Type | Required |
|---|---|---|
| `floor_id` | `string` | Yes |

### `delete_label`

*destructive*. Delete a label from the registry.

| Parameter | Type | Required |
|---|---|---|
| `label_id` | `string` | Yes |

### `update_area`

*writes*. Update an existing area (rename, move to a floor, set icon/labels).

| Parameter | Type | Required |
|---|---|---|
| `area_id` | `string` | Yes |
| `name` | `string` | No |
| `floor_id` | `string` | No |
| `icon` | `string` | No |
| `labels` | `array` | No |
| `aliases` | `array` | No |

### `update_device`

*writes*. Update a device in the device registry (rename, assign area, label).

| Parameter | Type | Required |
|---|---|---|
| `device_id` | `string` | Yes |
| `name_by_user` | `string` | No |
| `area_id` | `string` | No |
| `labels` | `array` | No |
| `disabled` | `boolean` | No |

### `update_entity`

*writes*. Update an entity in the entity registry.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |
| `name` | `string` | No |
| `icon` | `string` | No |
| `area_id` | `string` | No |
| `new_entity_id` | `string` | No |
| `labels` | `array` | No |
| `hidden` | `boolean` | No |
| `disabled` | `boolean` | No |
| `aliases` | `array` | No |

### `update_floor`

*writes*. Update an existing floor (rename, set level/icon/aliases).

| Parameter | Type | Required |
|---|---|---|
| `floor_id` | `string` | Yes |
| `name` | `string` | No |
| `level` | `integer` | No |
| `icon` | `string` | No |
| `aliases` | `array` | No |

### `update_label`

*writes*. Update an existing label (rename, set color/icon/description).

| Parameter | Type | Required |
|---|---|---|
| `label_id` | `string` | Yes |
| `name` | `string` | No |
| `color` | `string` | No |
| `icon` | `string` | No |
| `description` | `string` | No |

## Registry removal

> New in 0.2.0. Not yet verified against a live Home Assistant.

### `remove_device`

*destructive*. Remove a device and its entities from Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `device_id` | `string` | Yes |

### `remove_entity`

*destructive*. Remove an entity from the entity registry.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |

## Categories

> New in 0.2.0. Not yet verified against a live Home Assistant.

### `assign_category`

*writes*. Put an entity (automation, script, scene, helper) in a category.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |
| `scope` | `string` | Yes |
| `category_id` | `string` | No |

### `create_category`

*writes*. Create a category in a scope.

| Parameter | Type | Required |
|---|---|---|
| `scope` | `string` | Yes |
| `name` | `string` | Yes |
| `icon` | `string` | No |

### `delete_category`

*destructive*. Delete a category. Items in it become uncategorised.

| Parameter | Type | Required |
|---|---|---|
| `scope` | `string` | Yes |
| `category_id` | `string` | Yes |

### `list_categories`

*read-only*. List the categories defined for one scope.

| Parameter | Type | Required |
|---|---|---|
| `scope` | `string` | Yes |

### `update_category`

*writes*. Rename a category or change its icon.

| Parameter | Type | Required |
|---|---|---|
| `scope` | `string` | Yes |
| `category_id` | `string` | Yes |
| `name` | `string` | No |
| `icon` | `string` | No |

## Automations

### `create_automation`

*writes*. Create a new automation in Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `config` | `string` | Yes |

### `delete_automation`

*destructive*. Delete an automation from Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `automation_id` | `string` | Yes |

### `get_automation_traces`

Fetch recent stored traces for an automation. Returns full trace
details, including trigger data and action results.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `automation_id` | `string` | Yes | Automation entity ID (for example, `automation.garage_door`) |
| `limit` | `integer` | No | Number of most recent traces to return (1–10; default 3) |

### `duplicate_automation`

*writes*. Duplicate an existing automation with a new ID.

| Parameter | Type | Required |
|---|---|---|
| `automation_id` | `string` | Yes |
| `new_alias` | `string` | No |

### `get_automation`

*read-only*. Get the full configuration of a single automation.

| Parameter | Type | Required |
|---|---|---|
| `automation_id` | `string` | Yes |

### `list_automations`

*read-only*. List all automations in Home Assistant.

### `toggle_automation`

*writes*. Enable or disable an automation.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |
| `enabled` | `boolean` | Yes |

### `update_automation`

*writes*. Update an existing automation's configuration.

| Parameter | Type | Required |
|---|---|---|
| `automation_id` | `string` | Yes |
| `config` | `string` | Yes |

## Scripts

### `create_script`

*writes*. Create a new Home Assistant script.

| Parameter | Type | Required |
|---|---|---|
| `script_id` | `string` | Yes |
| `config` | `string` | Yes |

### `delete_script`

*destructive*. Delete an existing Home Assistant script.

| Parameter | Type | Required |
|---|---|---|
| `script_id` | `string` | Yes |

### `get_script`

*read-only*. Get the full configuration of a Home Assistant script.

| Parameter | Type | Required |
|---|---|---|
| `script_id` | `string` | Yes |

### `list_scripts`

*read-only*. List all scripts registered in Home Assistant.

### `update_script`

*writes*. Update an existing Home Assistant script.

| Parameter | Type | Required |
|---|---|---|
| `script_id` | `string` | Yes |
| `config` | `string` | Yes |

## Scenes

### `create_scene`

*writes*. Create a new Home Assistant scene.

| Parameter | Type | Required |
|---|---|---|
| `config` | `string` | Yes |

### `delete_scene`

*destructive*. Delete a Home Assistant scene.

| Parameter | Type | Required |
|---|---|---|
| `scene_id` | `string` | Yes |

### `get_scene`

*read-only*. Get the full configuration of a Home Assistant scene.

| Parameter | Type | Required |
|---|---|---|
| `scene_id` | `string` | Yes |

### `list_scenes`

*read-only*. List all scenes registered in Home Assistant.

### `update_scene`

*writes*. Update an existing Home Assistant scene.

| Parameter | Type | Required |
|---|---|---|
| `scene_id` | `string` | Yes |
| `config` | `string` | Yes |

## Helpers

### `create_helper`

*writes*. Create a new UI-managed helper in Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `helper_type` | `string` | Yes |
| `config` | `string` | Yes |

### `delete_helper`

*destructive*. Delete a UI-managed helper permanently.

| Parameter | Type | Required |
|---|---|---|
| `helper_type` | `string` | Yes |
| `entity_id` | `string` | Yes |

### `list_helpers`

*read-only*. List helper entities (input_*, counter, timer, schedule) and their states.

| Parameter | Type | Required |
|---|---|---|
| `helper_type` | `string` | No |

### `update_helper`

*writes*. Update a UI-managed helper.

| Parameter | Type | Required |
|---|---|---|
| `helper_type` | `string` | Yes |
| `entity_id` | `string` | Yes |
| `config` | `string` | Yes |

## Dashboards

### `add_card`

*writes*. Add a card to a view in a Lovelace dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_index` | `integer` | Yes |
| `card_config` | `string` | Yes |
| `dashboard_id` | `string` | No |

### `add_view`

*writes*. Add a new view to a Lovelace dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_config` | `string` | Yes |
| `dashboard_id` | `string` | No |
| `position` | `integer` | No |

### `delete_view`

*destructive*. Delete a view from a Lovelace dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_index` | `integer` | Yes |
| `dashboard_id` | `string` | No |

### `get_dashboard_config`

*read-only*. Get the full Lovelace configuration of a dashboard.

| Parameter | Type | Required |
|---|---|---|
| `dashboard_id` | `string` | No |

### `get_view`

*read-only*. Get the configuration of a single view from a dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_index` | `integer` | Yes |
| `dashboard_id` | `string` | No |

### `list_dashboards`

*read-only*. List all Lovelace dashboards configured in Home Assistant.

### `save_dashboard_config`

*writes*. Save a complete Lovelace dashboard configuration.

| Parameter | Type | Required |
|---|---|---|
| `config` | `string` | Yes |
| `dashboard_id` | `string` | No |

### `update_card`

*writes*. Replace a card in a view of a Lovelace dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_index` | `integer` | Yes |
| `card_index` | `integer` | Yes |
| `card_config` | `string` | Yes |
| `dashboard_id` | `string` | No |

### `update_view`

*writes*. Replace a view in a Lovelace dashboard.

| Parameter | Type | Required |
|---|---|---|
| `view_index` | `integer` | Yes |
| `view_config` | `string` | Yes |
| `dashboard_id` | `string` | No |

## Blueprints

### `create_from_blueprint`

*writes*. Create an automation or script from an existing blueprint.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |
| `blueprint_path` | `string` | Yes |
| `inputs` | `string` | Yes |

### `get_blueprint`

*read-only*. Get the full configuration of a specific blueprint.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |
| `path` | `string` | Yes |

### `import_blueprint`

*writes*. Import a community blueprint from a URL into Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `url` | `string` | Yes |

### `list_blueprints`

*read-only*. List available blueprints in Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |

## Configuration validation

### `check_config`

*read-only*. Check the Home Assistant core configuration for errors.

### `validate_automation_config`

*read-only*. Validate an automation configuration against Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `config` | `string` | Yes |

### `validate_yaml`

*read-only*. Validate YAML syntax without connecting to Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `yaml_text` | `string` | Yes |

## Diagnostics (repairs, logs, traces, trigger discovery)

> New in 0.2.0. Not yet verified against a live Home Assistant.

### `find_conditions_for_target`

*read-only*. List the purpose-specific conditions usable for a target (HA 2025.12+).

| Parameter | Type | Required |
|---|---|---|
| `target` | `string` | Yes |
| `expand_group` | `boolean` | No |

### `find_services_for_target`

*read-only*. List the actions (services) usable for a target (HA 2025.12+).

| Parameter | Type | Required |
|---|---|---|
| `target` | `string` | Yes |
| `expand_group` | `boolean` | No |

### `find_triggers_for_target`

*read-only*. List the purpose-specific triggers usable for a target (HA 2025.12+).

| Parameter | Type | Required |
|---|---|---|
| `target` | `string` | Yes |
| `expand_group` | `boolean` | No |

### `get_system_log`

*read-only*. Get the structured, deduplicated system log (Settings > System > Logs).

| Parameter | Type | Required |
|---|---|---|
| `level` | `string` | No |
| `logger_filter` | `string` | No |

### `get_trace`

*read-only*. Explain one automation/script run: what triggered it, which conditions passed, which step failed and why.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |
| `item_id` | `string` | Yes |
| `run_id` | `string` | Yes |

### `get_automation_diagnosis`

*read-only*. Diagnose an automation using its current enabled state,
recent stored traces, history for referenced trigger/condition entities,
and matching logbook entries. The result separates observations from
hypotheses, cites evidence sources and timestamps, and explains why an
empty trace result does not prove the automation never ran.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `automation_id` | `string` | Yes | Automation entity ID (for example, `automation.garage_door`) or config ID |
| `lookback_minutes` | `integer` | No | Evidence window, 1–1440 minutes (default 60) |
| `trace_limit` | `integer` | No | Maximum recent traces to retrieve, 1–5 (default 3) |

### `ignore_repair`

*writes*. Ignore (or un-ignore) a Repairs issue.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |
| `issue_id` | `string` | Yes |
| `ignore` | `boolean` | No |

### `list_repairs`

*read-only*. List open Repairs issues (Settings > System > Repairs).

| Parameter | Type | Required |
|---|---|---|
| `include_ignored` | `boolean` | No |

### `list_traces`

*read-only*. List stored execution traces for automations or scripts.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |
| `item_id` | `string` | No |

## State inspection

### `get_all_states`

*read-only*. Get the current state of all entities in Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |

### `get_entity_history`

*read-only*. Get the state change history of a Home Assistant entity.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |
| `start_time` | `string` | No |
| `end_time` | `string` | No |

### `get_entity_state`

*read-only*. Get the full current state of a single Home Assistant entity.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | Yes |

### `get_error_log`

*read-only*. Get the Home Assistant error log.

### `get_logbook`

*read-only*. Get logbook entries from Home Assistant.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | No |
| `start_time` | `string` | No |
| `end_time` | `string` | No |

### `render_template`

*read-only*. Render a Home Assistant Jinja2 template and return the result.

| Parameter | Type | Required |
|---|---|---|
| `template` | `string` | Yes |

## Backups

### `create_backup`

*writes*. Create a Home Assistant backup, e.g. before risky configuration changes.

| Parameter | Type | Required |
|---|---|---|
| `name` | `string` | No |
| `agent_ids` | `array` | No |
| `include_database` | `boolean` | No |

### `delete_backup`

*destructive* (new in 0.2.0, not yet verified against a live HA). Permanently delete a backup from all agents that hold it.

| Parameter | Type | Required |
|---|---|---|
| `backup_id` | `string` | Yes |

### `get_backup_config`

*read-only* (new in 0.2.0, not yet verified against a live HA). Get the automatic backup configuration: schedule, retention, which agents to back up to, what to include, and per-agent settings. The backup encryption password is redacted.

### `list_backup_agents`

*read-only* (new in 0.2.0, not yet verified against a live HA). List backup agents (storage locations) such as 'backup.local', 'hassio.local', cloud or network storage. Use their agent_id values in create_backup and update_backup_config.

### `list_backups`

*read-only*. List Home Assistant backups and the automatic-backup status.

### `update_backup_config`

*writes* (new in 0.2.0, not yet verified against a live HA). Update the automatic backup configuration.

| Parameter | Type | Required |
|---|---|---|
| `config` | `string` | Yes |

## System

### `get_config`

*read-only*. Get Home Assistant core configuration.

### `get_system_health`

*read-only*. Get system health information for Home Assistant and its integrations.

### `list_services`

*read-only*. List the services available in Home Assistant, optionally for one domain.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | No |

### `reload_domain`

*writes*. Reload a configuration domain so YAML/config changes take effect.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |

### `resolve_target`

*read-only*. Resolve a service target into the concrete entities/devices/areas it covers.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `array` | No |
| `device_id` | `array` | No |
| `area_id` | `array` | No |
| `label_id` | `array` | No |
| `expand_group` | `boolean` | No |

### `restart_home_assistant`

*destructive*. Restart the Home Assistant core (validates config first).

| Parameter | Type | Required |
|---|---|---|
| `safe_mode` | `boolean` | No |

## Suggestions

### `analyze_devices`

*read-only*. Analyse device and entity coverage across areas.

| Parameter | Type | Required |
|---|---|---|
| `area_id` | `string` | No |

### `detect_automation_conflicts`

*read-only*. Detect potential conflicts or redundancies between automations.

### `suggest_automations`

*read-only*. Suggest new automations based on existing devices and entities.

| Parameter | Type | Required |
|---|---|---|
| `entity_id` | `string` | No |
| `area_id` | `string` | No |

### `suggest_dashboard`

*read-only*. Suggest a Lovelace dashboard layout based on registered entities.

| Parameter | Type | Required |
|---|---|---|
| `area_id` | `string` | No |

## Live events

### `listen_events`

*read-only*. Listen for live Home Assistant events for a bounded time window.

| Parameter | Type | Required |
|---|---|---|
| `event_type` | `string` | No |
| `duration_seconds` | `number` | No |
| `entity_id` | `string` | No |
| `max_events` | `integer` | No |

## Device control

### `call_service`

*destructive*. Call a Home Assistant service to control a device or trigger an action.

| Parameter | Type | Required |
|---|---|---|
| `domain` | `string` | Yes |
| `service` | `string` | Yes |
| `data` | `string` | No |
