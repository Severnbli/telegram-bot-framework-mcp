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
Then set up nginx using `deploy/nginx.conf`: replace `mcp.example.com` and `CHANGE_ME_TOKEN`
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
