# ─────────────────────────────────────────────────────────────
#  BonviZvonki — Backend API (FastAPI)
#  Barcha bog'liqliklar konteyner ichida. Host toza qoladi.
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv — pip'dan ~10x tez
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# ── Dev (hot reload — kod bind-mount orqali keladi) ──────────
FROM base AS dev
COPY requirements-dev.txt ./
RUN uv pip install --system --no-cache -r requirements-dev.txt
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"]

# ── Prod ─────────────────────────────────────────────────────
FROM base AS prod
COPY . .
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
