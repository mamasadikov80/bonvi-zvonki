# ─────────────────────────────────────────────────────────────
#  BonviZvonki — Telegram bot (aiogram)
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# ── Dev (hot reload — watchfiles) ────────────────────────────
FROM base AS dev
# Testlar shu bosqichda ishlaydi (`docker exec zvonki-bot pytest src`).
# Prod image'ga tushmasligi ataylab: bot konteyneri iloji boricha
# yupqa qolsin.
COPY requirements-dev.txt ./
RUN uv pip install --system --no-cache -r requirements-dev.txt
CMD ["watchfiles", "--filter", "python", "python -m src.main", "/app/src"]

# ── Prod ─────────────────────────────────────────────────────
FROM base AS prod
COPY . .
CMD ["python", "-m", "src.main"]
