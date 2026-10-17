# Home Assistant MCP Server

An MCP (Model Context Protocol) server for setting up and maintaining
Home Assistant with an AI assistant. It adds integrations through config
flows, organises devices and entities, builds automations, scripts,
scenes, helpers, dashboards and blueprints, fixes repairs, debugs
automation traces, and manages backups.

It is aimed at configuration, not day-to-day device control. The generic
`call_service` tool is off by default.

## Features

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
  traces, and discovery of the triggers, conditions and services
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

- [Configuration](docs/configuration.md) -- settings, confirmation,
  client setup
- [Tools reference](docs/tools.md) -- all 110 tools
- [Prompts reference](docs/prompts.md)
- [Architecture](docs/architecture.md)

## License

See [LICENSE](LICENSE).
