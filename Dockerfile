FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned framework source: NuGet 8.0.0-preview.2 (published 2026-10-06) == `development` commit 6780abf.
ARG TGBOTBASE_REF=6780abf8966438a1ff01bc134e640b9a2c538bf4
ARG TGBOTBASE_NUGET_VERSION=8.0.0-preview.2
RUN git clone https://github.com/MajMcCloud/TelegramBotFramework /data/repo \
    && git -C /data/repo checkout --detach ${TGBOTBASE_REF}

WORKDIR /app
COPY knowledge /data/knowledge
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user; the cloned source stays owned by root (read-only for the app)
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin mcp \
    && git config --system --add safe.directory /data/repo
USER mcp

ENV PYTHONUNBUFFERED=1 TGBOTBASE_DIR=/data/repo TGBOTBASE_GUIDE=/data/knowledge/SKILL.md TGBOTBASE_NUGET_VERSION=${TGBOTBASE_NUGET_VERSION}
ENTRYPOINT ["telegram-bot-framework-mcp"]
