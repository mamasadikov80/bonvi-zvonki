# Bonvi · Savdo analitikasi

**Bonvi** kompaniyasi savdo bo'limi uchun qo'ng'iroq analitikasi va savdo
nazorati platformasi. MoyZvonki'dan qo'ng'iroq yozuvlari avtomatik olinadi,
transkripsiya qilinadi va rubrika bo'yicha AI tomonidan baholanadi. Natijalar
mijozlardan Telegram bot orqali yig'ilgan reyting bilan birga bitta dashboardda
ko'rsatiladi — rahbar har bir xodim, hudud va davr kesimida ishni ko'rib turadi.

📄 To'liq tahlil va reja: [`docs/PLAN.md`](docs/PLAN.md)

---

## ⚡ Tez ishga tushirish

Loyiha papkasi ichida turib (`cd BonviZvonki`):

**Birinchi marta — qurish va ishga tushirish:**

# `make init`

**Keyingi yangilanishlarda:**

# `make update`

---

Bu ikki buyruq nima qiladi:

| | `make init` | `make update` |
|---|---|---|
| `.env` | yo'q bo'lsa `.env.example` dan yaratadi | tegmaydi |
| kod | joyidagi kod | `git pull` (remote bo'lsa) |
| image'lar | quradi | qayta quradi |
| konteynerlar | ko'taradi | yangilaydi |
| baza jadvallari | yaratadi + demo ma'lumot | yangi ustunlarni qo'shadi |
| mavjud ma'lumot | — | **saqlanadi** |

Ikkalasi ham oxirida backend sog'lom bo'lishini kutadi va manzil bilan
kirish ma'lumotlarini chiqaradi. Birinchi ishga tushirish 5–10 daqiqa
oladi (image'lar yuklab olinadi), keyingilari 1–2 daqiqa.

---

## Talablar

| Nima | Qancha |
|---|---|
| **Docker Desktop** | 4.30+ (Compose v2 bilan) · Linuxda Docker Engine 24+ va `docker compose` plagini |
| **Disk** | kamida **8 GB** bo'sh joy (image'lar ~5 GB + baza) |
| **RAM** | Docker'ga kamida 4 GB ajratilgan bo'lsin |
| **Bo'sh portlar** | `5180`, `8010`, `5433`, `6380` |
| **Boshqa** | hech narsa. Python, Node, PostgreSQL **o'rnatilmaydi** — hammasi konteyner ichida |

Docker ishlayotganini tekshirish: `docker info` xatosiz chiqsa tayyor.

> Windows'da `make` bo'lmasa: Git Bash + `choco install make`, yoki
> to'g'ridan-to'g'ri: `cp .env.example .env && docker compose up -d --build`

---

## `.env` sozlamalari

`make init` uni o'zi yaratadi va **shu holicha tizim to'liq ko'tariladi** —
hech narsa to'ldirmasangiz ham dashboard, demo ma'lumot va analitika ishlaydi.

⚠️ Haqiqiy kalitlar `.env` dan tashqariga chiqmaydi — bu faylni git'ga
qo'shmang va hech qayerga nusxalamang.

**Ishlashi uchun shart (standart qiymati bor, tegmasa ham bo'ladi):**

| O'zgaruvchi | Nima uchun |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | baza hisobi |
| `SECRET_KEY` | JWT imzosi — **ishlab chiqarishda albatta almashtiring**: `openssl rand -hex 32` |
| `API_PORT` `WEB_PORT` `POSTGRES_PORT` `REDIS_PORT` | host tomondagi portlar (band bo'lsa shu yerda o'zgartiring) |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | birinchi admin hisobi |
| `SEED_DEMO_DATA` | demo ma'lumot yuklansinmi (`true` / `false`) |

**Ixtiyoriy — bo'sh qolsa tizim ko'tariladi, faqat shu funksiya ishlamaydi:**

| O'zgaruvchi | Bo'sh qolsa nima ishlamaydi |
|---|---|
| `MOIZVONKI_DOMAIN` `MOIZVONKI_USER` `MOIZVONKI_API_KEY` | qo'ng'iroqlar sinxronizatsiyasi — yangi qo'ng'iroq kelmaydi |
| `TELEGRAM_BOT_TOKEN` | mijoz so'rovnomalari va Telegram xabarnomalari |
| `INTERNAL_API_TOKEN` | bot ↔ backend aloqasi (ichki endpointlar 401 qaytaradi) |
| `PUBLIC_WEB_URL` | Telegram xabaridagi «Panelda ochish» havolasi qo'shilmaydi |
| `ESKIZ_EMAIL` / `ESKIZ_PASSWORD` | SMS zaxira kanali |
| `STORAGE_*` | tashqi audio arxivi |

**AI kalitlari `.env` da YO'Q — bu ataylab.** Provayder, model va API
kalitlar faqat dashboard → **Sozlamalar → Sun'iy intellekt** bo'limida
turadi. Ular to'ldirilmaguncha transkripsiya va baholash ishlamaydi,
qolgani ishlayveradi.

> **`.env` ni o'zgartirsangiz `make restart` YETMAYDI.** Compose `env_file`
> qiymatlarini konteyner *yaratilishida* biriktiradi. Kerak:
> `docker compose up -d --force-recreate backend bot worker`

---

## Manzillar va kirish

| Manzil | Nima |
|---|---|
| http://localhost:5180 | Dashboard |
| http://localhost:8010/docs | API hujjatlari (Swagger) |
| http://localhost:5180/monitor | Monitor rejimi (savdo xonasi ekrani) |

**Demo hisoblar** (`SEED_DEMO_DATA=true` bo'lganda yaratiladi):

| Rol | Email | Parol |
|---|---|---|
| Administrator | `admin@zvonki.uz` | `admin12345` |
| Menejer | `manager@zvonki.uz` | `manager12345` |
| Savdo xodimi | `sardor@zvonki.uz` | `sardor12345` |
| Kuzatuvchi | `viewer@zvonki.uz` | `viewer12345` |

⚠️ Bular **demo parollari**. Haqiqiy foydalanuvchilarga berishdan oldin
`.env` dagi `FIRST_ADMIN_PASSWORD` ni o'zgartiring va boshqa hisoblarni
dashboard orqali qayta parollang.

---

## Kundalik buyruqlar

```bash
make help          # barcha buyruqlar
make up            # ko'tarish (build bilan)
make down          # to'xtatish (ma'lumot saqlanadi)
make restart       # qayta ishga tushirish
make logs          # loglar (hammasi)
make logs-backend  # faqat backend
make sh-backend    # backend konteyneriga kirish
make psql          # PostgreSQL konsoli
make seed          # yetishmayotgan demo ma'lumotni qo'shish
make migrate       # migratsiyalarni qo'llash
make test          # backend testlari
make lint          # kod tekshiruvi
```

**Hot reload yoqilgan** — `services/` ichidagi faylni tahrirlasangiz,
tegishli servis avtomatik qayta yuklanadi. Qayta qurish shart emas.

### 🛑 Ma'lumotni O'CHIRADIGAN buyruqlar

`make init`, `make update`, `make up`, `make down` bazaga tegmaydi.
Quyidagilar esa **butun bazani o'chiradi** — ular `docker compose down -v`
ishlatadi va volume'lar bilan birga barcha qo'ng'iroqlar, baholar va
sozlamalar yo'qoladi:

| Buyruq | Nima o'chadi |
|---|---|
| `make clean` | konteynerlar + **volume'lar (BAZA)** |
| `make nuke` | yuqoridagilar + image'lar |
| `make seed-reset` | demo ma'lumot tozalanib qayta yaratiladi |
| `make clean-no-audio` | audiosiz, baholanmagan qo'ng'iroq qatorlari |

Boshqa kompyuterda ishga tushirayotganda bu buyruqlar **kerak emas**.

---

## Muammolar

**Port band** (`bind: address already in use`)
`.env` dagi `WEB_PORT` / `API_PORT` / `POSTGRES_PORT` / `REDIS_PORT` ni
o'zgartiring, so'ng `docker compose up -d --force-recreate`.
Kim band qilganini ko'rish: `lsof -i :5180` (macOS/Linux),
`netstat -ano | findstr :5180` (Windows).

**`.env` ni o'zgartirdim, lekin ta'sir qilmadi**
`make restart` yetmaydi — konteynerni qayta yaratish kerak:
`docker compose up -d --force-recreate backend bot worker`

**`Cannot connect to the Docker daemon`**
Docker Desktop ishga tushmagan yoki pauzada. Uni oching, "Engine running"
yozuvini kuting va buyruqni qaytaring.

**`make init` «Backend 5 daqiqada javob bermadi» deydi**
Sekin internetda birinchi build uzoqroq ketishi mumkin. Loglarga qarang:
`make logs-backend`. Konteynerlar holati: `docker compose ps`.

**Jadval yo'q / ustun yo'q xatosi**
Backend ishga tushganda `python -m src.bootstrap` jadvallarni o'zi
yaratadi va yetishmayotgan ustunlarni qo'shadi (idempotent).
Qo'lda: `make migrate`, keyin `docker compose restart backend`.
Konteyner umuman ko'tarilmasa: `docker compose up -d --force-recreate backend`.

**`make` topilmadi (Windows)**
`cp .env.example .env && docker compose up -d --build` — bu `make init`
bilan bir xil ish qiladi (kutish va xabarsiz).

---

## Arxitektura

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  web         │   │  backend     │   │  bot         │
│  Vite+React  │──▶│  FastAPI     │◀──│  aiogram     │
│  :5180       │   │  :8010       │   │  Telegram    │
└──────────────┘   └──────┬───────┘   └──────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
       ┌─────────────┐        ┌─────────────┐
       │ PostgreSQL  │        │ Redis       │
       │ + pgvector  │        │ queue/cache │
       └─────────────┘        └─────────────┘
```

### Papka strukturasi

```
zvonki/
├── services/
│   ├── backend/          Python · FastAPI · SQLAlchemy · Celery
│   │   ├── src/
│   │   │   ├── core/         konfiguratsiya, baza, xavfsizlik, deps
│   │   │   ├── shared/       umumiy bazaviy sinflar
│   │   │   └── modules/      ← CLEAN ARCHITECTURE
│   │   │       ├── auth/
│   │   │       ├── users/
│   │   │       ├── agents/
│   │   │       ├── clients/
│   │   │       ├── calls/
│   │   │       ├── scoring/
│   │   │       ├── surveys/
│   │   │       ├── analytics/
│   │   │       └── settings/
│   │   └── migrations/   Alembic
│   │
│   ├── bot/              Python · aiogram
│   │   └── src/
│   │       ├── core/         sozlamalar
│   │       ├── handlers/     so'rovnoma oqimi
│   │       ├── keyboards/    inline tugmalar
│   │       ├── states/       FSM bosqichlari
│   │       └── services/     backend klienti
│   │
│   └── web/              TypeScript · React · Vite · Tailwind
│       └── src/
│           ├── app/          router, providerlar
│           ├── modules/      ← xususiyat modullari
│           │   ├── auth/
│           │   ├── dashboard/
│           │   ├── analytics/
│           │   └── settings/
│           └── shared/       ui, api, i18n, layout, hooks, lib
│
├── infra/postgres/       baza init skripti
└── docs/PLAN.md          to'liq loyiha rejasi
```

### Clean architecture — backend moduli

Har bir modul 4 qatlamdan iborat. **Bog'liqlik faqat ichkariga qaraydi:**

```
presentation/    FastAPI router + Pydantic sxemalar
      ↓
application/     use case'lar, servislar
      ↓
domain/          sof Python — entity, enum, qoidalar
      ↑
infrastructure/  SQLAlchemy modellari, repozitoriylar
```

`domain/` qatlami FastAPI'ni ham, SQLAlchemy'ni ham bilmaydi —
shuning uchun biznes qoidalarini o'zgartirish uchun butun loyihani
o'rganish shart emas.

---

## Rollar

| Rol | Nima ko'radi |
|---|---|
| **admin** | Hamma narsa + foydalanuvchilar va sozlamalarni boshqarish |
| **manager** | Barcha ma'lumot, filtrlar, tahlil (Power BI kabi). Sozlamalarni faqat ko'radi |
| **sales** | **Faqat o'zining** ballari. Akkaunt o'zi tomonidan boshqarilmaydi — tizim baholarni yozib boradi |
| **viewer** | Faqat ko'rish — savdo xonasidagi monitor uchun (`/monitor`) |

Cheklov ikki joyda majburlanadi: backend servis qatlamida (`AnalyticsService._scoped`)
va frontend router'ida (`RoleGate`).

---

## Sozlamalar bo'limi

AI provayderlari, API kalitlari va qoidalar **dashboard orqali** o'zgartiriladi —
kodga tegmasdan, qayta deploy qilmasdan.

**Ustuvorlik:** bazadagi qiymat → `.env` → standart qiymat

Yangi sozlama qo'shish uchun bitta joyga bitta qator qo'shiladi:
`services/backend/src/modules/settings/domain/entities.py` → `SETTINGS_REGISTRY`.
UI, validatsiya va API avtomatik moslashadi.

Maxfiy kalitlar API orqali **hech qachon qaytarilmaydi** — faqat
"to'ldirilgan / to'ldirilmagan" holati ko'rsatiladi.

---

## Portlar

Boshqa loyihalar bilan to'qnashmasligi uchun alohida blok ajratilgan:

| Servis | Port |
|---|---|
| web | 5180 |
| backend | 8010 |
| postgres | 5433 |
| redis | 6380 |

O'zgartirish uchun `.env` faylini tahrirlang.

---

## UI qoidalari (loyiha konvensiyasi)

Bu qoidalar butun loyiha bo'ylab bir xil qo'llanadi:

| # | Qoida | Nega |
|---|---|---|
| 1 | **Yaratish / tahrirlash — faqat modal oynada.** Sahifaning o'ziga input maydonlari chiqarilmaydi | Sahifa o'qish uchun, modal — harakat uchun. Kontekst yo'qolmaydi |
| 2 | Sahifa kengligi qat'iy cheklanmaydi — `Page` komponenti ishlatiladi | 4K va TV ekranda bo'sh joy qolmaydi |
| 3 | Matnli kontent cho'zilmaydi — `PageGrid` bilan ustunlarga bo'linadi | O'qish qulayligi |
| 4 | Faqat sahifa kontenti scroll qiladi, yon panel qotib turadi | `h-screen overflow-hidden` |
| 5 | Rang faqat token orqali (`hsl(var(--accent))`), to'g'ridan-to'g'ri hex yozilmaydi | Yorug'/qorong'i mavzu avtomatik ishlaydi |
| 6 | `dark:` variantiga tayanmaslik — uchala holat qo'lda yoziladi | "System" rejimida `data-theme` atributi yo'q, `dark:` ishlamaydi |

Modal ishlatish:

```tsx
import { Modal, ModalFields } from '@/shared/ui/Modal'

<Modal open={open} onOpenChange={setOpen} title="..." footer={<Button>Saqlash</Button>}>
  <ModalFields>{/* maydonlar */}</ModalFields>
</Modal>
```

---

## Keyingi bosqichlar

Hozir tayyor: autentifikatsiya, rollar, dashboard, analitika, sozlamalar, bot skeleti.

Navbatdagi ishlar (`docs/PLAN.md` → 9-bo'lim):

1. **MoyZvonki integratsiyasi** — webhook + audio yuklab olish
2. **ASR benchmark** — Groq / ElevenLabs / Kotib solishtiruvi (Bosqich 0)
3. **ASR + diarizatsiya worker** — Celery vazifalari
4. **LLM baholash** — rubrika, Batch API, prompt caching
5. **So'rovnoma endpointlari** — bot allaqachon ularni chaqirishga tayyor
6. **Qo'ng'iroq tafsiloti sahifasi** — audio player + transkript + baholash
