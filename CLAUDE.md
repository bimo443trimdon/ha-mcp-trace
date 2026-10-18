# CLAUDE.md

## Project
MCP server for setting up and maintaining Home Assistant — config flows, config CRUD, registry read/write/remove, diagnostics, backups, and system control. Device control (`call_service`) is opt-in. Python package at `src/ha_mcp/`, distributed as an HA add-on (`ha_mcp_addon/`) and via pip.

## Key Architecture
- **FastMCP 4.1.x** (pinned `>=4.1,<5`) — decorators: `@mcp.tool()`, `@mcp.prompt()`, `@mcp.resource()`. HTTP endpoint is `/mcp` (no trailing slash; `/mcp/` 307-redirects)
- **Tools** registered via `register_*_tools(mcp_server)` pattern in each module. `register_all_tools` passes a registrar, not the server: it sets MCP annotations from the tool-name prefix (`list_/get_/find_/...` read-only; `delete_/remove_/restart_` + `call_service` destructive), drops write tools when `read_only`, and drops `call_service` unless `enable_device_control`. Name new tools accordingly
- **Clients** accessed via `from ha_mcp.util.context import get_clients` (NOT from server.py — causes circular import); it reads `ctx.lifespan_context`
- **Mutating tools** call `confirm_change(ctx, action, entity_type, identifier, config, validation_result=None)` from `util/dry_run.py`. Policy comes from `settings.confirm_mode` (`client` = trust client tool approval, `elicit` = `ctx.elicit`, raises if unsupported). Never add a model-controlled `skip_confirm` param. Validation failures raise `ToolError`
- **Auth**: `http`/`sse` require `HA_MCP_API_KEY` (bearer, `auth.ApiKeyVerifier`); `__main__` exits without it unless `HA_MCP_ALLOW_UNAUTHENTICATED`. Default host is `127.0.0.1`
- **REST paths**: wrap every interpolated value in `rest._seg()`. **WS**: `send_command` puts `id`/`type` after `**kwargs` so input can't override them
- Automation/script validation goes through `util/validation.py` (HA returns per-section `{valid, error}`, not a top-level `valid`)
- All tool functions accept `ctx: Context` and return JSON strings
- Config via `pydantic-settings` with `HA_MCP_` env prefix
- Build system: hatchling (`pyproject.toml`)

## HA Add-on (`ha_mcp_addon/`)
- **Pre-built Docker images** pushed to GHCR (`ghcr.io/bimo443trimdon/ha-mcp-trace-{arch}`)
- Architectures: amd64, aarch64 (no armv7 — Rust compilation fails on armv7 musl)
- Base images: `ghcr.io/home-assistant/{arch}-base-python:3.12-alpine3.19`
- **`init: false`** in config.yaml is required — HA Supervisor injects tini as PID 1 by default, which conflicts with the base image's s6-overlay init. Without this, you get `s6-overlay-suexec: fatal: can only run as pid 1`
- Dockerfile uses standard `CMD ["/run.sh"]` pattern (s6-overlay runs it via its init)
- **Ingress** on port 8100 is served by `guide_server.py` (aiohttp), which only answers the ingress proxy `172.30.32.2` and exposes `connection.json` (API key + settings) to `www/index.html`; MCP server on port 8099 (direct, not through ingress)
- HA auth is automatic via Supervisor token (`SUPERVISOR_TOKEN` env var). Client auth: `run.sh` uses the `api_key` option, else generates/persists `/data/api_key`
- Options: `api_key`, `confirm_mode`, `read_only`, `enable_device_control`, `log_level` → exported as `HA_MCP_*` by `run.sh`
- `build-prep.sh` copies `src/`, `pyproject.toml`, `README.md` into `ha_mcp_addon/package/` before Docker build (source is outside addon build context)
- `ha_mcp_addon/package/` is gitignored

## Version Bumping
**Always bump `ha_mcp_addon/config.yaml` version when making addon changes.** HA caches Docker images by version tag — same tag = no re-pull, even after reinstall. The CI tags images with the version from config.yaml.

## CI
- `.github/workflows/build-addon.yml` — `test` job (pytest) gates the build; builds + pushes to GHCR on push to main. Actions are pinned to commit SHAs
- PRs get build-only (no push) as smoke test
- GHCR packages must be set to **public** for HA to pull without auth

## Known Issues
- FastMCP static resources (no URI template params) don't support `ctx` parameter
- Circular import: `server.py` imports tools → tools must NOT import from `server.py` → use `util/context.py`

## Counts
- 79 tools, 6 prompts, 1 resource template, 40 source files
- Tools span config CRUD (automation/script/scene/helper/dashboard/blueprint),
  registry read + write (area/floor/label/entity/device), state/history,
  device control (`call_service`), integrations, backups, system reload/restart,
  and bounded live-event listening (`listen_events`).
- 109 tools by default (110 with `enable_device_control`, 53 in `read_only`), 6 prompts, 1 resource template, 41 Python source files
- Tools span config flows (integrations, options, subentries), config CRUD
  (automation/script/scene/helper incl. counter/timer/schedule/dashboard/blueprint),
  registry read + write + remove (area/floor/label/category/entity/device),
  diagnostics (repairs, system log, traces, target trigger/condition discovery),
  state/history, integrations, backups + backup config, system reload/restart,
  bounded live-event listening, and opt-in device control (`call_service`).
- 0.2.0 tools (config_flow, registry_remove, categories, diagnostics, backup config,
  counter/timer/schedule) are not yet verified against a live HA.
