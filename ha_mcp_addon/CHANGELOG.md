# Changelog

## 0.1.10

- Expose recent Home Assistant automation traces through the
  `get_automation_traces` MCP tool
## 0.2.2

### Added
- `update_entity` accepts `display_precision` to set how many decimals a sensor shows.

## 0.2.1

### Fixed
- Automation and script saves failed validation on current Home Assistant: `validate_config` now gets `triggers`/`conditions`/`actions` instead of the removed singular keys.

## 0.2.0

### Breaking
- MCP clients must authenticate with `Authorization: Bearer <API_KEY>`. A key is generated on first start and shown in the MCP Server panel; the `api_key` option overrides it.
- The endpoint is `/mcp` (no trailing slash).
- The `transport` option was removed. New options: `api_key`, `confirm_mode`, `read_only`, `enable_device_control`.
- Tools no longer accept `skip_confirm`. Confirmation is controlled by `confirm_mode`.
- `call_service` is off by default; dangerous services are always blocked.

### Security
- API-key auth on port 8099. The pip version refuses HTTP without a key and binds to 127.0.0.1 by default.
- The connection-guide panel only answers the Home Assistant ingress proxy.
- Failed automation/script validation now blocks saving, including when confirmation is delegated.
- Identifiers are escaped in REST paths, and WebSocket message `id`/`type` can no longer be overridden by tool input.
- Error logs are truncated and secrets redacted. Blueprint imports require https.
- Tool annotations (read-only/destructive) for client-side approval.
- CI runs tests before building, and GitHub Actions are pinned to commit SHAs.

### Fixes
- `create_backup` works on HA 2025.1+ (`agent_ids`).
- `update_helper` and `delete_helper` resolve the stored helper id.
- Automation validation reads HA's per-section result and accepts plural keys; script validation no longer always passes.
- `restart_home_assistant` reports success when the connection drops during restart.
- FastMCP pinned to 4.1.x.

### New tools (not yet verified against a live HA)
- Config flows: handlers, flows in progress, start/continue/abort, options and subentry flows, ignore, delete integration.
- Registry removal: `remove_entity`, `remove_device`.
- Categories: list/create/update/delete/assign.
- Diagnostics: repairs, system log, automation/script traces, trigger/condition/service discovery for a target.
- Backups: agents, backup configuration, delete.
- `counter`, `timer` and `schedule` helpers.

## 0.1.0

- Initial release
- MCP server with 54 tools for Home Assistant configuration management
- Automatic authentication via Supervisor token
- HTTP transport with streamable-HTTP and SSE fallback
- Dry-run and confirm flow for all mutating operations
- Pre-built Docker images for amd64, aarch64, and armv7 via GHCR
- Connection Guide web UI with auto-detected hostname and copy-to-clipboard configs for Claude Code, Claude Desktop, Cursor, Windsurf, VS Code, and more
