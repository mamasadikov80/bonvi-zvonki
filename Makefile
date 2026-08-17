.DEFAULT_GOAL := help
SHELL := /bin/bash

# ══════════════════════════════════════════════════════════════
#  ZvonkiDashboard
#  Kompyuteringizga HECH NARSA o'rnatilmaydi — faqat Docker.
# ══════════════════════════════════════════════════════════════

.PHONY: help
help: ## Buyruqlar ro'yxati
	@echo ""
	@echo "  ZvonkiDashboard — buyruqlar"
	@echo "  ─────────────────────────────────────────────"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ─── Asosiy ───────────────────────────────────────────────────

.PHONY: init
init: ## Birinchi ishga tushirish (.env yaratadi va hammasini ko'taradi)
	@if [ ! -f .env ]; then cp .env.example .env; echo "✅ .env yaratildi"; fi
	@$(MAKE) up

.PHONY: up
up: ## Hamma servislarni ko'tarish (hot reload bilan)
	docker compose up -d --build
	@echo ""
	@echo "  ✅ Tayyor!"
	@echo "  ─────────────────────────────────────────────"
	@echo "  Dashboard   →  http://localhost:5180"
	@echo "  API hujjat  →  http://localhost:8010/docs"
	@echo ""
	@echo "  Kirish:  admin@zvonki.uz  /  admin12345"
	@echo ""
	@echo "  Loglar:  make logs"
	@echo ""

.PHONY: down
down: ## Servislarni to'xtatish
	docker compose down

.PHONY: restart
restart: ## Qayta ishga tushirish
	docker compose restart

.PHONY: rebuild
rebuild: ## Image'larni qaytadan qurish
	docker compose build --no-cache
	docker compose up -d

# ─── Loglar ───────────────────────────────────────────────────

.PHONY: logs
logs: ## Barcha loglar
	docker compose logs -f

.PHONY: logs-backend
logs-backend: ## Faqat API loglari
	docker compose logs -f backend

.PHONY: logs-bot
logs-bot: ## Faqat bot loglari
	docker compose logs -f bot

.PHONY: logs-web
logs-web: ## Faqat frontend loglari
	docker compose logs -f web

# ─── Ichkariga kirish ─────────────────────────────────────────

.PHONY: sh-backend
sh-backend: ## API konteyneriga kirish
	docker compose exec backend bash

.PHONY: sh-bot
sh-bot: ## Bot konteyneriga kirish
	docker compose exec bot bash

.PHONY: sh-web
sh-web: ## Frontend konteyneriga kirish
	docker compose exec web sh

.PHONY: psql
psql: ## PostgreSQL konsoli
	docker compose exec postgres psql -U zvonki -d zvonki

# ─── Migratsiyalar ────────────────────────────────────────────

.PHONY: migrate
migrate: ## Migratsiyalarni qo'llash
	docker compose exec backend alembic upgrade head

.PHONY: migration
migration: ## Yangi migratsiya yaratish — make migration m="izoh"
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

.PHONY: seed
seed: ## Yetishmayotgan ma'lumotni qo'shish (idempotent)
	docker compose exec backend python -m src.seed

.PHONY: seed-agents
seed-agents: ## Faqat savdo xodimlari va clientlarni qo'shish
	docker compose exec backend python -m src.seed --agents-only

.PHONY: seed-reset
seed-reset: ## Demo ma'lumotni tozalab qayta yaratish
	docker compose exec backend python -m src.seed --reset

# ─── Sifat ────────────────────────────────────────────────────

.PHONY: lint
lint: ## Kodni tekshirish
	docker compose exec backend ruff check src
	docker compose exec web npm run lint

.PHONY: format
format: ## Kodni formatlash
	docker compose exec backend ruff format src
	docker compose exec web npm run format

.PHONY: test
test: ## Testlar
	docker compose exec backend pytest -q

# ─── Telegram Mini App uchun tunnel ───────────────────────────
#
# Mini App HTTPS talab qiladi, `localhost` esa telefonda ishlamaydi —
# shuning uchun web konteyneri vaqtinchalik ommaviy manzil orqali
# ochiladi.
#
# ⚠️ `--protocol http2` MAJBURIY, bezak emas.
#    `cloudflared` standart holda QUIC (UDP/7844) ishlatadi. Ko'p
#    tarmoqlarda (jumladan bu yerda) UDP chiqishi to'silgan va tunnel
#    hech qachon ko'tarilmaydi — log cheksiz "control stream
#    encountered a failure" bo'lib aylanaveradi, manzil esa berilmaydi.
#    Telefonda bu `ERR_NAME_NOT_RESOLVED` bo'lib ko'rinadi, ya'ni
#    sabab butunlay boshqa joyda ekanini taxmin qilish qiyin.
#    `http2` esa TCP/443 dan yuradi — u ochiq.
#
# ⚠️ Manzil HAR SAFAR YANGI bo'ladi (quick tunnel). Uni BotFather'da
#    yangilash kerak: /myapps → ilovani tanlang → Edit Web App URL.
#
# ⚠️ Tunnel ishlagan vaqtda dashboard INTERNETDA ochiq bo'ladi.
#    Ishingiz tugagach `Ctrl+C` bilan to'xtating.

.PHONY: tunnel
tunnel: ## Mini App uchun vaqtinchalik HTTPS manzil (Ctrl+C — to'xtatish)
	@echo "  Tunnel ko'tarilmoqda… manzil quyida chiqadi (…trycloudflare.com)"
	@echo "  Uni BotFather → /myapps → Edit Web App URL ga qo'ying."
	@echo ""
	docker run --rm --network zvonki-network \
		mirror.gcr.io/cloudflare/cloudflared:latest \
		tunnel --url http://web:5173 --protocol http2 --no-autoupdate

.PHONY: tunnel-check
tunnel-check: ## Tunnel uchun tarmoq tayyormi (QUIC/TCP tekshiruvi)
	@docker compose exec -T backend python -c "\
import socket;\
tcp=lambda h,p:(lambda s:(s.settimeout(4), s.connect_ex((h,p))==0)[1])(socket.socket());\
print('  TCP/443  ->', 'OCHIQ' if tcp('198.41.200.33',443) else 'yopiq');\
print('  UDP/7844 -> QUIC odatda to\'silgan; shuning uchun --protocol http2 ishlatiladi')"

# ─── Tozalash ─────────────────────────────────────────────────
#
# Sinxronizatsiya endi audiosi bor qo'ng'iroqlarnigina oladi, lekin
# eski yurishlarda tushib qolgan audiosiz qatorlar bazada qoladi —
# ro'yxatda ular 0:00 li, bahosiz qatorlar bo'lib ko'rinadi.
#
# ⚠️ Bu buyruq O'CHIRADI. Shuning uchun sharti qat'iy: audiosi YO'Q,
#    transkripti YO'Q va bahosi YO'Q qatorlar. Ya'ni hech qachon
#    baholanmagan va baholanishi ham mumkin bo'lmagan qatorlar —
#    ish natijasi yo'qolmaydi.

.PHONY: clean-no-audio
clean-no-audio: ## Audiosiz, baholanmagan qo'ng'iroqlarni o'chirish (O'CHIRADI!)
	@docker compose exec -T postgres psql -U zvonki -d zvonki -c "\
	DELETE FROM calls c \
	 WHERE (c.audio_key IS NULL OR c.audio_key = '') \
	   AND c.transcript IS NULL \
	   AND NOT EXISTS (SELECT 1 FROM call_scores s WHERE s.call_id = c.id);"

.PHONY: clean
clean: ## To'xtatish va volume'larni o'chirish (BAZA HAM O'CHADI!)
	docker compose down -v

.PHONY: nuke
nuke: ## Hamma narsani o'chirish (image'lar ham)
	docker compose down -v --rmi local
