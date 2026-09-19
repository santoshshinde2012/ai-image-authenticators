# syntax=docker/dockerfile:1.7

# --- Frontend build ---
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# --- Python deps + install project ---
FROM python:3.12-slim-bookworm AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev

# --- Runtime ---
FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    AIAUTH_HOST=0.0.0.0 \
    AIAUTH_PORT=8000 \
    AIAUTH_ENVIRONMENT=prod \
    AIAUTH_LOG_LEVEL=INFO \
    AIAUTH_FRONTEND_DIST=/app/apps/web/dist

COPY --from=python-deps /app/.venv /app/.venv
COPY --from=python-deps /app/apps/api /app/apps/api
COPY --from=python-deps /app/pyproject.toml /app/uv.lock /app/README.md /app/
COPY --from=frontend-build /app/apps/web/dist /app/apps/web/dist

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"
CMD ["uvicorn", "ai_image_authenticator.main:app", "--host", "0.0.0.0", "--port", "8000"]
