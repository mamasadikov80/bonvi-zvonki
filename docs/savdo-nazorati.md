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
- `Номер операции` — amalda noyob (1 juft istisno) → **idempotentlik kaliti**.
- `Дата регистрации` — matn `dd.mm.yyyy`, **VAQTI YO'Q** (faqat sana).
- `Хақдор ($)` — savdo summasi (Продажа qatorlarida to'ladi),
  `Қарздор ($)` — to'lov/qarz (Входящие платежи da). Sonlar **matn**:
  `"1 950,000"` (probel = minglik, vergul = o'nlik).
- Valyuta: USD 1895, UZS 391, CNY 84, AED 9.
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
| `op_type` | varchar(32) | `sale`, `payment_in`, `purchase`, `payment_out`, `sale_cancel`, `accounting` |
| `occurred_on` | date | ⚠️ faqat sana, vaqti yo'q |
| `branch` | varchar(128) null | `Подразделение` |
| `direction` | varchar(64) null | `Направление` (ВЕЛО, МЕТАН…) |
| `partner_code` | varchar(16) INDEX | |
| `partner_name` | varchar(255) | import paytidagi nusxa |
| `amount` | numeric(18,3) | `Хақдор` yoki `Қарздор` — turiga qarab |
| `currency` | varchar(8) | USD / UZS / CNY / AED |
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

Avtomatik moslash: nom normalizatsiyasi (kichik harf, `й→и`, `ж→дж`,
ortiqcha probel) → `agents.full_name`. Qolgani admin panelda qo'lda.

## 4. Qoidalar

Uchala qoida ham FAQAT `op_type = 'sale'` qatorlarga qo'llanadi.

| Kod | Nomi | Shart |
| --- | --- | --- |
| **R1** | Savdo oldidan qo'ng'iroq yo'q | Savdo kuni yoki undan oldingi **N kun** (sukut 3) ichida shu `phone_key` bilan `call_type='sales'` qo'ng'iroq bo'lmagan |
| **R2** | Ikki savdo orasida qo'ng'iroq yo'q | Shu mijozning oldingi savdosi bilan shu savdo orasida birorta qo'ng'iroq yo'q (`call → savdo → call → savdo` ketma-ketligi buzilgan) |
| **R3** | Umuman gaplashilmagan | Mijozda `phone_key` bor, savdolar bor, lekin butun tarixda birorta qo'ng'iroq yo'q — eng qattiq signal |

**Vaqt aniqligi:** savdoda vaqt yo'q, shuning uchun oyna = savdo kuni +
oldingi N kun (jami N+1 kun). Buni ekranda ochiq yozamiz.

**Istisnolar (avtomatik):**
- `partner_code = 'К00001'` («Разовый клиент») — nazorat qilinmaydi,
  bu kelib oladigan bir martalik mijoz.
- Kodda telefon bo'lmasa (`phone_key IS NULL`) — `unknown` toifasi,
  shubhali emas: tekshirishning iloji yo'q.
- Yetkazib beruvchilar (`Код группы != 'Клиенты'`) — nazoratdan tashqarida.

**Qo'ng'iroq yozuvi yo'q bo'limlar** (Логистика, Мастона ёйма, Маркетинг
булими, Онлайн савдо…) — **shubhali hisoblanadi** (rahbarning qarori).
Sabab: bu bo'limlarni MoyZvonki'ga ulashga turtki bo'lsin.

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

## 7. Interfeys

1. **«Savdo nazorati»** bo'limi — shubhali savdolar ro'yxati: sana,
   mijoz, summa, filial/xodim, qaysi qoida buzilgan, oxirgi qo'ng'iroq
   qachon bo'lgan. Filtr (davr, xodim, qoida, holat), Excelga yuklash,
   qarorni shu yerdan qo'yish.
2. **Mijoz kartochkasi** — qo'ng'iroqlar yonida savdolar ham ko'rinadi
   (bitta vaqt chizig'i: qo'ng'iroq → savdo → qo'ng'iroq → savdo).
3. **Telegram** — kunlik xabar: kechagi shubhali savdolar.

## 8. Bosqichlar

| Bosqich | Nima | Holat |
| --- | --- | --- |
| 1 | Ma'lumot qatlami: jadvallar, import, katalog, filial→xodim | ishlanmoqda |
| 2 | Qoidalar mexanizmi + tekshiruv navbati + «Savdo nazorati» sahifasi | navbatda |
| 3 | Mijoz kartochkasida savdo tarixi + Telegram xabari | navbatda |

## 9. Ochiq savollar

- 6 oylik savdo eksporti kutilmoqda (foydalanuvchi va'da qildi).
- `К00001` dan boshqa umumiy kodlar bormi?
- Valyuta kursi kerak bo'ladimi (summa chegarasi qo'yilsa)?
