# Bonvi · Savdo analitikasi

**Bonvi** kompaniyasi savdo bo'limi uchun AI-baholash platformasi.
Qo'ng'iroqlar avtomatik transkripsiya qilinadi, rubrika bo'yicha baholanadi va
client'lardan olingan reyting bilan birga bitta dashboardda ko'rsatiladi.

📄 To'liq tahlil va reja: [`docs/PLAN.md`](docs/PLAN.md)

---

## Ishga tushirish

**Talab: faqat Docker.** Kompyuteringizga Python, Node yoki PostgreSQL o'rnatilmaydi.

```bash
make init
```

Shu bitta buyruq `.env` faylini yaratadi, barcha image'larni quradi,
bazani tayyorlaydi va demo ma'lumot yuklaydi.

| Manzil | Nima |
|---|---|
| http://localhost:5180 | Dashboard |
| http://localhost:8010/docs | API hujjatlari (Swagger) |
| http://localhost:5180/monitor | Monitor rejimi (savdo xonasi ekrani) |

**Demo hisoblar:**

| Rol | Email | Parol |
|---|---|---|
| Administrator | `admin@zvonki.uz` | `admin12345` |
| Menejer | `manager@zvonki.uz` | `manager12345` |
| Savdo xodimi | `sardor@zvonki.uz` | `sardor12345` |
| Kuzatuvchi | `viewer@zvonki.uz` | `viewer12345` |

---

## Buyruqlar

```bash
make help          # barcha buyruqlar
make up            # ko'tarish
make down          # to'xtatish
make logs          # loglar (hammasi)
make logs-backend  # faqat backend
make sh-backend    # backend konteyneriga kirish
make psql          # PostgreSQL konsoli
make seed          # demo ma'lumotni qayta yuklash
make migration m="izoh"   # yangi migratsiya
make lint          # kod tekshiruvi
make clean         # to'xtatish + baza o'chirish
```

**Hot reload yoqilgan** — `services/` ichidagi faylni tahrirlasangiz,
tegishli servis avtomatik qayta yuklanadi. Qayta qurish shart emas.

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
