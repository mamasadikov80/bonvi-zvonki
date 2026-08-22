# BonviZvonki — holat

> Yangi seans (`/clear` dan keyin) shu fayldan boshlansin.
> To'liq tadqiqot va reja: `docs/PLAN.md`. UI konvensiyalari: `README.md`.

Oxirgi yangilanish: 15/08/2026 (3-seans)

---

## 1. Ishga tushirish

```bash
docker compose up -d      # hammasi konteynerda, kompyuterga hech narsa o'rnatilmaydi
docker compose logs -f backend
```

> **`.env` o'zgarsa `restart` yetmaydi.** Compose `env_file` qiymatlarini konteyner
> yaratilishida biriktiradi. Kerak: `docker compose up -d --force-recreate backend bot`.

| Xizmat   | Konteyner        | Port (host) | Manzil                          |
| -------- | ---------------- | ----------- | ------------------------------- |
| web      | `zvonki-web`     | 5180        | http://localhost:5180           |
| backend  | `zvonki-backend` | 8010        | http://localhost:8010/docs      |
| postgres | `zvonki-postgres`| 5433        | `zvonki` / bazasi `zvonki`      |
| redis    | `zvonki-redis`   | 6380        | —                               |
| bot      | `zvonki-bot`     | —           | aiogram, RedisStorage FSM       |
| worker   | `zvonki-worker`  | —           | Celery — ASR + baholash         |

Portlar 5173/8000/5432/6379 dan ko'chirilgan — foydalanuvchining `zinnur-v2` loyihasi
5173 ni band qilgan. Uni umuman tegmaymiz.

### Kirish (seed)

| Rol     | Email                | Parol          |
| ------- | -------------------- | -------------- |
| admin   | `admin@zvonki.uz`    | `admin12345`   |
| manager | `manager@zvonki.uz`  | `manager12345` |
| sales   | `sardor@zvonki.uz`   | `sardor12345`  |
| viewer  | `viewer@zvonki.uz`   | `viewer12345`  |

Bazada hozir: **15 savdo xodimi, 135 mijoz, 9 340 qo'ng'iroq + baho,
503 so'rovnoma, 270 javob** (har xodimda 16+ ta, javob berish darajasi ~54%).
`python -m src.seed` idempotent — qayta ishga tushirsa nusxa yaratmaydi.
`--reset` bilan demo ma'lumot tozalanadi, `--agents-only` bilan faqat xodimlar.

---

## 2. Qat'iy konvensiyalar (buzilmasin)

1. **Modal window** — har qanday qo'shish/tahrirlash faqat modalda. Ekranga inline
   input chiqarilmaydi. `shared/ui/Modal.tsx` + `ModalFields` ishlatiladi.
2. **To'liq kenglik** — sahifa kontenti `shared/layout/Page.tsx` orqali dinamik
   egallanadi (`2xl:px-10 3xl:px-14`), 4K/televizorda ham cho'zilib turadi.
3. **iOS uslubi** — chegara emas, yumshoq soya (`shadow-soft`), katta radius
   (`rounded-2xl`), `ease-ios` bilan silliq animatsiya.
4. Backend xizmati nomi — **`backend`**, hech qachon `api` emas.
5. Docker image/konteyner nomlari professional: `zvonki/backend:dev`, `zvonki-postgres`.
6. Baza — **PostgreSQL** (pgvector/pg16).
7. **Sana** admin va manager uchun to'liq: `12/08/2026`. `shared/lib/date.ts` →
   `useDateFormat()` rolga qarab formatni tanlaydi.

### Ikkita tuzoq (yana tushib qolmaslik uchun)

- **Tailwind `dark:` varianti "system" rejimda ishlamaydi** — `data-theme` atributi
  bo'lmaydi. Ranglar uchta holatda ham CSS o'zgaruvchisi orqali beriladi:
  yalang'och `:root`, `@media (prefers-color-scheme: dark)` (`:root:not([data-theme='light'])`
  bilan himoyalangan) va `:root[data-theme='dark']`.
- **Chrome `toLocaleDateString('uz-UZ')` oy nomini "M04" deb qaytaradi.** Oy nomlari
  `shared/lib/date.ts` da qo'lda yozilgan (`MONTHS_UZ`, `MONTHS_UZ_SHORT`).
- **Jadval nomi `app_settings`**, oddiy `settings` emas.
- **Guruh a'zolar soniga qarab tasniflanmaydi.** «Keraksiz guruh» degan
  tur yo'q. Ishchi guruhni HUDUD belgilaydi: hududi bor → so'rovnoma
  oladi, hududsiz → olmaydi. Sinovda ma'lum bo'ldiki, haqiqiy ishchi
  guruh «Bonvi works» da atigi 2 a'zo bor — a'zolar soni bo'yicha
  taxmin qilish uni jimgina o'chirib qo'yardi.
- **Bot guruh a'zosining telefon raqamini KO'RA OLMAYDI.** Telegram
  cheklovi, aylanib o'tib bo'lmaydi. Shuning uchun sotuvchi raqamini
  botga bir marta o'zi yuboradi (`request_contact`), keyin guruhlar
  avtomatik biriktiriladi.
- **Call audio bizda SAQLANMAYDI.** MoyZvonki'dan oqim bilan olinadi va
  uzatiladi. Diskka, bazaga, vaqtinchalik papkaga yozish taqiqlanadi.
- **`pydantic` versiyasi qotirilgan (2.13.4).** `google-genai>=2.18`
  `pydantic>=2.12.5` talab qiladi. Pastroq versiya bilan obraz umuman
  qayta yig'ilmaydi («No solution found»), garchi ishlab turgan
  konteyner ishlayotgandek ko'rinsa ham.
- **Hududlar qattiq yozilmaydi.** Yagona manba — `regions` jadvali,
  `GET /regions`. Kodga viloyat ro'yxatini yozmang: admin viloyatni bir necha
  hududga bo'lishi mumkin. `groups/domain/entities.py` dagi
  `SUGGESTION_REGIONS` — ro'yxat emas, faqat guruh nomidan taxmin qilish
  uchun sinonimlar lug'ati («Nukus» → Qoraqalpog'iston).
- **`bootstrap.py` `create_all` ishlatadi — mavjud jadvalga ustun qo'shmaydi.**
  Yangi ustun qo'shsangiz haqiqiy Alembic migratsiyasi yozing yoki qo'lda:
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`.

---

## 3. Tayyor bo'lgan qismlar

**Backend** (`services/backend/src/modules/…`, har birida `domain → application →
infrastructure → presentation`):

- `auth` — JWT (access + refresh), bcrypt to'g'ridan-to'g'ri (passlib **emas**).
- `users` — 4 rol. `ROLE_PERMISSIONS` bazaviy to'plam + `resolve_permissions(role, access)`
  sozlamalardan qo'shimcha huquq qo'shadi. Ya'ni admin deploy qilmasdan sales nimani
  ko'rishini o'zgartira oladi.
- `agents` — CRUD + **profil rasmi** (`POST`/`DELETE /agents/{id}/avatar`).
  `avatar_service.py` rasmni 256×256 WebP ga keltiradi (~2 KB), kvadratga kesadi,
  shaffoflikni oq fonga yopishtiradi. Fayllar `zvonki-media` volumeda,
  `/media` orqali beriladi. `mimetypes.add_type("image/webp")` `main.py` da.
- `clients`, `calls`, `scoring` (versiyalanadigan rubrika, bloklar yig'indisi
  qat'iy 100 bo'lishi tekshiriladi), `surveys` (rolga qarab ko'rinadi),
  `analytics` (8 ta endpoint, rol bo'yicha cheklov `_scoped()` da),
  `settings` (`SETTINGS_REGISTRY` — bitta qator qo'shsang UI da yangi sozlama paydo bo'ladi;
  maxfiy qiymatlar API dan hech qachon qaytmaydi).

**Frontend** (`services/web/src`) — Vite 6 + React 19 + TS + Tailwind + Radix +
TanStack Query/Table + Recharts + i18next (uz/ru/en) + zustand.
Tayyor sahifalar: Login, Dashboard, Agents (kartochka/jadval), Agent profili,
Calls + Call detali, Rubrika, Foydalanuvchilar, Sozlamalar, Monitor (TV uchun).

**Bot** — aiogram 3.17. Jonli: **@bonvisalesdashboardbot** ("Bonvi Sales Dashboard
Controller"). Tokeni **bazadan** olinadi, `.env` faqat zaxira. `core/runner.py` dagi
`BotRunner` har 30 soniyada `/settings/bot-config` ni so'raydi va token o'zgargan
bo'lsa botni o'zi qayta ishga tushiradi — admin panelda almashtirsangiz
`docker compose restart` **kerak emas**. Noto'g'ri token kiritilsa bot o'chib
qolmaydi, o'zbekcha ogohlantirish chiqarib to'g'risini kutadi.

### Shu seansda qo'shilgani — Mijozlar bo'limi

Tizim shu paytgacha faqat XODIM darajasida kesilardi. Endi menyuda
«Mijozlar» bor va u boshqa savolga javob beradi: kim bilan qancha
gaplashilgan, nechtasiga javob berilmagan, oxirgi aloqa qachon bo'lgan.

**Mijoz alohida yozuv EMAS.** `clients` katalogi bo'sh (0 qator) va
`calls.client_id` ning hech birida qiymat yo'q — katalog boshqa vazifa
uchun (Telegram so'rovnomasi, unda hudud majburiy). MoyZvonki esa har
qo'ng'iroqda raqamni va ko'pincha nomni beradi, shuning uchun ro'yxat
QO'NG'IROQLARDAN yig'iladi. Kalit — raqamning oxirgi 9 tasi (tizimda
hamma joyda shunday), ya'ni «+998 90 111-22-33», «998901112233» va
«901112233» bitta mijoz. Hozir 2 238 ta mijoz chiqadi.

Ichki suhbatlar sukut bo'yicha kirmaydi (hamkasb mijoz emas), lekin
tanlagichda «Ichki raqamlar» va «Hammasi» variantlari bor — filtr
yashirin emas.

⚠️ `*700` bilan tugaydigan omborlar hozir MIJOZ bo'lib ko'rinadi
(«Asosiy Ombor Zakas» — 870 qo'ng'iroq). Bu tasodif emas: suffiks
qoidasi sozlamada ataylab yoqilmagan. Kerak bo'lsa
`moizvonki.internal_numbers` ga `*700` yozilsa, ular «ichki» ga o'tadi.

Endpointlar: `GET /clients` (sahifalash, saralash, qidiruv, davr/xodim/
hudud filtri), `GET /clients/{kalit}` (yig'ma + gaplashgan xodimlar),
`GET /clients/{kalit}/calls`. Ruxsat qo'ng'iroqlarniki — bu o'sha
ma'lumotning boshqa kesimi; SALES faqat o'zi gaplashganlarni ko'radi.

Kartochka sukut bo'yicha BUTUN TARIXNI ko'rsatadi, lekin «Davr»
tugmasi bilan oraliq tanlash mumkin — «bu mijoz bilan qachon va kim
gaplashgan?» degan savol uchun. Tanlangan davr sahifaning hammasiga
tegadi: ko'rsatkichlar, «kim gaplashgan» va suhbatlar jadvali.
Sarlavha ostida sonlar qaysi oraliqqa tegishli ekani yozilib turadi.

⚠️ Bo'sh davr «mijoz topilmadi» EMAS: backend nollar bilan javob
qaytaradi (nomi butun tarixdan olinadi) va sahifa ochiq qoladi.
Aks holda davrni toraytirgan odam mijozni yo'qotgandek ko'rardi.

12 ta yangi test (`modules/clients/tests`).

### Shu seansda o'zgargani — qo'ng'iroq turi va baholash yengilligi

**1. Turlar ikkitaga tushdi: `sales` va `internal`.** Ilgari AI transkript
MAZMUNIGA qarab «savdo / xizmat / ichki / shaxsiy / aniqlanmadi» deb ajratardi
va yanglishardi: eski mijoz ham «qoldiq qancha, narx qanaqa» deb qisqa
gaplashadi — bu hamkasb suhbatidan farq qilmaydi. O'lchandi: tasniflangan 98
qo'ng'iroqdan **82 tasi «ichki»**, savdo esa atigi 9 ta bo'lib chiqqan, ya'ni
haqiqiy savdo suhbatlarining ko'pi baholanmay qolgan.

Endi tur RAQAM bo'yicha aniqlanadi (`calls/domain/routing.py`) va LLM chaqiruvi
TALAB QILMAYDI:

- suhbatdoshning raqami kompaniya liniyalari ro'yxatida bo'lsa → `internal`;
- ATS qisqa raqami (6 raqamdan kam) → `internal`;
- qolgan hammasi → `sales` (baholanadi).

Ro'yxat uch manbadan yig'iladi (`calls/application/internal_directory.py`):
`calls.agent_number` (MoyZvonki `src_number` — har sinxronizatsiyada o'zi
to'ladi), `agents.phone`, va admin sozlamasi (`moizvonki.internal_numbers`,
`*700` kabi suffiks qoidasini ham qabul qiladi).

⚠️ Ichki suhbat ham TRANSKRIPT oladi — faqat ball qo'yilmaydi.
⚠️ Ro'yxat bo'sh bo'lsa quvur qo'ng'iroqqa TEGMAYDI (`DirectoryEmptyError`):
aks holda hamma suhbat «tashqi» bo'lib, ichkilari ham baholanib ketardi.

**2. Baholashda «taalluqli emas» (`na`).** Mijozlarning aksariyati eski mijoz:
«akajon, menga 50 ta chiqaring» deb 30 soniyada tugatadi. Ilgari bunday
suhbatga to'liq skript rubrikasi qo'llanardi va xodim aybsiz holda 40–50 ball
olardi. Endi rubrikadagi har mezonda `optional` bayrog'i bor; AI o'rinsiz
mezonni `verdict: "na"` deb belgilaydi va u hisobdan CHIQADI (nol ham olmaydi).
Ball qo'llanilganlar ichida hisoblanadi: `blok × olingan / qo'llanilgan`.

Uchta himoya bor, aks holda hammasi 100 ball bo'lib ketardi (o'lchandi —
bo'ldi ham):
- `na` faqat `optional: true` mezonda (salomlashish, muomala madaniyati,
  savolga javob, kelishuv aniqligi — har doim baholanadi, 51 ball);
- **uzunlikka bog'liq budjet**: 90 soniyagacha chegara yo'q, 4 daqiqadan
  uzun suhbatda `na` ga ko'pi bilan 20 ball. Oxirgi urinishda chegara
  yumshaydi, lekin baho tekshiruv navbatiga tushadi (`na_over_budget`);
- qo'llanilganlar 40 balldan kam qolsa javob rad etiladi.

Model endi `overall_score` ni ham, blok balini ham QAYTARMAYDI — ikkalasi
kriteriyalardan hisoblanadi. Kriteriyalar javobda OBYEKT bo'lib keladi
(`{"A1": {...}}`), shuning uchun har mezon o'z chegarasini va o'z verdikt
ro'yxatini oladi — model tashlangan mezonning ballini boshqalarga taqsimlay
olmaydi.

**Real ma'lumotda sinaldi:** qisqa takroriy buyurtmalar 88–100, uzun
suhbatlar 58–92, mazmunsiz suhbat («salomlashib qayta qo'ng'iroq kelishildi»)
17–34 + tekshiruv bayrog'i.

**3. Yon tuzatish:** `review_rules.count_words` endi `[04:12]` va `SPEAKER_1:`
xizmat belgilarini sanamaydi. Ular so'z deb sanalgani uchun eng qisqa, ya'ni
eng shubhali suhbatlar tekshiruv navbatiga TUSHMAY qolardi.

**Keyingi qadam:** kompaniya liniyalari ro'yxati to'lishi uchun MoyZvonki
sinxronizatsiyasi kerak — kechki avtomatik yurish buni o'zi qiladi
(`agent_number` har qatorga yoziladi). Xodimlar kartochkasidagi telefon
raqamini to'ldirish ham ro'yxatni kengaytiradi (33 xodimdan 10 tasida bor).

### Oxirgi seansda tugatilgani

- **Sana bo'yicha filtr** — `shared/ui/DateRangePicker.tsx`: 7 tayyor davr
  (7/30/90 kun, shu oy, o'tgan oy, shu chorak, shu yil) + 4 yil chipi +
  ixtiyoriy boshlanish/tugash sanasi. Dashboard va Agent profilida ulangan.
  `AnalyticsQuery` ga `date_from`/`date_to` qo'shilgan.
- **Profil rasmi** — backend + frontend to'liq. `AgentModal` da yuklash/almashtirish/
  o'chirish; yangi xodimda fayl saqlanib turadi va xodim yaratilgach yuklanadi.
  `Avatar` komponenti `src` qabul qiladi, bo'lmasa bosh harflarga qaytadi.
  `avatar_url` leaderboard javobiga ham qo'shilgan, shuning uchun Dashboard,
  Monitor va TopPerformers da ham rasm ko'rinadi.

Tekshirilgan: TypeScript 0 xato; 900×600 PNG → 256×256 WebP 1.8 KB;
`/media/...` → `HTTP 200 image/webp`; `text/plain` yuklash → 422;
sales roli avatar yuklashga urinsa → 403; manager ham 403 (chunki
`access.manager_manages_agents` sukut bo'yicha o'chiq — admin Sozlamalardan yoqadi).

- **So'rovnoma oqimi** — `POST /surveys/{token}/open` va `/submit`. **Ochiq
  endpointlar, autentifikatsiyasiz** — token o'zi kalit, chunki javob beruvchi
  do'kondor hech qachon tizimga kirmaydi. Xatolar o'zbekcha: 404 topilmadi,
  409 muddati o'tgan, 409 allaqachon baholangan, 422 noto'g'ri qiymat.
  `telegram_user_id` qabul qilinadi, lekin **ataylab saqlanmaydi** — saqlansa
  bitta JOIN bilan "kim qanday baho qo'ygani" ochilib, anonimlik va'dasi buzilardi.
- **Client baholari sahifasi** — `/surveys`. Rolga qarab: admin/manager hammasini
  ko'radi, sales faqat o'zinikini ("Mening client baholarim"). `ready:false`
  bo'lsa o'rtacha ko'rsatilmaydi (5 tadan kam javob) — 0 emas, izoh chiqadi.
- **`GET /surveys`** ga `date_from`/`date_to` qo'shildi, `days` dan ustun turadi.
- **422 xatolar** endi loyiha konvertida va o'zbekcha (`main.py` dagi
  `RequestValidationError` handleri) — ochiq endpointlarda xatoni client ko'radi.

---

### 4-seansda qo'shilgani (tungi ish)

- **MoyZvonki ko'prigi** — `modules/moizvonki/`. `GET /calls/{id}/audio`
  yozuvni MoyZvonki'dan OQIM bilan uzatadi. `Range` qo'llab-quvvatlanadi
  (206 + `Content-Range`), shuning uchun pleerda oldinga o'tish ishlaydi.
  **Isbotlangan:** 200 MB oqimda fayl tizimi bayt-baytga o'zgarmadi,
  xotira +28 KB. `POST /calls/sync` — metadata tortish, idempotent.
- **AI provayderlari reyestri** — `modules/ai/`. Groq · OpenAI · Gemini ·
  Claude · ElevenLabs. Ikki rol: ASR va LLM. Admin panelda tanlanadi,
  kalit kiritiladi, «Tekshirish» bosiladi. Yangi provayder qo'shish =
  reyestrda bitta yozuv (isbotlangan: 141 fayldan faqat bittasi o'zgardi).
  Model nomlari erkin matn — provayder yangi model chiqarsa kod
  o'zgartirilmaydi.
- **Baholash konveyeri** — `modules/pipeline/` + Celery worker.
  Audio → ASR → transkript → LLM + rubrika → baho. Audio hech qayerda
  saqlanmaydi. LLM javobi qat'iy tekshiriladi: bloklar yig'indisi ballga
  mos kelmasa yoki o'ylab topilgan red flag kaliti bo'lsa — **saqlanmaydi**.
  Noto'g'ri javobda LLM ga tuzatuvchi ko'rsatma bilan qayta so'raladi.
  Endpointlar: `/pipeline/run`, `/pipeline/status`, `/pipeline/failures`,
  `/pipeline/calls/{id}/retry`.
- **Audio pleer** — `CallDetailPage`. `<audio src>` `Authorization`
  yubora olmaydi, shuning uchun **Service Worker ko'prigi** ishlatiladi
  (`public/audio-sw.js`): token SW da qo'shiladi, brauzer o'zi `Range`
  yuboradi, seek nativ ishlaydi. SW yo'q muhitda blob zaxirasi.

### 3-seansda qo'shilgani

- **Telegram Mini App so'rovnomasi.** Guruh xabarida bitta havola →
  sahifa Telegram ICHIDA ochiladi (`/s`). Ball, izoh va red flag —
  hammasi shu yerda. `initData` imzosi bot tokeni bilan tekshiriladi;
  `user_id` saqlanmaydi, faqat hash. Sahifa doim yorug', ranglar
  dashboarddan olingan.
  ⚠️ **Muhim:** rasmiy hujjat chalg'itadi — HMAC tekshiruvida
  `signature` maydoni CHIQARILMAYDI, faqat `hash`. Aks holda zamonaviy
  Telegram mijozidan kelgan hech narsa o'tmaydi.
- **Mini App sozlanmagan bo'lsa** bot eski oqimda ishlaydi: guruhda
  faqat 1–5 tugmalari (izoh tugmasi olib tashlangan).
- **Guruhlar avtomatik biriktiriladi** — botni kim qo'shgani, guruh
  adminlari va guruhda yozganlar bo'yicha. Admin qo'lda o'zgartirgan
  guruhga (`bound_by="manual"`) avtomatika tegmaydi.
- **Guruhlar daraxti** — `/groups`: sotuvchi → hudud → guruhlar.
  Sahifalangan (`page_size` 50, eng ko'pi 200), ochilgandagina yuklanadi.
  Ommaviy hudud biriktirish/bo'shatish bor.
- **Sotuvchi alohida baholarni ko'rmaydi** — har guruhda bitta mijoz
  bo'lgani uchun baho kimniki ekani aniqlanadi. `items` SALES uchun
  doim bo'sh, `access.sales_client_rating` sozlamasidan qat'i nazar.
- **Qidiruv** — qo'ng'iroqlar, savdo xodimlari va client baholarida
  (xodim ismi va hudud bo'yicha).
- **Sozlamalar bloklari alohida saqlanadi**, har birida o'z tugmasi.
- **Yuborish tezligi** ~20 xabar/soniya (Telegram chegarasi ~30).
  1000 guruh ≈ 53 soniya.

### 2-seansda qo'shilgani

- **Guruh asosidagi anonim so'rovnoma.** Bot guruhga qo'shilsa o'zini ro'yxatga
  oladi (eski guruhda `/bind`). Admin panelda xodim va hudud biriktiriladi.
  Guruhga 5 tugmali xabar tushadi; ball guruhda, izoh va red flag shaxsiy
  chatda. Bir kishi bir marta — `respondent_hash` orqali, Telegram ID hech
  qayerda saqlanmaydi.
- **Telegram guruhlari sahifasi** — `/groups`. Biriktirilmagan guruhlar
  ajratib ko'rsatiladi (ular so'rovnoma olmaydi, ya'ni jimgina ishlamaydi).
  Bitta xodim bir nechta hududni qamrashi ko'rinadi.
- **Hududlar** — `/regions`, admin boshqaradi. Nom o'zgarsa `agents`,
  `clients`, `telegram_groups` da kaskad yangilanadi; ishlatilayotgan hudud
  o'chirilmaydi (409), o'rniga faolsizlantiriladi.
- **Filtrlar dropdownga o'tdi** (`shared/ui/MultiSelect.tsx`). Til filtri
  butunlay olib tashlandi — qo'ng'iroqlar deyarli hammasi o'zbekcha.
- **Davr filtri** to'rt bo'limga bo'lindi: Tayyor · Oy · Yil · Oraliq.
  Yangi imkoniyat — aniq oy («aprel 2024»).
- **«Tekshiruv navbati» olib tashlandi** — menyu, marshrut va `review:*`
  ruxsatlari bilan birga.

---

## 4. Ertalab qilinadigan ishlar (foydalanuvchi uchun)

1. **Tunnel qayta ochish.** Manzil har safar o'zgaradi:
   `docker run --rm --network zvonki-network mirror.gcr.io/cloudflare/cloudflared:latest tunnel --url http://web:5173`
   Docker Hub O'zbekistondan to'silgan — `mirror.gcr.io/` prefiksi shart.
   Yangi manzilni BotFather → Mini App → Web App URL ga `+/s` bilan kiriting.
2. **MoyZvonki hisobi** — Sozlamalar → MoyZvonki: domen, foydalanuvchi,
   API kalit. Keyin qo'ng'iroqlarni tortish sinovi.
3. **AI kalitlari** — Sozlamalar → AI: provayder tanlash + kalit +
   «Tekshirish» tugmasi.
4. **Sotuvchilarni botga ulash** — har biri botni ochib «Raqamimni
   yuborish» bosadi. Shundan keyin guruhlar avtomatik biriktiriladi.
5. **`survey.min_responses`** hozir **1** da (sinov uchun). Ishlab
   chiqarishda 5 ga qaytaring.

---

## 5. Keyingi ishlar (navbat bo'yicha)

1. **So'rovnoma dispetcheri** — hozir so'rovnoma faqat qo'lda («So'rovnoma
   yuborish» tugmasi) yaratiladi. Kadans bo'yicha (14 kun) avtomatik
   yaratadigan Celery vazifasi kerak.
2. **MoyZvonki ingest** — yozuvlarni tortib olish; `agents` sahifasidagi "Sync"
   tugmasi hozircha `disabled`.
3. **So'rovnoma yuboruvchi** — hozir so'rovnomalar faqat seed orqali yaratiladi.
   Kadans bo'yicha (har 14 kun) avtomatik yaratib, Telegram guruhga yuboradigan
   Celery vazifasi kerak. Endpointlar va bot tayyor, yetishmayotgani — dispetcher.
4. **ASR benchmark (PLAN.md Bosqich 0)** — Groq turbo / Groq large-v3 /
   ElevenLabs Scribe ni o'zbek-rus aralash 20 ta qo'ng'iroqda solishtirish.
   Rejadagi tanlov: **ElevenLabs Scribe $0.22/soat** (diarizatsiya narxga kirgan),
   umumiy stsenariy **B ≈ $554/oy**.
5. **ASR + diarizatsiya worker**, keyin **LLM baholash worker** (Celery skeleti bor).

---

## 6. Foydali buyruqlar

```bash
# TypeScript tekshiruvi
docker compose exec -T web npx tsc --noEmit

# Bazaga kirish
docker compose exec -T postgres psql -U zvonki -d zvonki

# Demo ma'lumotni qayta yaratish
docker compose exec -T backend python -m src.seed --reset

# Backendni qayta ishga tushirish (model o'zgarsa)
docker compose restart backend

# .env o'zgarganda (restart yetmaydi!)
docker compose up -d --force-recreate backend bot
```

---

## 7. Maxfiy qiymatlar

`.env` gitignore qilingan, hammasi shu yerda:

| Kalit                 | Nima uchun                                                    |
| --------------------- | ------------------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`  | Bot tokeni — **zaxira**. Asosiysi bazada, admin panelda.       |
| `INTERNAL_API_TOKEN`  | Bot ↔ backend orasidagi ichki kalit (`X-Internal-Token`).      |

`GET /settings/bot-config` haqiqiy, maskalanmagan tokenni qaytaradi — shuning uchun
u foydalanuvchi JWT si bilan emas, `X-Internal-Token` bilan himoyalangan va
fail-closed: `INTERNAL_API_TOKEN` bo'sh bo'lsa hamma uchun 401.
**"Docker tarmog'i ichida" himoya emas** — 8010-port host'ga chiqarilgan.
Loglarda tokenlar hech qachon to'liq chiqmaydi, faqat oxirgi 4 belgi.
