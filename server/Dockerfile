# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for asyncpg, cryptography, boto3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency install from pyproject + uv.lock
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
# Default: production deps only. Eval deps installed when EVAL_EXTRAS=1 is set
# at build time via --build-arg, so the prod image stays lean.
ARG EVAL_EXTRAS=0
RUN if [ "$EVAL_EXTRAS" = "1" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra eval; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi

# Copy application source
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY README.md ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
