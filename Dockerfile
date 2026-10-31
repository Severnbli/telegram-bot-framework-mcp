FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned framework source. NuGet 7.2.0 (published 2026-08-04) == master commit 13fff09c.
ARG TGBOTBASE_REF=13fff09c2736e4616f1d3c5dffe40401b92c81b0
ARG TGBOTBASE_NUGET_VERSION=7.2.0
RUN git clone https://github.com/MajMcCloud/TelegramBotFramework /data/repo \
    && git -C /data/repo checkout --detach ${TGBOTBASE_REF}

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user; the cloned source stays owned by root (read-only for the app)
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin mcp \
    && git config --system --add safe.directory /data/repo
USER mcp

ENV PYTHONUNBUFFERED=1 TGBOTBASE_DIR=/data/repo TGBOTBASE_NUGET_VERSION=${TGBOTBASE_NUGET_VERSION}
ENTRYPOINT ["telegram-bot-framework-mcp"]
