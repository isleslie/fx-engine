# ---- Stage 1: build the SPA ------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* frontend/pnpm-lock.yaml* ./
# pnpm via corepack when a pnpm lockfile exists; falls back to npm ci
RUN if [ -f pnpm-lock.yaml ]; then corepack enable && pnpm install --frozen-lockfile; \
    else npm ci --no-audit --no-fund; fi
COPY frontend/ ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm build; else npm run build; fi

# ---- Stage 2: the app image (web + worker share it) ------------------------
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project; \
    else uv sync --no-dev --no-install-project; fi

COPY src/ src/
COPY config/ config/
COPY README.md ./
RUN uv sync --no-dev

# Built SPA lands where the API's STATIC_DIR expects it (repo_root/static)
COPY --from=frontend /build/dist/ static/

ENV PATH="/app/.venv/bin:$PATH" \
    FX_DB_PATH=/data/fx.db \
    FX_SOURCE_REGISTRY=/app/config/source_registry.yaml \
    PYTHONUNBUFFERED=1

# Default command is the web tier; compose overrides this for the worker
EXPOSE 8000
CMD ["uvicorn", "fxengine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
