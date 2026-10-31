# telegram-bot-framework-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant read the real source, docs and API changes of
[MajMcCloud/TelegramBotFramework](https://github.com/MajMcCloud/TelegramBotFramework) (NuGet: `TelegramBotBase`).
It ships as a Docker image with the framework source baked in, pinned to **8.0.0-preview.2** (`development` branch, commit `6780abf`), together with a curated how-to guide.

> **Warning:** 8.0.0-preview.2 is a **preview**; its API can still change before 8.0.0. The builder in this version has an extra
> *request dispatcher* stage that does not exist in 7.x, so code from the guide will not compile against 7.2.0.
> To serve 7.2.0 instead, build with `--build-arg TGBOTBASE_REF=13fff09c2736e4616f1d3c5dffe40401b92c81b0
> --build-arg TGBOTBASE_NUGET_VERSION=7.2.0` and expect the guide's dispatcher parts to be wrong.

**Contents:** [Quick start](#quick-start) · [Tools](#tools) · [Example prompts](#example-prompts) ·
[Hosting on a VPS](#hosting-on-a-vps) · [Upgrading the framework version](#upgrading-the-framework-version) ·
[CI and publishing](#ci-and-publishing)

## Quick start

Pick one way to connect. Both give the assistant the same tools.

### Local (stdio, no token)
```bash
claude mcp add tgbotbase -- docker run -i --rm severnbli/telegram-bot-framework-mcp:8.0.0-preview.2
```
> **Warning:** keep the `-i` flag. Without it the container's stdin closes and the connection fails immediately.

### Hosted (HTTP)
The public instance needs no token:
```bash
claude mcp add --transport http tgbotbase https://tbf-mcp.severnbli.dev/mcp
```
If the server owner enabled a token, add `--header "Authorization: Bearer <token>"`.

> **Note:** the public instance is a free, read-only, best-effort service: rate limited, no uptime guarantee. For
> reliability, run the [local](#local-stdio-no-token) image or [host your own](#hosting-on-a-vps).

See [Hosting on a VPS](#hosting-on-a-vps) to run your own copy.

### Other MCP clients
Use the URL above (plus the `Authorization` header if a token is enabled), or this stdio config:
```json
{ "mcpServers": { "tgbotbase": { "command": "docker",
  "args": ["run", "-i", "--rm", "severnbli/telegram-bot-framework-mcp:8.0.0-preview.2"] } } }
```

### Check it works
Run `/mcp` in Claude Code, or ask: *"What framework version does tgbotbase serve?"*
The answer should mention `8.0.0-preview.2` and commit `6780abf`.

> **Tip:** pin the image tag (`:8.0.0-preview.2`) in your client config. Prereleases never get the `latest` tag.

## Tools

| Tool | Use it to |
|---|---|
| `framework_version` | See the TelegramBotBase version, commit and dependencies (e.g. `Telegram.Bot`) the answers are based on |
| `list_doc_sections`, `get_doc_section` | Browse and read README sections (Quick start, ButtonGrid, State Machines, ...) |
| `list_symbols`, `get_symbol` | Find C# types by name; see doc comment, base types and public members |
| `find_subclasses` | Find everything deriving from or implementing a type (`FormBase`, `ControlBase`, `IStateMachine`) |
| `search_code` | Case-insensitive substring search of the source (`path_prefix` and `extension` narrow it) |
| `get_file`, `list_files` | Read any file (optionally a line range) or list files under a path |
| `list_examples` | List example and test-bot source files |
| `list_guide_sections`, `get_guide_section`, `search_guide` | Read the curated guide: decision tables (which message loop / dispatcher / serializer), patterns, ship checklist |
| `get_gotchas` | Describe a problem ("button spins forever") and get the known cause and fix |
| `get_changes`, `list_refs` | Public API diff between two tags/commits, for example before an upgrade |

Resources: `tgbotbase://readme` (the framework README) and `tgbotbase://guide` (the full guide).

> **Note:** the symbol index is built with regular expressions, not a C# compiler. It is good for finding types and
> comparing public APIs, but can miss unusual declarations, and `get_changes` may list a few false positives (for example
> a word inside a comment reported as a type). For exact behavior, read the file with `get_file`.

## Example prompts

- "Using tgbotbase, write a form with a paged `ButtonGrid`. Check the real `ButtonGrid` source for the API."
- "Which controls exist and how do they differ? Use `find_subclasses` on `ControlBase`."
- "How do I persist user sessions across restarts? Look at the state machine classes."
- "My button spins forever. Why?" (uses `get_gotchas`)
- "Which message loop and request dispatcher should I use for a bot with broadcasts?" (uses the guide's decision tables)
- "What changed in the public API between v7.1.0 and the current version?"

> **Tip:** tell the assistant to *verify against the source* (`get_symbol`, `get_file`) instead of answering from memory,
> and give it your bot's framework version so it can compare with `framework_version`.

## Hosting on a VPS

Runs the container on `127.0.0.1:8000` and puts host nginx in front of it with TLS and per-IP rate limiting.
The server is **public by default**; a bearer token is optional ([see below](#optional-require-a-bearer-token)).

**Requirements:** Docker, nginx and certbot on the VPS; a DNS A record for `tbf-mcp.severnbli.dev` pointing at it; ports 80 and 443 open.

### 1. Start the container
```bash
cd deploy && cp .env.example .env
docker compose up -d
```
The compose file runs the container read-only with a 512 MB memory and 1 CPU limit.
> **Note:** the image tag `8.0.0-preview.2` exists on Docker Hub only after the first publish from `main` (see
> [CI and publishing](#ci-and-publishing)). Before that, `docker compose up` fails with "not found".

### 2. Configure nginx
```bash
sudo cp nginx.conf /etc/nginx/sites-available/tgbotbase-mcp
sudo ln -s /etc/nginx/sites-available/tgbotbase-mcp /etc/nginx/sites-enabled/
sudo certbot certonly --nginx -d tbf-mcp.severnbli.dev
sudo nginx -t && sudo systemctl reload nginx
```
> **Warning:** on a fresh VPS the certificate does not exist yet, so `nginx -t` fails on the 443 block. Comment that
> block out, run certbot, then restore it. `http2 on;` needs nginx 1.25.1 or newer; on older versions remove it and
> write `listen 443 ssl http2;`.

### 3. Verify
```bash
curl -i https://tbf-mcp.severnbli.dev/mcp   # public mode: any response from the MCP server except 401/404/502
```

### Optional: require a bearer token
A bearer token is a secret string the client sends as `Authorization: Bearer <token>`. To enable it, edit the copy in
`/etc/nginx/sites-available/tgbotbase-mcp`:
1. Generate a token: `openssl rand -hex 32`.
2. In the `map` block change `default 1;` to `default 0;` and uncomment the `"Bearer ..."` line with your token.
3. `sudo nginx -t && sudo systemctl reload nginx`, then connect clients with
   `--header "Authorization: Bearer <token>"`. Requests without it get 401.

> **Warning:** put the token only in the copy under `/etc/nginx`, never in the repo file. Do not commit a real token.
> Anyone who has it can use the server. Use HTTPS only, since the token travels in a header.

### Updating
```bash
cd deploy && docker compose pull && docker compose up -d
```

> **Tip:** the port is bound to `127.0.0.1` on purpose. Do not change it to `0.0.0.0`: that would bypass nginx's rate
> limits (and the token, if enabled).

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

> **Tip:** the repo does not tag NuGet releases (there is no `v7.2.0` or `v8.0.0-preview.2`). Match the NuGet publish date to a commit on
> `master` and pin that commit SHA.

## CI and publishing

- `ci.yml` runs on every pull request: builds the image, runs `tests/smoke.py` inside it, and runs `tests/check_guide.py`,
  which fails if the guide mentions a source file that no longer exists in the pinned source (so a version bump can't silently leave the guide stale).
- `publish.yml` runs only on a push to `main` or a manual dispatch on `main`. It re-runs CI, then pushes
  `severnbli/telegram-bot-framework-mcp:<framework version>` (read from the `Dockerfile`; plus `:latest` for stable, non-prerelease versions) to Docker Hub
  for `linux/amd64` and `linux/arm64`.

> **Warning:** publishing needs the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Without them the
> publish job fails at login.
