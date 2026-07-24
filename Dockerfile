# syntax=docker/dockerfile:1
FROM node:20-bookworm-slim AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY src/ ./src/
COPY assets/ ./assets/
COPY 首批领域数据库知识数据/ ./首批领域数据库知识数据/
COPY frontend/ ./frontend/
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN uv sync --locked --no-dev

EXPOSE 18000
CMD ["uv", "run", "--no-sync", "uvicorn", "src.gateway.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "18000", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
