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

⚠️ **Fayl nomiga tayanilmaydi** — tur SARLAVHA bo'yicha aniqlanadi.
`клиент харакати общий 01.xlsx` (12 591 qator, 01.07–23.08.2026)
sarlavhasi `savdo kunlik.xlsx` bilan bir xil va xuddi shu registr
sifatida o'qiladi; `Mijozlar ruyxati.xlsx` esa `Workbook3.xlsx` bilan
bir xil (2.2-bo'lim).

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
  `Қарздор ($)` — to'lov/qarz (Входящие платежи da).
- ⚠️ **`($)` ustuni HAR DOIM dollar ekvivalenti**, `(cўм)` esa hujjat
  valyutasidagi summa (UZS da so'm, CNY da yuan, AED da dirham) —
  sarlavha aldamchi. Misol: UZS hujjatda `8,333 $` ↔ `100 000,000` so'm.

#### ⚠️ Summa tuzog'i: eksportning IKKI AVLODI bor

Bitta ustunda ikki xil ma'no keladi va farqni **faqat katak formati**
(`number_format`) ko'rsatadi — fayl nomi ham, sarlavha ham bir xil.
O'lchandi (`Хақдор ($)`, hamma raqam kataklar):

| | ESKI (`savdo kunlik.xlsx`) | YANGI (`клиент харакати общий 01.xlsx`) |
| --- | --- | --- |
| matn kataklar | 1 735 (`"1 950,000"`) | **0** |
| raqam kataklar | 649 | 12 591 |
| raqam formati | **`#,##0`** | **`General`** |
| qiymat misoli | `561000` (aslida 561.000) | `1230.0` (aynan 1230) |

Import qoidasi (`sales/application/reader.py`):

1. **MATN** (`"1 950,000"`) — probel = minglik, vergul = o'nlik → `1950.000`.
2. **RAQAM + `#,##0` + butun son** → **1000 ga bo'linadi**. Bu ESKI
   faylning buzilgan katagi: Excel probelsiz `"561,000"` ni o'zi raqamga
   aylantirib, vergulni minglik ajratkichi deb o'qigan va katakka
   `561000` yozgan. `#,##0` («o'nliksiz butun son») formati aynan
   shundan qolgan — kodda `LegacyThousands` belgisi shu katakka
   qo'yiladi.
3. **Qolgan har qanday RAQAM** (`General`, `#,##0.00`, kasrli) —
   **O'ZGARISHSIZ**. Yangi eksportda qiymat allaqachon to'g'ri.

⚠️ 3-qoida **regressiyadan keyin yozildi**. Ilgari HAR QANDAY raqam
katak 1000 ga bo'linardi va yangi eksport yuklangach summalar 1000
barobar kichrayib ketdi: **146 000 $ → 146 $**, **256 $ → 0**. Yangi
faylda 12 591 ta summa katagining hammasi raqam va hammasi `General`,
ya'ni eski qoida ularning BARCHASINI buzardi.

⚠️ `#,##0` belgisi summa ustunlarida **toza ajratadi**: yangi registrda
u umuman uchramaydi, yangi katalogda esa faqat 3 ta katakda bor va
uchalasi ham `Тел ракам` ustunida — u yerda summa o'qilmaydi. Shuning
uchun belgi katak o'qilayotganda qo'yilsa ham (`_cell_value`), ta'siri
faqat `parse_amount` bilan cheklanadi.

⚠️ Shu sababli registr `values_only` siz o'qiladi: format qiymatning
yonida qolmaydi, katak obyekti kerak. Katak obyektlari saqlanmaydi —
12 591 qatorli faylda narx 0.56 s → 0.65 s.
- Valyuta: USD 1895, UZS 391, CNY 84, AED 9 (Бух.оп da bo'sh — USD deb olinadi).
- **Telefon yo'q, sotuvchi ismi yo'q.** Bog'lanish faqat mijoz kodi orqali.
- ⚠️ Savdolarning **~29% i «Разовый клиент» (К00001)** umumiy kodida —
  real mijoz aniqlanmaydi.

### 2.2 `Workbook3.xlsx` — kontragentlar katalogi

3 746 qator, `Код БП` noyob. `Тел ракам` 94.7% to'ldirilgan, 3 090 noyob
oxirgi-9-raqam. `Код группы`: Клиенты 3 284, qolgani yetkazib beruvchi va
h.k. Kamchilik: 85 ta yetkazib beruvchi ikki marta (Й/П prefiks), 43 ta
`КлентID` bir necha kodda, telefon formatlari 10 xil.

⚠️ Bu yerda ham ikki avlod bor: eski `Workbook3.xlsx` da `Сальдо счета`
va `Лимит кредитования` matn (`"150 000,00000"`) yoki `#,##0` raqam,
yangi `Mijozlar ruyxati.xlsx` da esa oddiy `General`/`#,##0.00` raqam
(`150000`). 2.1-dagi summa qoidasi bu ustunlarga ham bir xil qo'llanadi
(hozircha ular importda o'qilmaydi — kerak bo'lsa tayyor).

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

Import **IKKI BOSQICHLI**: fayl avval hisoblanadi, bazaga esa
foydalanuvchi tasdiqlagandan keyin yoziladi.

```
fayl → POST /sales/import/preview → hisob-kitob modali
     → «Tasdiqlash» → POST /sales/import → natija hisoboti
```

⚠️ **Tasdiqlanmasa bazaga hech narsa yozilmaydi.** Bekor qilinganda
yoki modal yopilganda hech qanday so'rov ketmaydi — 2-bosqichda faqat
brauzerdagi `File` obyekti turadi va tasdiqlashda O'SHA fayl
yuboriladi.

**Nega.** Ilgari fayl tanlanishi bilan bazaga tushardi va foydalanuvchi
nima kirganini FAQAT KEYIN ko'rardi. Ikkita xato jimgina o'tib ketardi:
noto'g'ri fayl (o'tgan haftaning eksporti, boshqa bo'limniki) va
takroriy yuklash. Ikkalasini ham orqaga qaytarish yo'q — savdolar
allaqachon yozilgan bo'lardi.

### 6.1 `POST /sales/import/preview` — hisob-kitob

Multipart fayl, ruxsat `sales:import`, `.xlsx`, 20 MB. **Bazaga hech
narsa yozmaydi** — faqat `SELECT`. Uchala fayl turi uchun ham ishlaydi.

| Maydon | Ma'nosi |
| --- | --- |
| `kind` | `register` / `catalog` / `balance` — sarlavha bo'yicha |
| `filename`, `rows` | fayl nomi va undagi ma'noli qatorlar |
| `date_from`, `date_to` | davr (registr; qolganida `null`) |
| `by_type` | registrda operatsiya turi, katalogda guruh, balansda bo'lim: `{type, label, count, amount_usd}` |
| `by_day` | kun kesimi, faqat registr: `{day, count, amount_usd}` |
| `new_rows` / `existing_rows` | bazada YO'Q va BOR kalitlar (registrda `external_id`, qolganida `code`) |
| `unknown_partners`, `unknown_partner_count` | katalogda topilmagan mijoz kodlari (ro'yxat 20 tagacha) |
| `unmatched_branches` | xodimga biriktirilmagan filiallar — NOMLARI bilan |
| `without_phone` | telefon kaliti olinmaydigan qatorlar — nazorat qilib bo'lmaydi |
| `warnings` | tayyor o'zbekcha jumlalar: sanasiz/summasiz/takroriy qatorlar soni |

⚠️ **`rows` va `new_rows + existing_rows` teng bo'lmasligi mumkin va bu
nosozlik emas**: faylda bir operatsiya raqami ikki qatorda uchraydi
(o'lchandi — 2384 qatorda 2383 noyob). Ekranda ular ham qo'shilmaydi.

⚠️ `existing_rows` fayldagi HAMMA kalit bo'yicha **bitta** `SELECT ...
IN (...)` bilan hisoblanadi. Har qator uchun alohida so'rov 2383 ta
borish-kelish demak edi va hisob-kitob importning o'zidan sekinroq
bo'lardi.

⚠️ Preview `importer._resolve_branches` ni ISHLATMAYDI — o'sha funksiya
topilmagan filialni `sale_branches` ga yozadi. Bu yerda o'sha qoidaning
faqat o'qish qismi takrorlangan (`preview._match_branches`), aks holda
bekor qilingan hisob-kitobdan ham bazada iz qolardi.

### 6.2 `POST /sales/import` — yozish

O'zgarmadi. Tasdiqlashda aynan shu chaqiriladi.

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
| `sales/application/preview.py` | `build_preview` — hisob-kitob, YOZMAYDI |
| `web/src/modules/sales/ImportModal.tsx` | ikki bosqichli modal |

Haqiqiy fayllarda o'lchandi (22.08.2026): katalog 3746 kontragent
(94.3% telefonli), registr 2383 operatsiya, shundan 1039 savdo;
kodi topilmagan **0 ta**, xodimga bog'langan **728 (70.1%)**,
`phone_key` olgan savdo 885 (85.2%; qolganining 152 tasi «Разовый
клиент», ular baribir nazoratdan tashqarida). Qayta import: 0 yangi.

Hisob-kitob o'sha fayllarda (23.08.2026, baza to'la holatda):

| Fayl | `rows` | `new` / `existing` | Nima ko'rsatdi |
| --- | --- | --- | --- |
| `savdo kunlik.xlsx` | 2384 | 0 / 2383 | 10.08–20.08, Продажа 1039, Входящие платежи 999, Закупка 178; 14 filial xodimsiz, 504 qator telefonsiz |
| `Workbook3.xlsx` | 3746 | 0 / 3746 | Клиенты 3284, 323 telefonsiz, 1239 «Неактив» |
| `Workbook1.xlsx` | 2766 | 0 / 2153 | bo'limlar kesimi (`Kod` noyob emas: 2766 qator → 2153 kod); 180 qator telefonsiz |

Uchala so'rovdan keyin ham `sales` da 2383, `sale_partners` da 3746,
`sale_branches` da 29 qator qoldi — ya'ni hisob-kitob bazaga tegmadi.

## 7. Interfeys

1. **«Savdo nazorati»** bo'limi — shubhali savdolar ro'yxati: sana,
   mijoz, summa, filial/xodim, qaysi qoida buzilgan, oxirgi qo'ng'iroq
   qachon bo'lgan. Filtr (davr, xodim, qoida, holat), Excelga yuklash,
   qarorni shu yerdan qo'yish.
2. **Mijoz kartochkasi** — qo'ng'iroqlar yonida savdolar ham ko'rinadi
   (bitta vaqt chizig'i: qo'ng'iroq → savdo → qo'ng'iroq → savdo).
3. **Telegram** — kunlik xabar: kechagi shubhali savdolar.
   ⚠️ Sukut bo'yicha O'CHIQ, tafsiloti 7.3-bo'limda.

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

Kategoriya: yangi `SettingCategory.SALES` («Savdo nazorati»). Mavjud
sakkiztasining birortasi ham mos kelmadi (`scoring` — rubrika
chegaralari, ya'ni butunlay boshqa mavzu), sozlamalar sahifasi esa
kategoriyalarni dinamik chizadi — yangi bo'lim o'zi paydo bo'ladi.

### Ruxsatlar (yangi)

`sales:read` (ro'yxat va hisobot), `sales:review` (qaror qo'yish),
`sales:import` (fayl yuklash). ADMIN va MANAGER da uchalasi ham bor.
⚠️ SALES va VIEWER rollarida **YO'Q**: bu ro'yxat xodim ustidan
tekshiruv, uni xodimning o'zi ham, televizordagi monitor ham
ko'rmasligi kerak.

### API

| Metod | Yo'l | Ruxsat | Nima qaytaradi |
| --- | --- | --- | --- |
| POST | `/sales/import/preview` | `sales:import` | `ImportPreview` — hisob-kitob, **bazaga yozmaydi** (6.1) |
| POST | `/sales/import` | `sales:import` | `ImportReport` (multipart fayl) |
| GET | `/sales/compliance` | `sales:read` | `{items, total, page, page_size, window_days}` |
| GET | `/sales/compliance/summary` | `sales:read` | toifalar soni + xodimlar kesimi |
| POST | `/sales/{id}/review` | `sales:review` | qaror qo'yadi |
| GET | `/sales/branches` | `sales:read` | filial → xodim xaritasi + dalil |
| PUT | `/sales/branches/{branch}` | `sales:review` | xodimni qo'lda biriktiradi |
| GET | `/clients/{key}/sales` | **`sales:read`** | mijoz kartochkasidagi savdo tarixi |

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

### 7.2 Qurilishda aniqlangan tafsilotlar (2-bosqich)

Yuqoridagi nomlar O'ZGARMADI. Quyidagilar shartnomada ochiq
qoldirilgan joylar — mexanizm yozilganda hal qilindi va shu yerga
yozib qo'yildi, chunki ekran ham, Telegram xabari ham (3-bosqich)
shularga tayanadi.

1. **Qo'ng'iroq sanasi mahalliy vaqtda o'qiladi** (`Asia/Tashkent`).
   Savdoda faqat sana bor, qo'ng'iroqda esa UTC dagi vaqt: soat 2 dagi
   suhbat UTC bo'yicha «kechagi» bo'lib qolardi va oyna bir kunga
   siljirdi. Faollik hisoboti bilan bir xil qoida.
2. **R2 oralig'i: oldingi savdo KUNIDAGI suhbat sanalmaydi**
   (`prev < kun ≤ savdo kuni`). U oldingi savdoni oqlagan bo'lishi
   mumkin, ya'ni bitta suhbat ikki savdoni oqlab yuborardi. Shu savdo
   kuni esa KIRADI — savdo vaqti noma'lum.
3. **Bir kunda ikki savdo bo'lsa**, «oldingi savdo» o'sha kunning
   o'zi EMAS, undan oldingi sana. Aks holda har ikkinchi savdo
   avtomatik R2 bo'lib chiqardi.
4. **Faqat `call_type = 'sales'`.** Ichki suhbat R1 ni oqlamaydi;
   `calls_total` ham faqat shu turni sanaydi.
5. **`R3` uchun «butun tarix» — davrsiz**, savdodan keyingi suhbatlar
   ham hisobga olinadi. R3 eng qattiq signal, shuning uchun eng
   ehtiyotkor shaklda.
6. **`/sales/compliance` sukut bo'yicha `review=new`** qaytaradi —
   tekshiruv navbati shu. To'liq ro'yxat: `review=new` |
   `justified` | `confirmed` | **`all`**. `all` ATAYLAB alohida
   qiymat, `review=` ni bo'sh qoldirish emas: rahbarga «hamma
   qarorlarni ko'rsat» kerak bo'ladi (oqlanganlar statistikasi shu
   ro'yxatdan o'qiladi), lekin bu aniq TANLOV bo'lsin — bo'sh
   parametr «foydalanuvchi tanlamadi» degani va o'shanda sukut
   baribir `new`.
7. **`/sales/compliance/summary` `verdict`/`rule`/`review` filtrlarini
   OLMAYDI**: uchala toifaning ham soni ekranda turishi kerak. Davr,
   xodim, filial va qidiruv esa ta'sir qiladi.
8. **Javobga `window_days` qo'shildi** (ro'yxatda ham, hisobotda ham):
   «savdo kuni + oldingi N kun» degani ekranda ochiq yozilishi kerak,
   frontend esa sozlamani alohida so'rab olmasin.
9. **`PUT /sales/branches/{branch}` savdolarni ham ko'chiradi.**
   `backfill_sale_links()` faqat BO'SH `agent_id` ni to'ldiradi, ya'ni
   xato biriktirish tuzatilganda eski savdolar eski xodimda qolib
   ketardi. Filial → xodim xaritasi yagona manba, savdolar unga
   ergashadi.
10. **`POST /sales/import`**: faqat `.xlsx`, eng ko'pi 20 MB, xato —
    422 `sales_bad_file`. `openpyxl` faylni butunlay xotiraga ochadi.
11. **Umumiy kodlar ro'yxati** — `sales/domain/entities.py` dagi
    `GENERIC_PARTNER_CODES` (kirill `К`, lotin `K` emas). Sozlamaga
    chiqarilmadi: yiliga bir marta o'zgaradi, noto'g'ri to'ldirilgan
    sozlama esa butun bo'limni jimgina bo'shatib qo'yardi.

**Haqiqiy ma'lumotdagi natija (22.08.2026, oyna 3 kun, 1 039 savdo,
qo'ng'iroq tarixi atigi 1 oylik):** `ok` 407 (39%), `suspicious` 443
(43%), `not_checkable` 189 (18%). Qoidalar bo'yicha: R1 403, R2 248,
R3 265 (bir savdo bir necha qoidani buzishi mumkin).

⚠️ 43% — ROSTGA O'XSHAMAYDI va bu kutilgan edi: 9-bo'limdagi ochiq
savol aynan shu. Savdo mijozlarining 38% i bazada yo'q, chunki
qo'ng'iroq tarixi bir oylik. Shubhalilarning katta qismi shundan.
**1 yillik sinxronizatsiya ishga tushmaguncha bu ro'yxatni rahbarga
ko'rsatib bo'lmaydi** — u ishonchni yo'qotardi.

⚠️ **Xizmat qatlamini sinash YETARLI EMAS.** Uchidan-uchiga sinovda
oltita endpointdan uchtasi 500 qaytardi — javob `slots=True`
dataclass'dan `vars()` bilan yig'ilardi, unda esa `__dict__` yo'q
(`dataclasses.asdict()` kerak). Xizmat qatlami testlari (861 ta)
yashil turgan edi: bunday xato FAQAT HTTP chegarasida, Pydantic
javobni yig'ayotganda chiqadi. Shuning uchun endi oltala yo'l uchun
ham alohida HTTP testi bor (`test_compliance.py`, «HTTP chegarasi»
bo'limi) va yangi endpoint shusiz qo'shilmaydi.

**Unumdorlik (o'lchandi 22.08.2026, `EXPLAIN ANALYZE`).** Sahifa ham,
hisobot ham BITTA so'rov: `calls` jadvali bir marta skanerlanadi,
qolgani hash join. 1 039 savdo — sahifa 53 ms, hisobot 26 ms;
17 663 savdoda (6 oylik eksportga taqlid) — sahifa 0.4 s, hisobot
0.2 s. ⚠️ Tekshiruv holati filtri (`review`) ATAYLAB xulosa
hisoblangandan KEYIN qo'llanadi: `LEFT JOIN … IS NULL` ni so'rov
boshiga qo'yganda PostgreSQL qatorlar sonini 200 barobar kam
baholab, `evidence` uchun nested loop tanladi va so'rov 0.24 s dan
0.78 s ga chiqdi.

### 7.3 Kunlik Telegram xabari (3-bosqich)

⚠️ **SUKUT BO'YICHA O'CHIQ.** Bu tizimdagi yagona TASHQARIGA
chiqadigan amal: noto'g'ri guruhga tushgan xabarni qaytarib
bo'lmaydi. Shuning uchun rahbar kalitni yoqmaguncha va guruhni
ko'rsatmaguncha birorta xabar ketmaydi.

**Sozlamalar** (`SettingCategory.SALES`):

| Kalit | Tur | Sukut | Ma'nosi |
| --- | --- | --- | --- |
| `sales.digest_enabled` | bool | **`false`** | Bosh kalit |
| `sales.digest_chat_id` | matn | bo'sh | Guruh/chat id. Bo'sh — YUBORILMAYDI (logga ogohlantirish) |
| `sales.digest_min_amount` | son | `0` | Shu summadan ($) past savdolar xabarga kirmaydi |

`sales.digest_min_amount` FAQAT xabarga tegishli — paneldagi
ro'yxat va sonlar o'zgarmaydi. Summasi NOMA'LUM savdo chegaradan
qat'i nazar qoladi: «bilmadim» — «kichik» degani emas.

Panel havolasi `PUBLIC_WEB_URL` (.env) dan olinadi. Bo'sh bo'lsa
havola xabarga umuman qo'shilmaydi — ishlamaydigan `localhost`
havolasi butun xabarga ishonchni tushirardi.

**Xabar** (o'zbekcha, Telegram HTML): sarlavhada oxirgi import
qilingan kun; uchala toifa soni; xodimlar kesimi (eng ko'p
shubhalisi birinchi, beshtadan keyin «va yana N ta»); eng katta
3–5 shubhali savdo dalili bilan (qaysi qoida, oxirgi suhbat
qachon); oxirida panel havolasi va «bu ro'yxat AYBLAMAYDI» jumlasi.

⚠️ **4096 belgi — Telegram chegarasi.** Undan uzun xabar
yuborilmaydi (400 xato), ya'ni «uzun bo'lsa kesilar» degan umid ish
bermaydi — xabar BUTUNLAY yo'qolardi. Matn shuning uchun sig'guncha
qisqaradi: avval savdolar 5→3, keyin xodimlar 5→3→1→0, eng oxirida
qator bo'yicha kesish. Sonlar va yakundagi jumla hech qachon
tushmaydi.

**Qachon:** tungi vazifaning (`pipeline.nightly`) UCHINCHI bosqichi,
sinxronizatsiyadan KEYIN. Alohida beat yozuviga chiqarilmadi: o'shanda
ikki vazifaning tartibi vaqtga tayanardi va sinxronizatsiya cho'zilsa
xabar eskirgan ma'lumot bilan chiqib ketardi.

**Takrorlanmaslik:** `sale_digests` jadvali (audit + suv belgisi).
Yangi savdo importi bo'lmagan bo'lsa (`max(sales.imported_at)`
o'zgarmagan) xabar YUBORILMAYDI — beat jadvali kafolat emas
(`worker.py` dagi izoh), takroriy xabar esa shovqin.

**Qo'lda sinash:** `POST /sales/digest/test` (ruxsat `sales:review`,
`sales:read` emas — bu tashqariga xabar yuboradi). `digest_enabled`
ni TEKSHIRMAYDI: tugmaning ma'nosi kalitni yoqishdan oldin matnni
ko'rish. Javobda yuborilgan matn ham qaytadi. Yozuv `kind='test'`
bo'lib tushadi va kechasi keladigan haqiqiy xabarga ta'sir qilmaydi.

⚠️ **Bot orqali emas, backend'dan to'g'ridan-to'g'ri.** Guruh
so'rovnomalari navbat orqali ketadi (bot `pending-surveys` ni
so'rab turadi), lekin u mexanizm so'rovnomaga moslangan (reyestr,
hisoblagich, xabarni keyin o'chirish). Hal qiluvchi sabab boshqa:
«Sinov xabari» tugmasi DARHOL javob kutadi — «ketdimi, matni
qanaqa». Navbat orqali bunga javob berib bo'lmaydi. Token o'sha-o'sha
(`telegram.bot_token`), guruhlar o'sha-o'sha (`telegram_groups` —
bot chiqarilgan guruhga yuborilmaydi), yangi maxfiy kalit ham,
yangi navbat ham qo'shilmadi.

## 8. Bosqichlar

| Bosqich | Nima | Holat |
| --- | --- | --- |
| 1 | Ma'lumot qatlami: jadvallar, import, katalog, filial→xodim | **bajarildi** |
| 2 | Qoidalar mexanizmi + tekshiruv navbati + API | **bajarildi** (`compliance.py`, `branches.py`, `review.py`, `presentation/router.py`); «Savdo nazorati» sahifasi — frontendda |
| 3 | Mijoz kartochkasida savdo tarixi + Telegram xabari | **bajarildi**: Telegram (`digest.py`, `infrastructure/telegram.py`, `sale_digests`, `POST /sales/digest/test`) — ⚠️ sukut bo'yicha O'CHIQ; mijoz kartochkasi (`GET /clients/{key}/sales`, aralash vaqt chizig'i) |

### Qolgan ish (4-bosqich uchun ro'yxat)

- **Telegram sozlamalari ekranda yo'q.** Backend tayyor
  (`sales.digest_enabled`, `sales.digest_chat_id`, `sales.digest_min_amount`,
  `POST /sales/digest/test`), lekin Sozlamalar sahifasida ularni yoqadigan
  va «Sinov xabari» yuboradigan qism hali yozilmagan.
- **`PUBLIC_WEB_URL` bo'sh.** Xabardagi «Panelda ochish» havolasi shu
  sababli qo'shilmayapti — ishlamaydigan `localhost` havolasini
  yuborgandan ko'ra yo'qligi yaxshi. Ishga tushirishdan oldin to'ldirilsin.
- **5 ta MoyZvonki hisobi xodimga bog'lanmagan** — 3 oylik
  sinxronizatsiyada 2 456 ta qo'ng'iroq shu sababli hisobga tushmadi
  (`bonvivelomoizvonki77@mail.ru`, `moizvonkibonvivelo33@mail.ru`,
  `bonvivelomoizvonki22@mail.ru`, `moizvonkibonvivelo79@mail.ru`,
  `bonvivelo@gmail.com`). «Xodimlar» bo'limida `external_id` to'ldirilsa
  yopiladi.
- **Eski qo'ng'iroqlarni baholash navbatidan chiqarish.** 3 oylik
  sinxronizatsiyadan keyin 24 154 ta qo'ng'iroq AI baholashga yaroqli
  bo'lib qoldi va tungi vazifa ularni har kecha 2 000 tadan navbatga
  qo'yadi. Rahbarning qarori (22.08.2026): **hozir baholash shart emas**.
  Chora hali QO'LLANMAGAN — 22.07.2026 dan oldingi, audiosi bor
  qo'ng'iroqlar `status='skipped'` ga o'tkazilishi kerak (qaytarish
  mumkin bo'lgan usulda; undan keyingi kunlar sinxronizatsiyagacha ham
  bazada bor edi va ularga tegilmaydi).

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
