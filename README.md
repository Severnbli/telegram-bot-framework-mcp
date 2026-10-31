# telegram-bot-framework-mcp

Dockerized MCP server over the source of [MajMcCloud/TelegramBotFramework](https://github.com/MajMcCloud/TelegramBotFramework)
(NuGet `TelegramBotBase`), pinned to **7.2.0** (master commit `13fff09c`).

## Build / register
```
docker build -t tgbotbase-mcp:7.2.0 .
claude mcp add tgbotbase -- docker run -i --rm tgbotbase-mcp:7.2.0
```
Version bump: `docker build --build-arg TGBOTBASE_REF=<tag|sha> --build-arg TGBOTBASE_NUGET_VERSION=<x.y.z> -t tgbotbase-mcp:<x.y.z> .`

## Tools
`framework_version`, `get_changes(from_ref, to_ref)`, `list_refs`, `list_symbols`, `get_symbol`, `find_subclasses`,
`list_files`, `get_file`, `search_code`, `list_doc_sections`, `get_doc_section`, `list_examples`. Resource: `tgbotbase://readme`.

## Using the server

### 1. Connect
Hosted (`https://mcp.example.com/mcp`, needs the bearer token):
```
claude mcp add --transport http tgbotbase https://mcp.example.com/mcp --header "Authorization: Bearer <token>"
```
Local (no hosting, no token):
```
claude mcp add tgbotbase -- docker run -i --rm severnbli/telegram-bot-framework-mcp:7.2.0
```
Other MCP clients: use the same URL and `Authorization` header (HTTP), or the `docker run -i --rm ...` command (stdio):
```json
{ "mcpServers": { "tgbotbase": { "command": "docker",
  "args": ["run", "-i", "--rm", "severnbli/telegram-bot-framework-mcp:7.2.0"] } } }
```
Check it works: run `/mcp` in Claude Code, or ask "what framework version does tgbotbase serve?".

### 2. Tools
| Tool | Use it to |
|---|---|
| `framework_version` | See which TelegramBotBase version, commit and dependencies (e.g. `Telegram.Bot`) the answers are based on |
| `list_doc_sections` / `get_doc_section` | Browse and read README sections (Quick start, ButtonGrid, State Machines, ...) |
| `list_symbols` / `get_symbol` | Find C# types by name; see doc comment, base types, public members |
| `find_subclasses` | Find everything deriving from/implementing a type (`FormBase`, `ControlBase`, `IStateMachine`) |
| `search_code` | Search source by substring or regex (`path_prefix`, `extension` narrow it) |
| `get_file` / `list_files` | Read any file (with line ranges) or list files under a path |
| `list_examples` | Example and test-bot source files |
| `get_changes` / `list_refs` | Public API diff between two tags/commits, e.g. before upgrading |

Resource: `tgbotbase://readme` (full README).

### 3. Example prompts
- "Using tgbotbase, write a form with a paged ButtonGrid; check the real `ButtonGrid` source for the API."
- "Which controls exist and how do they differ? Use `find_subclasses ControlBase`."
- "How do I persist user sessions across restarts? Look at the state machine classes."
- "What changed in the public API between v7.1.0 and the current version?"

Tips: tell the assistant to *verify against the source* (`get_symbol` / `get_file`) rather than answer from memory, and
mention your bot's framework version so it can compare with `framework_version`.

### 4. Upgrading the framework version
```
docker build --build-arg TGBOTBASE_REF=<tag|sha> --build-arg TGBOTBASE_NUGET_VERSION=<x.y.z> -t tgbotbase-mcp:<x.y.z> .
```
Update the defaults in the `Dockerfile` and merge to `main` to publish; on the VPS run `docker compose pull && docker compose up -d`.
Before bumping your bot, ask for `get_changes` between the old and new ref to see what to adapt.

## CI / publishing
- `ci.yml` runs on every PR: builds the image and runs `tests/smoke.py` inside it.
- `publish.yml` runs only on push to `main` or manual dispatch on `main`: re-runs CI, then pushes
  `severnbli/telegram-bot-framework-mcp:latest` and `:<framework version>` (read from the Dockerfile) to Docker Hub.
  Requires repo secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.

```
claude mcp add tgbotbase -- docker run -i --rm severnbli/telegram-bot-framework-mcp:7.2.0
```

## Hosting on a VPS (Docker + host nginx)
Needs Docker and nginx on the VPS, and a DNS A record for your domain pointing at it.
```
cd deploy && cp .env.example .env
docker compose up -d                 # listens on 127.0.0.1:8000 only
```
Then set up nginx using `deploy/nginx.conf`: replace `CHANGE_ME_TOKEN`
(`openssl rand -hex 32`), install it as a site, get a certificate and reload:
```
sudo cp nginx.conf /etc/nginx/sites-available/tgbotbase-mcp
sudo ln -s /etc/nginx/sites-available/tgbotbase-mcp /etc/nginx/sites-enabled/
sudo certbot certonly --nginx -d mcp.example.com   # if the cert doesn't exist yet, comment out the 443 block first
sudo nginx -t && sudo systemctl reload nginx
```
Requests without `Authorization: Bearer <token>` get 401. Connect a client:
```
claude mcp add --transport http tgbotbase https://mcp.example.com/mcp --header "Authorization: Bearer <token>"
```
Update to a new image: `docker compose pull && docker compose up -d`.
