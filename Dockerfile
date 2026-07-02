# RootSeeker V2 Dockerfile
# Multi-stage build; production image installs git for repo sync/clone

# ============================================================
# Stage 1: Build admin-web frontend
# ============================================================
FROM node:22-slim AS frontend-builder

WORKDIR /build/admin-web

COPY apps/admin-web/package.json apps/admin-web/package-lock.json ./
RUN npm ci --prefer-offline

COPY apps/admin-web/ ./
RUN npm run build

# ============================================================
# Stage 2: Python builder
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY pyproject.toml README.md ./
COPY rootseeker ./rootseeker
COPY apps ./apps
COPY mcp_servers ./mcp_servers
COPY plugins ./plugins
COPY skills ./skills

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ============================================================
# Stage 3: Production image
# ============================================================
FROM python:3.11-slim AS production

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY docker/bin/zoekt-index /usr/local/bin/zoekt-index
RUN chmod +x /usr/local/bin/zoekt-index

RUN groupadd -r rootseeker && useradd -r -g rootseeker -d /app rootseeker

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=rootseeker:rootseeker . .
COPY --from=frontend-builder --chown=rootseeker:rootseeker /build/admin-web/dist /app/apps/admin-web/dist

RUN mkdir -p /app/data /data/repos /data/zoekt/index && \
    chown -R rootseeker:rootseeker /app/data /data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ROOTSEEKER_ZOEKT_INDEX_BINARY=/usr/local/bin/zoekt-index

USER rootseeker

EXPOSE 8000 8010

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
