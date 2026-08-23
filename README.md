# Bonvi · Savdo analitikasi

**Bonvi** kompaniyasi savdo bo'limi uchun qo'ng'iroq analitikasi va savdo
nazorati platformasi. MoyZvonki'dan qo'ng'iroq yozuvlari avtomatik olinadi,
transkripsiya qilinadi va rubrika bo'yicha AI tomonidan baholanadi. Natijalar
mijozlardan Telegram bot orqali yig'ilgan reyting bilan birga bitta dashboardda
ko'rsatiladi — rahbar har bir xodim, hudud va davr kesimida ishni ko'rib turadi.

📄 To'liq tahlil va reja: [`docs/PLAN.md`](docs/PLAN.md)

---

## ⚡ Tez ishga tushirish

Faqat **Docker** kerak — boshqa hech narsa o'rnatilmaydi.
Klon qilib, papka ichida bitta buyruq:

```bash
docker compose up -d --build
```

Shu bilan tamom: obrazlar quriladi, baza ko'tariladi, jadvallar
yaratiladi va admin hisobi qo'shiladi. Birinchi marta 3–10 daqiqa
oladi (bazaviy obrazlar yuklanadi), keyingi safar kesh bilan ancha tez.

**Keyingi yangilanishlarda** — xuddi shu buyruq, oldiga `git pull`:

```bash
git pull && docker compose up -d --build
```

Windows'ning eski **PowerShell 5.1** da `&&` ishlamaydi — u yerda `;` bilan:

```powershell
git pull ; docker compose up -d --build
```

Tugagach: **http://localhost:5180** · kirish `admin@zvonki.uz` / `admin12345`

---

> ### 🔑 `.env` — faqat tashqi xizmatlar uchun
>
> Tizim `.env` **siz ham ishlaydi**: baza, portlar va maxfiy kalit
> `docker-compose.yml` da sukut qiymatlar bilan berilgan. Dashboard
> ochiladi, barcha bo'limlar ishlaydi — faqat baza bo'sh bo'ladi.
>
> Tashqi xizmatlar kerak bo'lganda `.env` yaratasiz:
>
> ```bash
> cp -n .env.example .env      # macOS / Linux — mavjudini ezmaydi
> ```
> ```powershell
> Copy-Item .env.example .env -NoClobber    # Windows
> ```
>
> Keyin uni to'ldirib, `docker compose up -d` ni qayta yurgizasiz.
>
> | Qiymat | Nimaga kerak | Bo'lmasa |
> | --- | --- | --- |
> | `MOIZVONKI_DOMAIN`, `MOIZVONKI_API_KEY` | qo'ng'iroqlarni tortib olish | ro'yxat bo'sh qoladi |
> | `TELEGRAM_BOT_TOKEN` | bot va so'rovnomalar | bot ishlamaydi |
> | `SECRET_KEY` | tokenlarni imzolash | dev qiymati ishlatiladi — **ishlab chiqarishda albatta almashtiring** |
>
> AI kaliti `.env` da EMAS — u dashboard ichida, **Sozlamalar** bo'limida
> kiritiladi va bazada saqlanadi.

---

Birinchi buyruq: `.env` yaratadi → image'larni quradi → hamma servisni
ko'taradi. Baza jadvallari, migratsiya va demo ma'lumot backend konteyneri
ichida **avtomatik** bajariladi — alohida buyruq shart emas.

Birinchi ishga tushirish **5–10 daqiqa** oladi (image'lar yuklab olinadi),
keyingilari 1–2 daqiqa. Buyruq qaytgach backend yana bir necha daqiqa
bazani tayyorlaydi — kuzatish: `docker compose logs -f backend`,
holat: `docker compose ps`.

Yangilash buyrug'i ma'lumotni **o'chirmaydi**: unda `down` ham, `-v` ham yo'q.

**Xohlasangiz, aynan shu buyruqlar skriptga ham solingan:**

```bash
./start.sh          # macOS / Linux
```
```powershell
.\start.ps1         # Windows PowerShell
```

---

## Talablar

| Nima | Qancha |
|---|---|
| **Docker Desktop** | 4.30+ (Compose v2 bilan) · Linuxda Docker Engine 24+ va `docker compose` plagini |
| **Disk** | kamida **8 GB** bo'sh joy (image'lar ~5 GB + baza) |
| **RAM** | Docker'ga kamida 4 GB ajratilgan bo'lsin |
| **Bo'sh portlar** | `5180`, `8010`, `5433`, `6380` |
| **Boshqa** | hech narsa. Python, Node, PostgreSQL, `make` — **o'rnatilmaydi** |

Docker tayyorligini tekshirish: `docker info` xatosiz chiqsa bo'ldi.

**Windows uchun alohida:**
- Docker Desktop **ishga tushgan** bo'lsin (trey belgisi yashil, "Engine running").
- **WSL2 yoqilgan** bo'lsin — Docker Desktop → Settings → General →
  *Use the WSL 2 based engine*. Yoqilmagan bo'lsa konteynerlar ko'tarilmaydi.
- Buyruqlar **PowerShell** da yoziladi (`cmd.exe` da emas).

---

## `.env` sozlamalari

Birinchi buyruqdagi nusxa uni `.env.example` dan yaratadi va **shu holicha
tizim to'liq ko'tariladi** — hech narsa to'ldirmasangiz ham dashboard,
demo ma'lumot va analitika ishlaydi.

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

Hamma joyda ishlaydi — qo'shimcha dastur talab qilmaydi:

```bash
docker compose ps                      # nima ishlayapti
docker compose logs -f                 # loglar (hammasi)
docker compose logs -f backend         # faqat backend
docker compose restart                 # qayta ishga tushirish
docker compose down                    # to'xtatish (ma'lumot SAQLANADI)
docker compose up -d --build           # ko'tarish / yangilash

docker compose exec backend bash                       # konteynerga kirish
docker compose exec postgres psql -U zvonki -d zvonki  # PostgreSQL konsoli
docker compose exec backend python -m src.seed         # demo ma'lumot (idempotent)
docker compose exec backend alembic upgrade head       # migratsiyalar
docker compose exec backend pytest -q                  # backend testlari
```

**Hot reload yoqilgan** — `services/` ichidagi faylni tahrirlasangiz,
tegishli servis avtomatik qayta yuklanadi. Qayta qurish shart emas.

### Qulaylik uchun: `make` (ixtiyoriy)

Agar kompyuteringizda `make` **o'rnatilgan** bo'lsa, yuqoridagilarning
qisqa varianti bor. `make` alohida dastur — **u bo'lmasa ham hammasi
ishlaydi**, yuqoridagi `docker compose` buyruqlaridan foydalaning.

- macOS'da olish: `xcode-select --install`
- Linuxda: `sudo apt install make` (yoki distributivingizga mos)
- Windowsda odatda yo'q — PowerShell buyruqlaridan foydalaning

```bash
make help          # barcha buyruqlar ro'yxati
make init          # birinchi marta: .env + build + ko'tarish + kutish
make update        # git pull + qayta qurish (baza saqlanadi)
make up / down / restart / logs / logs-backend
make sh-backend / psql / seed / migrate / test / lint
```

### 🛑 Ma'lumotni O'CHIRADIGAN buyruqlar

Yuqoridagilarning hech biri bazaga tegmaydi — `docker compose down` ham
volume'ni saqlaydi. Quyidagilar esa **butun bazani o'chiradi**: ular
`docker compose down -v` ishlatadi, volume'lar bilan birga barcha
qo'ng'iroqlar, baholar va sozlamalar yo'qoladi.

| Buyruq | Nima o'chadi |
|---|---|
| `docker compose down -v` · `make clean` | konteynerlar + **volume'lar (BAZA)** |
| `make nuke` | yuqoridagilar + image'lar |
| `make seed-reset` | demo ma'lumot tozalanib qayta yaratiladi |
| `make clean-no-audio` | audiosiz, baholanmagan qo'ng'iroq qatorlari |

Boshqa kompyuterda ishga tushirayotganda bularning hech biri **kerak emas**.

---

## Muammolar

**`make: command not found` / `make : The term 'make' is not recognized`**
`make` — alohida dastur, u loyihaning talabi EMAS. Windowsda odatda umuman
yo'q, macOS'da Xcode buyruq qatori vositalarisiz yo'q. Yechim: yuqoridagi
`docker compose` buyruqlaridan foydalaning. `make` aynan kerak bo'lsa:
macOS — `xcode-select --install`, Linux — `sudo apt install make`.

**`env file .../.env not found`**
Eski Docker Compose (2.24 dan past) `.env` ni majburiy deb biladi. Ikki
yechim: Docker Desktop'ni yangilash yoki bo'sh fayl yaratish —
`cp .env.example .env` (Windowsda `copy .env.example .env`), so'ng
buyruqni qaytarish. Yangi Compose'da bu xato umuman chiqmaydi:
`.env` ixtiyoriy qilib belgilangan.

**Port band** (`bind: address already in use`)
`.env` dagi `WEB_PORT` / `API_PORT` / `POSTGRES_PORT` / `REDIS_PORT` ni
o'zgartiring, so'ng `docker compose up -d --force-recreate`.
Kim band qilganini ko'rish: `lsof -i :5180` (macOS/Linux),
`netstat -ano | findstr :5180` (Windows).

**`.env` ni o'zgartirdim, lekin ta'sir qilmadi**
`restart` yetmaydi — Compose `env_file` qiymatlarini konteyner *yaratilishida*
biriktiradi. Kerak: `docker compose up -d --force-recreate backend bot worker`

**`Cannot connect to the Docker daemon`**
Docker Desktop ishga tushmagan yoki pauzada. Uni oching, "Engine running"
yozuvini kuting va buyruqni qaytaring. Windowsda qo'shimcha: Settings →
General → *Use the WSL 2 based engine* yoqilgan bo'lsin.

**Buyruq tugadi, lekin `localhost:5180` ochilmayapti**
Backend hali bazani tayyorlayotgan bo'lishi mumkin (birinchi safar bir
necha daqiqa). Holat: `docker compose ps` — `backend` `healthy` bo'lishi
kerak. Kuzatish: `docker compose logs -f backend`.

**Jadval yo'q / ustun yo'q xatosi**
Backend ishga tushganda `python -m src.bootstrap` jadvallarni o'zi
yaratadi va yetishmayotgan ustunlarni qo'shadi (idempotent). Qo'lda:
`docker compose exec backend alembic upgrade head`, keyin
`docker compose restart backend`. Konteyner umuman ko'tarilmasa:
`docker compose up -d --force-recreate backend`.

**`./start.sh: Permission denied`**
`chmod +x start.sh` — yoki to'g'ridan-to'g'ri: `bash start.sh`.

**PowerShell `.\start.ps1` ni ishga tushirmayapti**
Bir seansga ruxsat: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`,
yoki skriptsiz — README boshidagi ikki buyruqni qo'lda yozing.

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
