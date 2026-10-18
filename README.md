# Home Assistant MCP Server

An MCP (Model Context Protocol) server for setting up and maintaining
Home Assistant with an AI assistant. It adds integrations through config
flows, organises devices and entities, builds automations, scripts,
scenes, helpers, dashboards and blueprints, fixes repairs, debugs
automation traces, and manages backups.

It is aimed at configuration, not day-to-day device control. The generic
`call_service` tool is off by default.

## Features

- **Registry queries** -- list and search devices, entities, areas,
  floors, and labels
- **Registry editing** -- create/update/delete areas, floors, and
  labels; rename entities and devices, assign them to areas, attach
  labels, and hide/disable them
- **Device control** -- call any Home Assistant service to actuate
  devices (turn lights on/off, set a thermostat, run a script)
- **Integration management** -- list, reload, and enable/disable
  configured integrations (config entries)
- **Backups** -- list existing backups and create a new full backup
- **System control** -- reload a config domain, restart core (with a
  config check first), inspect core config, system health, and the
  available services
- **Live events** -- listen to Home Assistant events for a bounded
  window (e.g. to watch what a device does)
- **State inspection** -- read entity states, history, logbook
  entries, error logs, and render Jinja2 templates
- **Automation management** -- full CRUD, toggle, duplicate, and
  conflict detection for automations; retrieve recent automation
  traces and build evidence-based diagnoses for failed runs or
  automations that may not have triggered
- **Script management** -- create, read, update, and delete scripts
- **Scene management** -- create, read, update, and delete scenes
- **Helper management** -- create, update, and delete input helpers
  (`input_boolean`, `input_number`, `input_text`, `input_select`,
  `input_datetime`, `input_button`)
- **Dashboard management** -- manage Lovelace dashboards, views,
  and cards
- **Blueprint management** -- list, import, and create automations
  or scripts from blueprints
- **Configuration validation** -- validate automation configs,
  check HA core configuration, and validate YAML syntax
- **Proactive suggestions** -- analyze device coverage, suggest
  automations, detect conflicts, and suggest dashboard layouts
- **Guided workflows** -- six prompt templates for common tasks
  like creating automations, building dashboards, and
  troubleshooting
- **Integration setup** -- start and step through config flows, options
  flows and subentry flows; handle discovered and ignored flows; delete
  integrations
- **Registries** -- list, search and edit devices, entities, areas,
  floors, labels and categories; remove orphaned entities and devices
- **Automations, scripts, scenes** -- full CRUD, validated against Home
  Assistant before saving, plus conflict detection
- **Helpers** -- `input_*`, `counter`, `timer` and `schedule`, and
  config-flow helpers (template, group, utility_meter, ...) via config
  flows
- **Dashboards and blueprints** -- views, cards, blueprint import and
  instantiation
- **Diagnostics** -- repairs, structured system log, automation/script
  traces, one-call automation diagnoses combining enabled state,
  traces, trigger/condition entity history, and matching logbook
  evidence; discovery of the triggers, conditions and services
  available for a target
- **Backups** -- list, create, delete, and configure automatic backups
- **System** -- reload domains, restart core after a config check,
  system health
- **Guided workflows** -- six prompt templates

Tools added in 0.2.0 (config flows, registry removal, categories,
diagnostics, backup configuration, `counter`/`timer`/`schedule` helpers)
are not yet verified against a live Home Assistant.

## Security model

- MCP clients authenticate with an API key (`Authorization: Bearer
  <key>`). The add-on generates one on first start; the pip version
  refuses to serve HTTP without one.
- Confirmation is a server setting (`confirm_mode`), never a tool
  argument, so the model can't skip it.
- Every tool carries MCP annotations (read-only / destructive), so your
  client can auto-approve reads and prompt for changes.
- `read_only` mode exposes only read tools.
- Shell/Python execution, Supervisor services, stop/restart and recorder
  purge are blocked in `call_service` even when device control is on.

## Installation

### Home Assistant add-on (recommended)

1. **Settings > Add-ons > Add-on Store**, overflow menu (**⋮**) >
   **Repositories**, add `https://github.com/bimo443trimdon/ha-mcp-trace`.
2. Install **Home Assistant MCP Server** and click **Start**.
3. Open the **MCP Server** panel in the sidebar. It shows your API key
   and ready-to-copy snippets for Claude Code, Claude Desktop, Cursor,
   VS Code and other clients.

For example, Claude Code:

```bash
claude mcp add --transport http --scope user home-assistant http://homeassistant.local:8099/mcp \
  --header "Authorization: Bearer <API_KEY>"
```

Claude Desktop (requires Node.js; Settings > Developer > Edit Config):

```json
{
  "mcpServers": {
    "home-assistant": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://homeassistant.local:8099/mcp",
               "--allow-http", "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer <API_KEY>" }
    }
  }
}
```

Claude Desktop's custom connectors can't reach a server on your LAN,
so use the config file above. See
[docs/configuration.md](docs/configuration.md#client-setup) for all
clients.

### pip install

Requires Python 3.11+ and a
[long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile).

```bash
pip install .
export HA_MCP_HA_URL="http://homeassistant.local:8123"
export HA_MCP_HA_TOKEN="<long-lived-access-token>"
ha-mcp            # stdio, for clients that launch the server themselves
```

For HTTP, an API key is required:

```bash
export HA_MCP_TRANSPORT=http
export HA_MCP_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
ha-mcp            # serves http://127.0.0.1:8099/mcp
```

### Automation debugging

Use `get_automation_diagnosis` with an automation entity ID such as
`automation.garage_door` (or its config ID) to gather a bounded set of
recent traces, the current enabled state, recent history for entities
referenced by its triggers and conditions, and matching logbook entries.
The result separates observed facts from hypotheses and includes evidence
sources and timestamps. An empty trace result is not proof that an
automation never ran: Home Assistant retains a limited number of traces,
and entity history cannot verify every trigger type.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `HA_MCP_HA_URL` | `http://homeassistant.local:8123` | Home Assistant base URL |
| `HA_MCP_HA_TOKEN` | *(required)* | Long-lived access token |
| `HA_MCP_TRANSPORT` | `stdio` | `stdio`, `http` or `sse` |
| `HA_MCP_HOST` | `127.0.0.1` | Bind address for `http`/`sse` |
| `HA_MCP_PORT` | `8099` | Port for `http`/`sse` |
| `HA_MCP_API_KEY` | *(empty)* | Required for `http`/`sse` |
| `HA_MCP_ALLOW_UNAUTHENTICATED` | `false` | Allow `http`/`sse` without a key (loopback only) |
| `HA_MCP_CONFIRM_MODE` | `client` | `client` (client's tool approval) or `elicit` (server-side prompt) |
| `HA_MCP_READ_ONLY` | `false` | Only expose read-only tools |
| `HA_MCP_ENABLE_DEVICE_CONTROL` | `false` | Expose `call_service` |
| `HA_MCP_LOG_LEVEL` | `INFO` | Logging level |

## Documentation

- [Configuration](docs/configuration.md) -- environment variables,
  transport options, and client setup
- [Tools reference](docs/tools.md) -- all MCP tools with
  parameters and descriptions
- [Prompts reference](docs/prompts.md) -- guided workflow
  templates
- [Architecture](docs/architecture.md) -- project structure,
  module design, and extension guide

## License

See [LICENSE](LICENSE).
