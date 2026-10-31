# telegram-bot-framework-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant read the real source, docs and API changes of
[MajMcCloud/TelegramBotFramework](https://github.com/MajMcCloud/TelegramBotFramework) (NuGet: `TelegramBotBase`).
It ships as a Docker image with the framework source baked in, pinned to **7.2.0** (master commit `13fff09c`).

**Contents:** [Quick start](#quick-start) · [Tools](#tools) · [Example prompts](#example-prompts) ·
[Hosting on a VPS](#hosting-on-a-vps) · [Upgrading the framework version](#upgrading-the-framework-version) ·
[CI and publishing](#ci-and-publishing)

## Quick start

Pick one way to connect. Both give the assistant the same tools.

### Local (stdio, no token)
```bash
claude mcp add tgbotbase -- docker run -i --rm severnbli/telegram-bot-framework-mcp:7.2.0
```
> **Warning:** keep the `-i` flag. Without it the container's stdin closes and the connection fails immediately.

### Hosted (HTTP, bearer token)
```bash
claude mcp add --transport http tgbotbase https://mcp.example.com/mcp \
  --header "Authorization: Bearer <token>"
```
See [Hosting on a VPS](#hosting-on-a-vps) to run your own copy.

### Other MCP clients
Use the URL and `Authorization` header above, or this stdio config:
```json
{ "mcpServers": { "tgbotbase": { "command": "docker",
  "args": ["run", "-i", "--rm", "severnbli/telegram-bot-framework-mcp:7.2.0"] } } }
```

### Check it works
Run `/mcp` in Claude Code, or ask: *"What framework version does tgbotbase serve?"*
The answer should mention `7.2.0` and commit `13fff09c`.

> **Tip:** pin the image tag (`:7.2.0`) in your client config instead of `:latest`, so answers don't change under you when a new image is published.

## Tools

| Tool | Use it to |
|---|---|
| `framework_version` | See the TelegramBotBase version, commit and dependencies (e.g. `Telegram.Bot`) the answers are based on |
| `list_doc_sections`, `get_doc_section` | Browse and read README sections (Quick start, ButtonGrid, State Machines, ...) |
| `list_symbols`, `get_symbol` | Find C# types by name; see doc comment, base types and public members |
| `find_subclasses` | Find everything deriving from or implementing a type (`FormBase`, `ControlBase`, `IStateMachine`) |
| `search_code` | Search the source by substring or regex (`path_prefix` and `extension` narrow it) |
| `get_file`, `list_files` | Read any file (optionally a line range) or list files under a path |
| `list_examples` | List example and test-bot source files |
| `get_changes`, `list_refs` | Public API diff between two tags/commits, for example before an upgrade |

Resource: `tgbotbase://readme` (the full README).

> **Note:** the symbol index is built with regular expressions, not a C# compiler. It is good for finding types and
> comparing public APIs, but can miss unusual declarations. For exact behavior, read the file with `get_file`.

## Example prompts

- "Using tgbotbase, write a form with a paged `ButtonGrid`. Check the real `ButtonGrid` source for the API."
- "Which controls exist and how do they differ? Use `find_subclasses` on `ControlBase`."
- "How do I persist user sessions across restarts? Look at the state machine classes."
- "What changed in the public API between v7.1.0 and the current version?"

> **Tip:** tell the assistant to *verify against the source* (`get_symbol`, `get_file`) instead of answering from memory,
> and give it your bot's framework version so it can compare with `framework_version`.

## Hosting on a VPS

Runs the container on `127.0.0.1:8000` and puts host nginx in front of it with TLS and a bearer-token check.

**Requirements:** Docker, nginx and certbot on the VPS; a DNS A record for `mcp.example.com` pointing at it; ports 80 and 443 open.

### 1. Start the container
```bash
cd deploy && cp .env.example .env
docker compose up -d
```
> **Note:** the image tags `latest` and `7.2.0` exist on Docker Hub only after the first publish from `main` (see
> [CI and publishing](#ci-and-publishing)). Before that, `docker compose up` fails with "not found".

### 2. Configure nginx
Generate a token (`openssl rand -hex 32`) and put it in a copy of `deploy/nginx.conf` in place of `CHANGE_ME_TOKEN`:
```bash
sudo cp nginx.conf /etc/nginx/sites-available/tgbotbase-mcp
sudo ln -s /etc/nginx/sites-available/tgbotbase-mcp /etc/nginx/sites-enabled/
sudo certbot certonly --nginx -d mcp.example.com
sudo nginx -t && sudo systemctl reload nginx
```
> **Warning:** edit the token in the copy under `/etc/nginx`, never in the repo file. Do not commit a real token.
> Anyone who has it can use the server.

> **Warning:** on a fresh VPS the certificate does not exist yet, so `nginx -t` fails on the 443 block. Comment that
> block out, run certbot, then restore it. `http2 on;` needs nginx 1.25.1 or newer; on older versions remove it and
> write `listen 443 ssl http2;`.

### 3. Verify
```bash
curl -i https://mcp.example.com/mcp                                   # expect 401
curl -i -H "Authorization: Bearer <token>" https://mcp.example.com/mcp # expect a response from the MCP server (not 401)
```

### Updating
```bash
cd deploy && docker compose pull && docker compose up -d
```

> **Tip:** the port is bound to `127.0.0.1` on purpose. Do not change it to `0.0.0.0` or the token check can be bypassed.

## Upgrading the framework version

1. Build with the new ref (a tag or commit SHA) and version:
   ```bash
   docker build \
     --build-arg TGBOTBASE_REF=<tag|sha> \
     --build-arg TGBOTBASE_NUGET_VERSION=<x.y.z> \
     -t tgbotbase-mcp:<x.y.z> .
   ```
2. Update the defaults in the `Dockerfile` and the pinned version in this README, then merge to `main` to publish.
3. Before changing your bot, ask the assistant for `get_changes` between the old and new ref to see what to adapt.

> **Tip:** the repo does not tag NuGet releases (there is no `v7.2.0`). Match the NuGet publish date to a commit on
> `master` and pin that commit SHA.

## CI and publishing

- `ci.yml` runs on every pull request: builds the image and runs `tests/smoke.py` inside it.
- `publish.yml` runs only on a push to `main` or a manual dispatch on `main`. It re-runs CI, then pushes
  `severnbli/telegram-bot-framework-mcp:latest` and `:<framework version>` (read from the `Dockerfile`) to Docker Hub
  for `linux/amd64` and `linux/arm64`.

> **Warning:** publishing needs the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Without them the
> publish job fails at login.
