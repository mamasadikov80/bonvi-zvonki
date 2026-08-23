#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  BonviZvonki — ishga tushirish (macOS / Linux)
#
#  Bu skript README boshidagi buyruqning aynan o'zini bajaradi:
#      cp .env.example .env && docker compose up -d --build
#
#  Skriptsiz ham bo'ladi — o'sha buyruqni qo'lda yozsangiz kifoya.
#  Yangilashda avval kodni torting:  git pull && ./start.sh
# ══════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo "  ℹ️  .env allaqachon bor — tegilmadi"
else
  cp .env.example .env
  echo "  ✅ .env yaratildi (.env.example dan)"
fi

docker compose up -d --build

cat <<'MSG'

  ✅ Konteynerlar ko'tarildi
  ─────────────────────────────────────────────
  Birinchi safar backend bazani tayyorlaydi — bu bir necha daqiqa
  oladi. Holat:  docker compose ps   (backend "healthy" bo'lsin)

  Dashboard   →  http://localhost:5180
  API hujjat  →  http://localhost:8010/docs

  Kirish:  admin@zvonki.uz  /  admin12345
  Loglar:  docker compose logs -f backend

MSG
