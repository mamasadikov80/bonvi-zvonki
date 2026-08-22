# Savdo nazorati — texnik shartnoma (spec)

> Bu hujjat ishlab chiquvchilar uchun YAGONA manba. Jadval nomlari,
> ustunlar va qoidalar shu yerdan olinadi. O'zgarish bo'lsa avval shu
> fayl yangilanadi.

## 1. Maqsad

Har bir savdo **rasmiy kelishuv** bilan — ya'ni yozib olingan qo'ng'iroqdan
keyin — bo'lyaptimi yoki tizimdan tashqarida kelishilyaptimi, shuni
aniqlash.

Xavf: xodim mahsulotni o'z narxida sotib, farqini o'zida qoldirishi
mumkin. Buni yashirish uchun kelishuv shaxsiy telefonda bo'ladi — bizda
qo'ng'iroq yozuvi qolmaydi, lekin SAP da savdo qoladi. Demak signal —
**savdo bor, unga mos suhbat yo'q**.

⚠️ Bu tizim AYBLAMAYDI. U faqat tekshirish uchun ro'yxat tayyorlaydi;
qaror rahbarniki (5-bo'lim, tekshiruv navbati).

## 2. Manba ma'lumotlar (o'lchangan, 22.08.2026)

Uch xil Excel eksporti keladi. Barchasi SAP dan qo'lda yuklanadi.

### 2.1 `savdo kunlik.xlsx` — operatsiyalar registri

2 384 qator, 11 kun (10.08–20.08.2026). Ustunlar:
`# | Тип | Номер операции | Подразделение | Направление | № док. |
Дата регистрации | Код заказчика/поставщика | Название заказчика/поставщика |
Название группы | Хақдор ($) | Хақдор (сўм) | Қарздор ($) | Қарздор (сўм) |
Валюта документа | Конвертация`

- `Тип`: **Продажа 1039**, Входящие платежи 999, Закупка 178,
  Исходящие платежи 146, Отмена продажа 17, Бух.оп 5.
  ⚠️ Eksportdagi HAQIQIY matn — `Исходящие платежи платежи`, so'z ikki
  marta yozilgan. Import ikkala ko'rinishni ham tushunadi.
- `Номер операции` — amalda noyob (1 juft istisno) → **idempotentlik kaliti**.
  Takror kelgan qator import ichida bir marta yoziladi.
- `Дата регистрации` — matn `dd.mm.yyyy`, **VAQTI YO'Q** (faqat sana).
- `Хақдор ($)` — savdo summasi (Продажа qatorlarida to'ladi),
  `Қарздор ($)` — to'lov/qarz (Входящие платежи da). Sonlar **matn**:
  `"1 950,000"` (probel = minglik, vergul = o'nlik).
- ⚠️ **`($)` ustuni HAR DOIM dollar ekvivalenti**, `(cўм)` esa hujjat
  valyutasidagi summa (UZS da so'm, CNY da yuan, AED da dirham) —
  sarlavha aldamchi. Misol: UZS hujjatda `8,333 $` ↔ `100 000,000` so'm.
- ⚠️ **Sonlarning bir qismi matn EMAS.** Excel probelsiz qiymatlarni
  (`"561,000"`) o'zi raqamga aylantirib, vergulni minglik ajratkichi deb
  o'qigan va katakka `561000` yozgan (`number_format` = `#,##0`).
  O'lchandi: `Хақдор ($)` da 649 ta shunday katak, 1735 tasi matn.
  Raqam katakdagi qiymat **1000 barobar katta** — import uni bo'ladi.
  Busiz savdo summalari shishib ketardi.
- Valyuta: USD 1895, UZS 391, CNY 84, AED 9 (Бух.оп da bo'sh — USD deb olinadi).
- **Telefon yo'q, sotuvchi ismi yo'q.** Bog'lanish faqat mijoz kodi orqali.
- ⚠️ Savdolarning **~29% i «Разовый клиент» (К00001)** umumiy kodida —
  real mijoz aniqlanmaydi.

### 2.2 `Workbook3.xlsx` — kontragentlar katalogi

3 746 qator, `Код БП` noyob. `Тел ракам` 94.7% to'ldirilgan, 3 090 noyob
oxirgi-9-raqam. `Код группы`: Клиенты 3 284, qolgani yetkazib beruvchi va
h.k. Kamchilik: 85 ta yetkazib beruvchi ikki marta (Й/П prefiks), 43 ta
`КлентID` bir necha kodda, telefon formatlari 10 xil.

### 2.3 `Workbook1/2.xlsx` — mijoz balansi hisoboti

Qator = mijoz × filial × yo'nalish (kod NOYOB EMAS). `Tel raqami` 95%,
1 822 noyob raqam — ikkala faylda bir xil to'plam. **wb2 yangiroq**
(20.08 vs 18.08). Telefon qamrovini wb3 dan oshirmaydi, lekin
`Oxirgi Sotuv` sanasi va qarz holati shu yerda.

### 2.4 Bog'lanish qanchalik ishlaydi (o'lchangan)

| Bosqich | Natija |
| --- | --- |
| Savdo kodlari katalogda topildi | 484 / 484 = **100%** |
| Kodda telefon bor | **93.2%** |
| Telefon bizning `calls` da uchraydi | **62.3%** (savdo mijozlari bo'yicha 68.2%) |
| `Подразделение` → xodim nomiga tushdi | **70.1%** (1039 dan 728) |

Qolgan 38% — qo'ng'iroq tarixi atigi 1 oylik bo'lgani uchun.
**Chora:** MoyZvonki'dan 1 yillik sinxronizatsiya (imkoniyat bor).
Bu qoida uchun AUDIO kerak emas — faqat «suhbat bo'lganmi» degan fakt,
u esa metadata bilan keladi.

## 3. Ma'lumot modeli

Yangi modul: `services/backend/src/modules/sales/`.

### `sale_partners` — kontragent katalogi (wb3 + wb1/wb2 dan)

| ustun | tur | izoh |
| --- | --- | --- |
| `id` | uuid | |
| `code` | varchar(16) UNIQUE | `К02711` — SAP kodi, yagona kalit |
| `name` | varchar(255) | |
| `group_name` | varchar(64) | `Клиенты`, `Поставщики импорт`… |
| `branch` | varchar(128) null | `Подразделение` |
| `phone` | varchar(64) null | xom ko'rinish, ekranda ko'rsatish uchun |
| `phone_key` | varchar(9) null, INDEX | oxirgi 9 raqam — `calls` bilan bog'lash kaliti |
| `is_active` | bool | `Актив` |
| `telegram_link` | varchar(255) null | |
| `updated_at` | timestamptz | |

### `sales` — operatsiyalar

| ustun | tur | izoh |
| --- | --- | --- |
| `id` | uuid | |
| `external_id` | varchar(32) UNIQUE | `Номер операции` — qayta yuklashda upsert |
| `doc_number` | varchar(32) null | `№ док.` |
| `op_type` | varchar(32) | `sale`, `payment_in`, `purchase`, `payment_out`, `sale_cancel`, `accounting`, `other` |
| `occurred_on` | date | ⚠️ faqat sana, vaqti yo'q |
| `branch` | varchar(128) null | `Подразделение` |
| `direction` | varchar(64) null | `Направление` (ВЕЛО, МЕТАН…) |
| `partner_code` | varchar(16) INDEX | |
| `partner_name` | varchar(255) | import paytidagi nusxa |
| `amount` | numeric(18,3) | `Хақдор` yoki `Қарздор` — qaysi tomon to'lgan bo'lsa, **hujjat valyutasida** |
| `currency` | varchar(8) | USD / UZS / CNY / AED |
| `amount_usd` | numeric(18,3) | aynan shu summa dollarda — `($)` ustunidan |
| `agent_id` | uuid null FK agents | filial nomidan aniqlanadi |
| `phone_key` | varchar(9) null INDEX | katalogdan olinadi, import paytida yoziladi |
| `source_file` | varchar(255) | qaysi fayldan kelgani |
| `imported_at` | timestamptz | |

### `sale_reviews` — rahbarning qarori

| ustun | tur | izoh |
| --- | --- | --- |
| `sale_id` | uuid UNIQUE FK sales | |
| `status` | varchar(16) | `justified` (oqlandi) / `confirmed` (haqiqatan shubhali) |
| `reason` | varchar(32) null | `walk_in`, `telegram`, `visit`, `contract`, `other` |
| `note` | text null | |
| `reviewed_by` | uuid FK users | |
| `reviewed_at` | timestamptz | |

⚠️ **Qoida natijasi JADVALGA YOZILMAYDI.** U har safar hisoblanadi:
qo'ng'iroq savdodan KEYIN sinxronlanishi mumkin va o'shanda eski
«shubhali» belgisi yolg'onga aylanardi. Bazada faqat ODAMNING qarori
saqlanadi.

### `sale_branches` — filial → xodim

| ustun | tur | izoh |
| --- | --- | --- |
| `branch` | varchar(128) PK | SAP dagi nom |
| `agent_id` | uuid null FK agents | qo'lda yoki avtomatik biriktiriladi |
| `matched_automatically` | bool | |

Avtomatik moslash: nom normalizatsiyasi → `agents.full_name` bo'yicha
AYNAN TENGLIK (fuzzy yo'q — noto'g'ri xodimga savdo yozish bo'sh
qoldirishdan yomonroq). Normalizatsiya bosqichlari:

1. kichik harf, ortiqcha probel olib tashlanadi;
2. `дж → ж`, `ё → е`, `й → и`, `ъ`/`ь` o'chiriladi.
   ⚠️ Yo'nalish aynan `дж → ж`: teskarisi (`ж → дж`) `Джиззах` ni
   `дджиззах` qilib O'ZINI BUZARDI;
3. ketma-ket takrorlangan harflar bittaga tushiriladi.
   ⚠️ Busiz `Навоий` → `навоии` bo'lib qolardi va bizdagi `Навои`
   bilan mos kelmasdi. Bu SAP dagi eng ko'p uchraydigan farq.

⚠️ Import MAVJUD qatorga TEGMAYDI (`ON CONFLICT DO NOTHING`) —
rahbar qo'lda biriktirgan xodim har importda almashib ketmasin.
Topilmagan filial ham jadvalga **`agent_id = NULL` bilan yoziladi**:
aks holda admin panelda biriktirish uchun ro'yxat bo'sh bo'lardi.

## 4. Qoidalar

Uchala qoida ham FAQAT `op_type = 'sale'` qatorlarga qo'llanadi.

| Kod | Nomi | Shart |
| --- | --- | --- |
| **R1** | Savdo oldidan qo'ng'iroq yo'q | Savdo kuni yoki undan oldingi **N kun** (sukut 3) ichida shu `phone_key` bilan `call_type='sales'` qo'ng'iroq bo'lmagan |
| **R2** | Ikki savdo orasida qo'ng'iroq yo'q | Shu mijozning oldingi savdosi bilan shu savdo orasida birorta qo'ng'iroq yo'q (`call → savdo → call → savdo` ketma-ketligi buzilgan) |
| **R3** | Umuman gaplashilmagan | Mijozda `phone_key` bor, savdolar bor, lekin butun tarixda birorta qo'ng'iroq yo'q — eng qattiq signal |

**Vaqt aniqligi:** savdoda vaqt yo'q, shuning uchun oyna = savdo kuni +
oldingi N kun (jami N+1 kun). Buni ekranda ochiq yozamiz.

### Uch toifa — HECH NARSA YASHIRILMAYDI

Rahbarning qarori (22.08.2026): ro'yxatdan hech bir savdo olib
tashlanmaydi. Buning o'rniga har savdo uch toifadan biriga tushadi va
uchalasining ham soni ekranda turadi.

| Toifa | Qachon | Ma'nosi |
| --- | --- | --- |
| `ok` | Qoida buzilmagan | Savdo oldidan suhbat bo'lgan |
| `suspicious` | Qoida buzilgan, tekshirish MUMKIN edi | Rahbar ko'rib chiqadi |
| `not_checkable` | Tekshirishning iloji yo'q | Shubhali EMAS |

`not_checkable` ga faqat ikki holat tushadi:

- **Umumiy kod** — bitta kod ostida ko'p mijoz: `К00001` («Разовый
  клиент», 152 savdo), `К02370` («Салл сентр», 20), `К03223`
  («Разовый клиент — Тошкент телефон савдо», 2). Bular bitta real
  odam emas, ya'ni «shu mijoz bilan gaplashilganmi?» degan savolning
  o'zi ma'nosiz.
- **Telefon yo'q yoki ishonchsiz** (`phone_key IS NULL`) — chet el
  kodi, soxta raqam va h.k. (`reader.phone_key` izohiga qarang).

⚠️ Ular «toza» deb ham hisoblanmaydi. Alohida son bo'lib turadi:
«N ta savdoni tekshirib bo'lmadi» — bu SAP dagi ma'lumot sifatining
ko'rsatkichi va vaqt o'tib kamayishi kerak.

**Qolgan hammasi nazoratda:** Логистика bo'limi (77 savdo), ichki
kontragentlar (zavod, tashuvchi — ~56 savdo), yetkazib beruvchi
guruhidagi kodlar va qo'ng'iroq yozuvi yo'q bo'limlar (Онлайн савдо,
Зухриддин…) ham tekshiriladi. Ularni oldindan oqlash tizimning
ma'nosini yo'qotardi — oqlash rahbarning ishi, tekshiruv navbatida.

### Filial → xodim: tasdiqlangan xarita

Nom bo'yicha avtomatik moslik 29 filialdan 15 tasini qamraydi
(savdolarning 74.9%). Qolganini **qo'ng'iroq dalili** bilan aniqladik:
o'sha filial mijozlari bilan amalda kim gaplashgan. Rahbar
tasdiqlagan qo'shimcha to'rtta:

| SAP filiali | Xodim | Dalil | Savdo |
| --- | --- | --- | --- |
| Мастона ёйма | Велозапчасть | 31/35 = 88.6% | 79 |
| Кукон метан булими | Метан савдо | 15/15 = 100% | 35 |
| Маркетинг булими | Вело Савдо | 20/20 = 100% | 20 |
| Хусниддин телефон | Телефон савдо | 6/6 = 100% | 6 |

Natija: **19/29 filial = savdolarning 88.4%** xodimga bog'lanadi.

⚠️ `Зухриддин` (34 savdo) ATAYLAB bog'lanmaydi: u bizning xodimimiz
emas, lekin kompaniya bilan ishlaydi. Savdolari «xodimsiz» bo'lib
qoladi va baribir nazoratda turadi.

⚠️ `Направление` (ВЕЛО/МЕТАН/…) xodimni aniqlashga YORDAM BERMAYDI —
tekshirildi: bir filialda yo'nalishga qarab boshqa xodim chiqmaydi.
Yo'nalish allaqachon filial nomida ko'rinadi («Мастона вело дукон» /
«Мастона метан дукон»).

### Har qator TEKSHIRILADIGAN bo'lsin

Rahbar sonni qo'lda qayta hisoblab ko'rmoqchi — bu talab, xohish emas.
Shuning uchun har shubhali savdo yonida DALIL turadi va u ekrandan
ham, Excelga yuklaganda ham chiqadi:

- oxirgi qo'ng'iroq sanasi va kim bilan bo'lgani (yoki «umuman yo'q»);
- savdodan necha kun oldin bo'lgani;
- qaysi qoida buzilgani (R1/R2/R3) va o'sha paytdagi oyna (N kun);
- mijoz kodi, telefoni va filiali — SAP dagi qatorni topish uchun.

Filial → xodim xaritasi ham ochiq: har qatorda avtomatik moslik
dalili ko'rinadi va rahbar uni bir bosishda o'zgartira oladi
(o'shanda `matched_automatically = false` bo'lib qoladi va keyingi
importlar tegmaydi).

## 5. Tekshiruv navbati

Har shubhali savdo ro'yxatga tushadi. Rahbar ikki qarordan birini
qo'yadi:

- **Oqlandi** + sabab (kelib oldi / Telegram / vizit / shartnoma / boshqa)
- **Haqiqatan shubhali** + izoh

Qaror `sale_reviews` da saqlanadi va statistikaga yig'iladi:
«qaysi xodimda oqlanmagan savdo ko'p». Ro'yxat sukut bo'yicha faqat
KO'RILMAGANLARNI ko'rsatadi.

## 6. Import

`POST /sales/import` — multipart fayl. Fayl turi SARLAVHA bo'yicha
avtomatik aniqlanadi (registr / katalog / balans hisoboti), noto'g'ri
fayl aniq xato bilan rad etiladi.

- Idempotent: `sales.external_id` va `sale_partners.code` bo'yicha upsert.
- Sonlar matn ko'rinishida keladi (`"1 950,000"`) — tozalash import
  qatlamida.
- Hisobot: nechta qator o'qildi / yangi / yangilandi / kodi topilmadi /
  filiali biriktirilmagan.
- ⚠️ **Upsert to'ldirilgan maydonni bo'sh qiymat bilan almashtirmaydi**
  (`coalesce`): telefon balans hisobotidan, xodim esa rahbardan
  kelishi mumkin va keyingi katalog importi ularni o'chirmasligi kerak.
- Import tartibi ERKIN. Registr katalogdan oldin yuklansa savdolar
  telefonsiz qoladi — katalog kelganda `backfill_sale_links()` ularni
  tiklaydi. Busiz xato JIMGINA bo'lardi: ro'yxat bo'sh ko'rinardi,
  ya'ni «hammasi joyida» degan ma'no berardi.

**Kod holati (1-bosqich bajarildi):**

| Fayl | Nima qiladi |
| --- | --- |
| `sales/infrastructure/models.py` | 4 jadval |
| `sales/domain/entities.py` | tur xaritasi, filial normalizatsiyasi |
| `sales/application/reader.py` | xlsx o'qish, tur aniqlash, son/sana/telefon tozalash |
| `sales/application/importer.py` | `import_file` / `import_register` / `import_catalog`, `backfill_sale_links` |

Haqiqiy fayllarda o'lchandi (22.08.2026): katalog 3746 kontragent
(94.3% telefonli), registr 2383 operatsiya, shundan 1039 savdo;
kodi topilmagan **0 ta**, xodimga bog'langan **728 (70.1%)**,
`phone_key` olgan savdo 885 (85.2%; qolganining 152 tasi «Разовый
клиент», ular baribir nazoratdan tashqarida). Qayta import: 0 yangi.

## 7. Interfeys

1. **«Savdo nazorati»** bo'limi — shubhali savdolar ro'yxati: sana,
   mijoz, summa, filial/xodim, qaysi qoida buzilgan, oxirgi qo'ng'iroq
   qachon bo'lgan. Filtr (davr, xodim, qoida, holat), Excelga yuklash,
   qarorni shu yerdan qo'yish.
2. **Mijoz kartochkasi** — qo'ng'iroqlar yonida savdolar ham ko'rinadi
   (bitta vaqt chizig'i: qo'ng'iroq → savdo → qo'ng'iroq → savdo).
3. **Telegram** — kunlik xabar: kechagi shubhali savdolar.

## 7.1 Ichki shartnoma (2-bosqich uchun)

Bu bo'lim qurilish jamoasi uchun: interfeys OLDINDAN qotirilgan,
shuning uchun mexanizm, API va ekran bir vaqtda yozilishi mumkin.

### Xizmat: `sales/application/compliance.py`

```python
@dataclass(slots=True)
class SaleVerdict:
    sale_id: UUID
    verdict: str                   # "ok" | "suspicious" | "not_checkable"
    broken_rules: list[str]        # ["R1", "R2", "R3"] — buzilganlari
    skip_reason: str | None        # "generic_code" | "no_phone"
    last_call_at: datetime | None  # savdodan OLDINGI eng yaqin suhbat
    last_call_agent: str | None    # kim gaplashgan
    days_before: int | None        # savdodan necha kun oldin
    previous_sale_on: date | None  # R2: shu mijozning oldingi savdosi
    calls_between: int             # R2: ikki savdo orasidagi suhbatlar
    calls_total: int               # R3: butun tarixda nechta suhbat

@dataclass(slots=True)
class ComplianceFilter:
    since: date | None = None
    until: date | None = None
    agent_ids: list[UUID] | None = None
    branches: list[str] | None = None
    verdict: str | None = None     # ok | suspicious | not_checkable
    review: str | None = None      # new | justified | confirmed
    rule: str | None = None        # R1 | R2 | R3
    search: str | None = None      # mijoz nomi, kodi yoki telefoni
    window_days: int = 3           # sozlamadan keladi

class ComplianceService:
    async def page(f, *, page, page_size, sort, order) -> CompliancePage
    async def summary(f) -> ComplianceSummary   # toifalar + xodimlar kesimi
    async def for_client(phone_key, *, limit) -> list[ClientSale]
```

⚠️ Xulosa HAR SO'ROVDA hisoblanadi (3-bo'limdagi sabab). Bazada faqat
`sale_reviews` — odamning qarori — saqlanadi.

### Sozlama

`SETTINGS_REGISTRY` ga bitta qator: `sales.window_days` (son, sukut 3)
— «Savdo oldidan qo'ng'iroq qidiriladigan kunlar soni».

### Ruxsatlar (yangi)

`sales:read` (ro'yxat va hisobot), `sales:review` (qaror qo'yish),
`sales:import` (fayl yuklash). ADMIN va MANAGER da uchalasi ham bor.
⚠️ SALES va VIEWER rollarida **YO'Q**: bu ro'yxat xodim ustidan
tekshiruv, uni xodimning o'zi ham, televizordagi monitor ham
ko'rmasligi kerak.

### API

| Metod | Yo'l | Ruxsat | Nima qaytaradi |
| --- | --- | --- | --- |
| POST | `/sales/import` | `sales:import` | `ImportReport` (multipart fayl) |
| GET | `/sales/compliance` | `sales:read` | `{items, total, page, page_size}` |
| GET | `/sales/compliance/summary` | `sales:read` | toifalar soni + xodimlar kesimi |
| POST | `/sales/{id}/review` | `sales:review` | qaror qo'yadi |
| GET | `/sales/branches` | `sales:read` | filial → xodim xaritasi + dalil |
| PUT | `/sales/branches/{branch}` | `sales:review` | xodimni qo'lda biriktiradi |

`/sales/compliance` dagi bitta qator (frontend shu nomlarga tayanadi):

```json
{
  "id": "uuid", "occurred_on": "2026-08-14", "external_id": "615830",
  "partner_code": "К02711", "partner_name": "…", "phone": "+998…",
  "phone_key": "901234567", "branch": "Бухоро", "direction": "ВЕЛО",
  "agent_id": "uuid|null", "agent_name": "Бухоро|null",
  "amount": 561.0, "currency": "USD", "amount_usd": 561.0,
  "verdict": "suspicious", "broken_rules": ["R1", "R2"],
  "skip_reason": null,
  "last_call_at": "2026-08-05T14:22:00Z", "last_call_agent": "Бухоро",
  "days_before": 9, "previous_sale_on": "2026-08-12",
  "calls_between": 0, "calls_total": 3,
  "review": { "status": "justified", "reason": "telegram",
              "note": "…", "reviewed_by": "Ism", "reviewed_at": "…" }
}
```

## 8. Bosqichlar

| Bosqich | Nima | Holat |
| --- | --- | --- |
| 1 | Ma'lumot qatlami: jadvallar, import, katalog, filial→xodim | **bajarildi** (`POST /sales/import` — 2-bosqichda) |
| 2 | Qoidalar mexanizmi + tekshiruv navbati + «Savdo nazorati» sahifasi | navbatda |
| 3 | Mijoz kartochkasida savdo tarixi + Telegram xabari | navbatda |

## 9. Ochiq savollar

- 6 oylik savdo eksporti kutilmoqda (rahbar va'da qildi).
- 1 yillik qo'ng'iroq sinxronizatsiyasi hali ishga tushirilmagan —
  busiz «qo'ng'iroq yo'q» degan xulosalarning bir qismi YOLG'ON
  bo'ladi (savdo mijozlarining 38% i bazada yo'q, chunki tarix bir
  oylik).
- ~~`К00001` dan boshqa umumiy kodlar bormi?~~ **Ha:** `К02370`
  («Салл сентр») va `К03223`. Uchalasi `not_checkable` toifasida.
- ~~Valyuta kursi kerak bo'ladimi (summa chegarasi qo'yilsa)?~~
  **KERAK EMAS.** `Хақдор ($)` ustuni hujjat valyutasidan qat'i nazar
  dollar ekvivalentini beradi va u `sales.amount_usd` da saqlanadi.
