# BonviZvonki — Savdo xodimlarini baholash platformasi

**Hujjat versiyasi:** 1.1
**Sana:** 2026-08-15
**Holat:** Tahlil + reja (implementatsiya boshlanmagan)

> **v1.1 o'zgarishlari (buyurtmachi qarorlari asosida):**
> 1. Client baholash — **gibrid model tasdiqlandi** (guruhda chaqiruv, shaxsiyda baho)
> 2. Ma'lumot lokalizatsiyasi **cheklov emas** → chet el API'lari ochiq, ustuvorlik: **sifat + arzonlik**
> 3. **SAP/CRM integratsiyasi qamrovdan chiqarildi** → savdo natijasi faqat transkriptdan aniqlanadi
> 4. Arzonroq ASR variantlari qo'shildi (Groq Whisper $0.04/soat) va **"maksimal tejamkorlik"** stsenariysi hisoblandi

---

## 0. Qisqacha xulosa (TL;DR)

**Nima quramiz:** Har bir qo'ng'iroqni avtomatik transkripsiya qilib, AI orqali rubrika bo'yicha baholaydigan, buni client'lar qo'yadigan reyting bilan birlashtirib, menejerlar va boss uchun bitta dashboardda ko'rsatadigan ichki platforma.

**Asosiy 5 ta qaror (tavsiya):**

| # | Qaror | Tavsiya | Nega |
|---|---|---|---|
| 1 | **Client baholash usuli** | Guruhda **e'lon + tugma**, baho esa **bot bilan shaxsiy chatda** (anonim) | Guruhda ochiq baho = yolg'on baho. Savdo xodimi guruhda o'tirganda client hech qachon rostini yozmaydi. Guruh — faqat "yetkazish kanali", baho — shaxsiy |
| 2 | **Baholash chastotasi** | **Har 14 kunda bir marta** (rolling, client'lar bo'yicha taqsimlangan) + yirik bitimlardan keyin event-trigger | Siz to'g'ri o'ylagansiz: har call'dan keyin so'rash = shovqin va bitta yomon kayfiyat sababli reyting qulashi |
| 3 | **ASR (nutqni matnga)** | **Benchmark hal qiladi.** Narx zinapoyasi: Groq Whisper turbo $0.04/soat → Groq large-v3 $0.111 → ElevenLabs Scribe $0.22 → Kotib $1.44. **Benchmarkdan o'tgan eng arzoni tanlanadi** | Farq 5–36×. Lekin ASR sifati past bo'lsa keyingi hamma narsa qiymatsiz — shuning uchun "arzon" faqat WER < 20% shartida |
| 4 | **LLM (baholovchi)** | **Claude Haiku 4.5** asosiy (arzon) + **Sonnet 5/Opus 5** kalibratsiya va nizoli holatlar uchun. Batch API + prompt caching | Haiku + batch + cache = **$54/oy**. Sifat gold set bilan tekshiriladi; yetmasa Sonnet'ga ko'tariladi ($163/oy) |
| 5 | **Sotib olish vs qurish** | **Qurish** (build) | Tayyor platforma taxminan **$5,000+/oy**, o'zimizniki **$250–700/oy**. Dev xarajati 4–6 oyda qoplanadi |

**Taxminiy oylik xarajat:** **$323/oy** (maksimal tejamkorlik) – **$554/oy** (tavsiya) – **$708/oy** (sifat ustuvor)
≈ **4.0–8.9 mln so'm/oy** → 15 xodim uchun **$22–47/xodim/oy**. Optimizatsiyalar bilan tavsiya variant **$430/oy** gacha tushadi.
**Taxminiy ishlab chiqish muddati:** **14 hafta** (5 bosqich), MVP — 6-haftada
**Eng katta risk:** O'zbek tili + dialekt + kod-almashinuv (uz/ru aralash) da ASR sifati. Shuning uchun 1-bosqich = benchmark.

---

## 0.1 ✅ Tasdiqlangan qarorlar (buyurtmachi bilan kelishilgan)

| # | Qaror | Holat | Ta'siri |
|---|---|---|---|
| **D1** | **Client baholash = gibrid model.** Bot guruhga tugmali chaqiruv tashlaydi → client tugmani bosib **shaxsiy chatda** anonim baho qo'yadi | ✅ Tasdiqlangan | 2-bo'lim spetsifikatsiyaga aylandi, muqobillar olib tashlandi |
| **D2** | **Ma'lumot lokalizatsiyasi cheklov emas.** Chet el API'lari (Groq, ElevenLabs, Anthropic, Google) ochiq. Ustuvorlik: **sifat + natija, keyin arzonlik** | ✅ Tasdiqlangan | Eng arzon global provayderlar ishlatiladi. Huquqiy risk 11.1-bo'limda qayd etilgan, lekin bloklamaydi |
| **D3** | **SAP/CRM integratsiyasi YO'Q.** Savdo natijasi faqat transkriptdan aniqlanadi | ✅ Tasdiqlangan | Blok D qayta yozildi (fakt emas, **signal**). SAP ulash qamrovdan chiqdi — ~2 hafta ish tejaladi |

> **D2 bo'yicha ochiq eslatma:** Men huquqiy riskni (ovoz yozuvi = biometrik ma'lumot deb talqin qilinishi ehtimoli, ZRU-547) ko'rsatib o'tdim va siz uni ustuvor emas deb belgiladingiz. Bu sizning qaroringiz — men shunga muvofiq eng arzon global stack bilan davom etaman. Arxitekturada ASR/LLM provayderi **almashtiriladigan qilib** (adapter pattern) quriladi, ya'ni ertaga qonun o'zgarsa yoki auditor talab qilsa, 1–2 kunda mahalliy provayderga o'tish mumkin. Bu qo'shimcha xarajat talab qilmaydi — shunchaki yaxshi arxitektura.

---

## 1. Hajm modeli (hamma hisob-kitob shu asosda)

Bu raqamlarni tasdiqlashingiz kerak — pastda "Ochiq savollar" bo'limida so'ralgan.

| Parametr | Min | **Baza** | Max |
|---|---|---|---|
| Savdo xodimlari | 12 | **15** | 18 |
| Qo'ng'iroq / xodim / kun | 25 | **30** | 40 |
| O'rtacha davomiylik | 6 min | **8 min** | 15 min |
| Ish kunlari / oy | 22 | **26** | 26 |

**Baza stsenariy:**
- Kuniga: 450 qo'ng'iroq = 3,600 minut = **60 soat audio/kun**
- Oyiga: 11,700 qo'ng'iroq = 93,600 minut = **1,560 soat audio/oy**
- Yiliga: ~140,000 qo'ng'iroq = **~18,700 soat audio/yil**

> ⚠️ **Bu juda katta hajm.** 1,560 soat/oy — bu O'zbekistondagi o'rtacha kontakt-markazdan kam emas. Har bir dollar/soat = $1,560/oy. Shuning uchun ASR narxi platformaning **eng katta xarajat drayveri** — LLM emas. Bu qaror birinchi navbatda hal qilinishi kerak.

---

## 2. Client baholash tizimi — chuqur tahlil

Bu loyihaning **eng nozik** qismi. Texnikasi oson, dizayni qiyin.

### 2.1 Asosiy muammo: kim, kimni, qachon baholaydi?

Telefon orqali savdoda client reytingi to'plashning 4 ta fundamental muammosi bor:

| Muammo | Tavsif | Sizning holatda |
|---|---|---|
| **A. Attribusiya** | Qaysi xodim uchun baho? | ✅ **Hal qilingan** — har guruhda 1 client + 1 xodim. Bu katta ustunlik, ko'p kompaniyalarda yo'q |
| **B. Anonimlik** | Xodim ko'rib turgan joyda client rostini aytmaydi | ❌ **Hal qilinmagan** — sizning 3-variantingizning asosiy zaifligi |
| **C. Response rate** | Client javob bermaydi | ⚠️ Telegram guruhi bu muammoni 60-70% hal qiladi |
| **D. Bias / gaming** | Bir client hammaga 3 qo'yadi, boshqasi hammaga 5. Xodim client'dan "5 qo'ying" deb so'raydi | ❌ **Hal qilinmagan** — statistik normalizatsiya kerak |

### 2.2 Sizning 3 variantingiz — ochiq tahlil

#### Variant 1: SMS orqali link (Eskiz.uz)
- **Narx:** 95 so'm/SMS (oddiy), 175 so'm/SMS (reklama tarifi). Agar 500 client × 2 hafta = 1,000 SMS/oy ≈ 95,000 so'm/oy. Arzon.
- **Response rate:** Global benchmark bo'yicha SMS + link (one-way) = **6–15%**. B2B'da yanada past.
- **Muammo:** Sizning client'laringiz do'konda turishadi, SMS'ni ochib link bosishga vaqt yo'q. Siz buni o'zingiz to'g'ri aytdingiz.
- **Xulosa:** ❌ **Asosiy kanal sifatida yaramaydi.** Zaxira sifatida — Telegram'i yo'q clientlar uchun (~10%) saqlanadi.

#### Variant 2: Alohida bot orqali so'rovnoma
- **Muammo:** Client alohida botni ochishi, /start bosishi kerak. Bu yangi "ish" — qilmaydi.
- **Response rate:** Cold bot = **5–10%**.
- **Xulosa:** ❌ Alohida kanal sifatida yaramaydi. **Lekin** — quyidagi gibridda "shaxsiy baholash oynasi" sifatida ishlatiladi.

#### Variant 3: Mavjud guruhga so'rovnoma (sizning asosiy g'oyangiz)
- **Kuchli tomon:** ✅✅ Client bu guruhni **har kuni ochadi** (savdo hisobotlari kelyapti). Kanal jonli. Bu global benchmark'larda WhatsApp survey ~40–55% response berishining aynan sababi — odam allaqachon o'sha yerda.
- **Zaif tomon:** ❌❌ **Guruhda savdo xodimi o'tiribdi.** Client 3 ball qo'ysa, ertaga o'sha xodim bilan gaplashishi kerak. Bu **social desirability bias** — ilmiy adabiyotda yaxshi hujjatlashtirilgan. Natija: hammaga 5, ma'lumot nolga teng.
- **Telegram `sendPoll` bilan:** `is_anonymous: false` qilsangiz — kim nima qo'yganini hamma ko'radi (yomon). `is_anonymous: true` qilsangiz — **siz ham kim qo'yganini bilmaysiz**, ya'ni attribusiya yo'qoladi (guruhda 3-5 kishi bor: client, xodim, menejerlar). Ikkalasi ham ishlamaydi.

> **Bu Telegram Poll API'ning tub cheklovi.** `poll_answer` update faqat `is_anonymous: false` bo'lganda `user_id` beradi — ya'ni anonimlik va attribusiya bir vaqtda mumkin emas.

### 2.3 ✅ TASDIQLANGAN YECHIM (D1): Gibrid model — "Guruhda chaqiruv, shaxsiyda baho"

> Bu bo'lim endi **tavsiya emas, spetsifikatsiya**. 4-bosqichda aynan shu qurib chiqiladi.

```
┌─────────────────────────────────────────────────────────────┐
│  TELEGRAM GURUH (client + xodim + 2 menejer)                │
│                                                              │
│  🤖 Bot:                                                     │
│  "Assalomu alaykum, Akmal aka! 👋                            │
│   So'nggi 2 haftadagi ishimizni baholab bering —             │
│   bu bizga sifatni oshirishga yordam beradi.                 │
│   ⏱ 30 soniya vaqtingizni oladi.                            │
│                                                              │
│   🔒 Javobingiz maxfiy — guruhda hech kim ko'rmaydi."        │
│                                                              │
│   [ ⭐ Baholashni boshlash ]  ← inline button, deep-link     │
└──────────────────────────┬──────────────────────────────────┘
                           │ t.me/ZvonkiBot?start=srv_<token>
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  BOT BILAN SHAXSIY CHAT (faqat client ko'radi)              │
│                                                              │
│  1️⃣ Umumiy qoniqish?   ⭐⭐⭐⭐⭐  (1–5)                       │
│  2️⃣ Muammolaringizni hal qildimi?  [Ha] [Qisman] [Yo'q]     │
│  3️⃣ Izoh qoldirasizmi? (ixtiyoriy, matn)                    │
│                                                              │
│  ✅ "Rahmat! Javobingiz faqat rahbariyatga ko'rinadi."       │
└─────────────────────────────────────────────────────────────┘
```

**Nega bu ishlaydi:**

| Talab | Qanday hal qilinadi |
|---|---|
| Client kanalni tekshiradi | Chaqiruv guruhda — u har kuni ochadigan joyda |
| Attribusiya aniq | `token` → `(client_id, agent_id, period)` bazada saqlangan |
| Anonimlik | Baho shaxsiy chatda, guruhga hech narsa yozilmaydi |
| Xodim ta'sir qilolmaydi | Xodim natijani ko'rmaydi (dashboard'da faqat o'zining o'rtacha reytingi, izohlarsiz) |
| Past friksiya | 2 ta tugma bosish, 30 soniya |

**Texnik nozik nuqta:** Deep-link ishlashi uchun client bot bilan kamida bir marta `/start` qilgan bo'lishi kerak. Birinchi bosishda Telegram avtomatik `/start srv_<token>` yuboradi va chat ochiladi — ya'ni **bir bosish yetarli**. Agar client botni bloklagan bo'lsa → SMS fallback (Eskiz).

### 2.4 So'rovnoma dizayni

**Qoida: 3 savoldan oshmasin.** Har qo'shimcha savol response rate'ni ~15% tushiradi.

| # | Savol | Turi | Majburiy | Nima o'lchaydi |
|---|---|---|---|---|
| 1 | "Oxirgi 2 haftada [Xodim ismi] bilan ishlashdan qanchalik roziligingiz?" | 1–5 yulduz | ✅ | **CSAT** — asosiy metrika |
| 2 | "Savollaringizga to'liq javob oldingizmi?" | Ha / Qisman / Yo'q | ✅ | **Resolution rate** |
| 3 | "Nimani yaxshilashimiz mumkin?" | Erkin matn | ❌ | Sifat signali + AI orqali tahlil |

**Qo'shimcha (choraklik, alohida):**
- **NPS:** "Bizni hamkasbingizga tavsiya qilasizmi? (0–10)" — bu har 2 haftada emas, 3 oyda bir marta.

**Muhim:** Savolni **xodim ismi bilan** shaxsiylashtiring ("Sardor bilan ishlash") — mavhum "bizning kompaniya" emas. Bu attribusiyani client miyasida ham aniqlashtiradi.

### 2.5 Kadans (chastota) — statistik asos

**Tavsiya: har 14 kunda, lekin client'lar bo'yicha taqsimlangan (staggered).**

```
Hafta 1:  A guruhi (client'larning 1/2 qismi) → so'rovnoma
Hafta 2:  B guruhi (qolgan 1/2)              → so'rovnoma
Hafta 3:  A guruhi
Hafta 4:  B guruhi
```

**Nega taqsimlangan:**
- Dashboardda **har hafta** yangi ma'lumot keladi (hammasi bir kunda emas)
- Trend chizig'i silliq bo'ladi
- Bot bir kunda 500 ta xabar yubormaydi (Telegram rate limit: ~30 msg/sek, lekin guruhga 20 msg/min)

**Qo'shimcha trigger'lar:**
| Trigger | Qachon |
|---|---|
| Yirik bitim yopildi | Bitim summasi > X so'm bo'lsa, 24 soat ichida |
| Yangi client | 3-chi qo'ng'iroqdan keyin (birinchi taassurot) |
| AI red-flag | AI 40 balldan past baholagan call'dan keyin 48 soatda (menejer tasdig'i bilan) |
| Suppression | Oxirgi 10 kunda so'ralgan bo'lsa — **so'ramaslik** |

### 2.6 Bias va gaming'ga qarshi statistik dizayn

Bu bo'lim ko'pincha e'tibordan chetda qoladi va butun tizimni foydasiz qiladi.

#### a) Client severity normalizatsiyasi
Ba'zi client'lar tabiatan hammaga 3 qo'yadi, ba'zilari hammaga 5. Xom o'rtacha noto'g'ri.

**Yechim:** Har client uchun `client_bias` hisoblang:
```
client_bias_i = mean(client i ning barcha baholari) − mean(barcha baholar)
adjusted_score = raw_score − client_bias_i
```
Bu **mixed-effects model** ning soddalashtirilgan ko'rinishi. Client kamida 3 marta baho bergandan keyin qo'llanadi.

#### b) Minimal namuna (sample size)
**Qoida: xodimning client-reytingi dashboardda `n < 5` bo'lsa ko'rsatilmasin.** O'rniga "Ma'lumot yig'ilmoqda (3/5)" deb yozilsin.

Ishonch oralig'i (Wilson interval) ham ko'rsatilsin: `4.2 ★ (n=12, ±0.4)`.

#### c) Gaming'ni aniqlash
Xodim client'ga "iltimos 5 qo'ying" deyishi mumkin. Buni qanday ushlash:

| Signal | Talqin |
|---|---|
| Client reytingi yuqori (4.8) + AI bahosi past (55) | 🚩 **Divergensiya** — tekshirish kerak |
| Xodimning barcha reytinglari aynan 5.0, dispersiya = 0 | 🚩 Tabiiy emas |
| Baho qo'yish vaqti so'rovnomadan < 60 soniya, hammasi ketma-ket | 🚩 Xodim client telefonidan qo'ygan bo'lishi mumkin |
| Response rate 100% (odatda 40–60%) | 🚩 Majburlash belgisi |

Dashboardda alohida **"Divergensiya"** paneli: AI bahosi va client bahosi orasidagi farq eng katta xodimlar.

#### d) Kutilayotgan response rate
Realistik prognoz: **35–55%**. Telegram guruhi kuchli kanal, lekin B2B'da 100% hech qachon bo'lmaydi. 500 client × 2 haftada 1 marta × 45% = **~110 baho/hafta**. Bu 15 xodim uchun yetarli statistika.

---

## 3. AI baholash tizimi

### 3.1 Umumiy arxitektura (pipeline)

```
┌──────────────┐
│  MoyZvonki   │  webhook: call.finish
│  (Android)   │──────────────┐
└──────────────┘              │
                              ▼
                    ┌───────────────────┐
                    │  Ingest Service   │  calls.list + recording URL
                    │  (FastAPI)        │  → yuklab olish
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │  Object Storage   │  S3-compatible (MinIO / AWS S3)
                    │  raw audio (m4a)  │  🔴 30 kunlik MoyZvonki limitidan oldin
                    └─────────┬─────────┘
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
        ┌────────────────────┐  ┌────────────────────┐
        │  ASR Worker        │  │  Audio Feature     │
        │  • transkript      │  │  Worker            │
        │  • diarizatsiya    │  │  • RMS/loudness    │
        │  • timestamp       │  │  • F0 (pitch)      │
        │  • til aniqlash    │  │  • speech rate     │
        └─────────┬──────────┘  │  • pauzalar        │
                  │             │  • overlap/talqin  │
                  │             └─────────┬──────────┘
                  └──────────┬────────────┘
                             ▼
                  ┌────────────────────────┐
                  │  LLM Scoring Worker    │  Claude Sonnet 5
                  │  (Batch API, tunda)    │  + rubrika (cached)
                  │  → structured JSON     │  + prosodika xulosasi
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐         ┌──────────────────┐
                  │  PostgreSQL            │◄────────│  Telegram Bot    │
                  │  + pgvector (qidiruv)  │  client │  (so'rovnoma)    │
                  └───────────┬────────────┘  bahosi └──────────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │  Backend API + Dashboard│  Next.js
                  └────────────────────────┘
```

### 3.2 ASR (nutqni matnga o'girish) — eng muhim qaror

**Bu platformaning sifat va narx nuqtai nazaridan eng kritik komponenti.**

#### Narx zinapoyasi (arzondan qimmatga) — 1,560 soat/oy uchun

| # | Xizmat | $/soat | **$/oy** | so'm/oy | O'zbek sifati (taxmin) | Diarizatsiya |
|---|---|---|---|---|---|---|
| 1 | **Groq `whisper-large-v3-turbo`** | **$0.04** | **$62** | 780 ming | ⚠️ Past (~25–35% WER kutilmoqda) | ❌ pyannote kerak |
| 2 | **Self-hosted Whisper large-v3** (ijaraga GPU) | ~$0.05 | ~$80 | 1 mln | ⚠️ O'rtacha (~20–28%) | ❌ pyannote kerak |
| 3 | **Gemini 3.x Flash** (to'g'ridan audio) | ~$0.086 | $135 | 1.7 mln | ⚠️ Scribe'dan past | ⚠️ Ishonchsiz |
| 4 | **Groq `whisper-large-v3`** | **$0.111** | **$173** | 2.2 mln | ⚠️ O'rtacha (~20–25%) | ❌ pyannote kerak |
| 5 | **ElevenLabs Scribe v2** | **$0.22** | **$343** | 4.3 mln | ✅ Yaxshi (hujjatlarda 10–20% WER) | ✅ **Ichida** (32 spiker) |
| 6 | **Deepgram Nova-3** (+diariz.) | $0.378 | $590 | 7.4 mln | ❌ O'zbek yo'q | ✅ |
| 7 | **Kotib STT** (5 so'm/sek) | **$1.44** | **$2,246** | **28 mln** | ✅✅ Eng yaxshi (UZ dialektlarga fine-tune) | ❌ |
| 8 | **Muxlisa AI** (Uzinfocom) | ? | ? | ? | ✅✅ Davlat loyihasi, dialekt+aralash | ? |

**Diarizatsiya qo'shimchasi:** 1, 2, 4, 7-variantlarda `pyannote.audio` alohida kerak → **+$70–90/oy** GPU. Ya'ni Groq turbo real narxi ≈ **$62 + $80 = $142/oy**, ElevenLabs Scribe esa $343 (diarizatsiya ichida).

#### 🔑 Muhim ogohlantirish: bu yerda "arzon" tuzoq bo'lishi mumkin

```
ASR sifati past  →  transkript buzuq  →  LLM noto'g'ri baholaydi
                 →  menejerlar ishonmaydi  →  butun platforma foydasiz
                 →  $18,000 dev xarajati kuyadi
```

**Farq:** Groq turbo ($142/oy) vs ElevenLabs Scribe ($343/oy) = **$201/oy = 2.5 mln so'm/oy**.
Bu 15 xodimni noto'g'ri baholash riskiga arzimaydi. **Shuning uchun qoida:**

> **Benchmarkdan o'tgan ENG ARZON variantni oling.** WER < 20% shartini bajarmagan variant qanchalik arzon bo'lsa ham tanlanmasin.

#### Nima kutish mumkin (mening bahom, benchmark tasdiqlashi kerak)

| Variant | Ehtimoliy natija |
|---|---|
| Groq turbo | ❌ Ehtimol o'tmaydi. Turbo dekoderi 32→4 qatlamga qisqartirilgan; kam resursli tillarda (o'zbek) aniqlik sezilarli tushadi |
| Groq large-v3 | ⚠️ Chegarada. Sof o'zbekda o'tishi mumkin, uz/ru aralashda qiyin |
| ElevenLabs Scribe v2 | ✅ Eng ehtimolli g'olib. Rasman o'zbek qo'llab-quvvatlanadi, diarizatsiya ichida, narxi maqbul |
| Kotib | ✅✅ Sifat bo'yicha eng yaxshi, lekin **36× qimmat**. Faqat boshqa hech biri o'tmasa |

**Amaliy tavsiya:** benchmarkda **1, 4, 5, 7-variantlarni** sinang (Gemini va Deepgram'ni o'tkazib yuboring — biri diarizatsiyasiz, ikkinchisi o'zbeksiz).

#### 💡 "Deyarli tekin" variant (siz "tekin bo'lsa ham zo'r" dedingiz)

Bu hajmda (1,560 soat/oy) haqiqiy tekin API varianti **yo'q** — barcha free tier'lar rate-limit bilan cheklangan va oyiga bir necha soat audio beradi. Lekin bitta yo'l bor:

**Bir martalik apparat + self-hosting:**
| Element | Xarajat |
|---|---|
| RTX 4090 / 5090 ish stansiyasi (bir marta) | ~$2,500–3,500 |
| Elektr + internet (oyiga) | ~$30–40 |
| **Marginal ASR xarajati** | **≈ $0** |

Hisob: 60 soat audio/kun ÷ 25× realtime = **2.4 GPU-soat/kun** — bitta RTX 4090 buni bemalol uddalaydi (kuniga 2.5 soat ishlaydi, 21 soat bo'sh turadi — pyannote diarizatsiya va prosodika ham shu yerda ishlaydi).

**Qoplanish muddati:** ElevenLabs Scribe ($343/oy) ga nisbatan → **~9 oy**. Groq turbo ($142/oy) ga nisbatan → ~25 oy.

**Lekin:** o'zbek tilida Whisper large-v3 ning "qutidan chiqqan" sifati past (~20–28% WER). Bu variant faqat **fine-tune bilan** ma'no kasb etadi — sizda oyiga 1,560 soat domen-audio yig'iladi, bu fine-tune uchun ideal ma'lumot.

**Tavsiya etilgan yo'l:**
```
1-6 oy:   Bulut API (benchmark g'olibi) — tez ishga tushish, ma'lumot yig'ish
          + har call'ni arxivlash (fine-tune datasetiga aylanadi)
6-9 oy:   500-1000 soat qo'lda tekshirilgan transkript to'planadi
9-12 oy:  Whisper large-v3 ni shu ma'lumot bilan fine-tune qilish
12+ oy:   O'z GPU'ga o'tish → ASR xarajati ~$0, sifat bulutdan YUQORI
          (chunki aynan sizning mahsulot nomlaringiz va dialektlaringizga o'rgatilgan)
```

#### 🔬 MAJBURIY BOSQICH: ASR Benchmark (1-hafta)

**Hech qanday qaror qabul qilmang, avval o'lchang.** Bu 1 haftalik ish keyingi 2 yillik xarajatni belgilaydi.

**Metodologiya:**
1. **30 ta real call tanlang** (har regiondan 5 ta): Toshkent, Farg'ona vodiysi (Qo'qon), Buxoro, Xorazm, Samarqand, Surxondaryo.
   - 10 ta — sof o'zbek
   - 10 ta — uz/ru aralash (kod-almashinuv)
   - 10 ta — shovqinli muhit (do'kon, ko'cha)
2. **Qo'lda "gold" transkript yozing** (har biri ~15 daqiqa ish, jami ~8 soat).
3. Har bir ASR xizmatiga yuboring, **WER** (Word Error Rate) va **DER** (Diarization Error Rate) hisoblang.
4. **Muhim:** faqat WER emas, **biznes-kritik aniqlik** ni ham o'lchang:
   - Mahsulot nomlari to'g'ri yozildimi?
   - Raqamlar (miqdor, narx) to'g'rimi?
   - Kim gapirgani to'g'ri ajratildimi (agent vs client)?

**Qaror qoidasi:**
| WER | Qaror |
|---|---|
| < 15% | ✅ LLM baholash ishonchli ishlaydi |
| 15–25% | ⚠️ Ishlaydi, lekin rubrikani soddalashtirish kerak |
| > 25% | ❌ Bu ASR yaramaydi — boshqasiga o'ting yoki fine-tune qiling |

#### Tavsiya qilinadigan strategiya

1. **Bosqich 0 (benchmark):** Groq large-v3-turbo, Groq large-v3, ElevenLabs Scribe, Kotib — 4 tasini bir xil 30 ta call'da o'lchash.
2. **MVP (1–3 oy):** Benchmarkdan **o'tgan eng arzoni**. Mening prognozim — ElevenLabs Scribe v2.
3. **Agar hech biri o'tmasa:** Gibrid — til segment darajasida aniqlanadi, sof o'zbek qismlar Kotib/Muxlisa'ga, rus qismlar Scribe'ga. Qimmatroq, lekin ishlaydi.
4. **Uzoq muddat (9–12 oy):** O'z ma'lumotingiz bilan Whisper fine-tune + o'z GPU'ingiz → ASR xarajati ≈ $0 va sifat bulutdan yuqori.

#### ⚙️ Arxitektura talabi: ASR adapter

ASR provayderi **bitta interfeys ortida** yashirilsin — bu bepul, lekin keyinchalik millionlab so'm tejaydi:

```python
class ASRProvider(Protocol):
    def transcribe(self, audio_path: str, language_hint: str | None) -> Transcript: ...
    #  Transcript: segments[(speaker, start_ms, end_ms, text, confidence)]

# Implementatsiyalar (bir xil interfeys):
#   GroqWhisperProvider     — arzon, diarizatsiya pyannote bilan
#   ElevenLabsScribeProvider — diarizatsiya ichida
#   KotibProvider            — mahalliy
#   LocalWhisperProvider     — o'z GPU'da (kelajak)
```

Provayder `.env` faylidagi bitta o'zgaruvchi bilan almashtiriladi. Benchmark natijasi kelgunicha kod yozishni to'xtatmaslik uchun ham kerak.

### 3.3 Diarizatsiya (kim gapirdi?) — muhim nozik nuqta

**Muammo:** MoyZvonki telefondan yozib oladi → **mono aralash yozuv** (agent va client bitta kanalda).

**Natijalar:**
- Diarizatsiya **majburiy** — usiz kim nima degani noma'lum, rubrikani baholab bo'lmaydi.
- Scribe v2 ichida bor. Agar boshqa ASR tanlansa — `pyannote.audio` (community-1 model) qo'shiladi.
- **Speaker labeling:** Diarizatsiya "SPEAKER_00 / SPEAKER_01" beradi. Qaysi biri agent ekanini aniqlash kerak:
  - **Usul A (ishonchli):** Agentning ovoz izidan (voice embedding) foydalanish — har agent uchun 30 soniyalik namuna, keyin `speechbrain/spkrec-ecapa` bilan solishtirish.
  - **Usul B (oddiy):** Chiquvchi qo'ng'iroqda odatda birinchi gapirgan = agent. + Mikrofonga yaqin ovoz balandroq (RMS yuqoriroq).
  - **Tavsiya:** A + B birgalikda, ishonch < 80% bo'lsa LLM'ga "spiker noaniq" deb belgilab yuborish.

### 3.4 LLM baholash — rubrika va model

#### Model tanlovi

| Model | Narx (input/output, 1M token) | Batch bilan | **Oylik xarajat** | Vazifa |
|---|---|---|---|---|
| **Claude Haiku 4.5** | $1 / $5 | $0.50 / $2.50 | **$54** | ✅ **Asosiy baholovchi** — arzonlik ustuvor bo'lgani uchun shundan boshlanadi |
| **Claude Sonnet 5** | $3 / $15 | $1.50 / $7.50 | $163 | Zaxira: Haiku gold set testidan o'tmasa, shunga ko'tariladi |
| **Claude Opus 5** | $5 / $25 | $2.50 / $12.50 | $272 (to'liq) / **$22** (8% sampl) | Kalibratsiya etaloni + nizoli/apellyatsiya holatlari + oylik audit sampli |
| *Gemini 3.x Flash* | $0.75 / $3.75 | $0.375 / $1.875 | *$42* | *Muqobil — A/B test qilish mumkin, lekin o'zbek tilida ko'rsatkichi tekshirilmagan* |

**Nega Haiku'dan boshlaymiz:** siz arzonlikni ustuvor deb belgiladingiz, va rubrika bo'yicha baholash — bu klassifikatsiya + dalil ajratish vazifasi, ekstremal reasoning talab qilmaydi.

**Lekin qaror gold set bilan qabul qilinadi, taxmin bilan emas.** Bosqich 2 kalibratsiyasida uchala modelni bir xil 150 ta gold call'da o'lchang:

| Natija | Qaror |
|---|---|
| Haiku MAE < 8 ball | ✅ Haiku qoldiriladi — **$54/oy** |
| Haiku MAE 8–12 | ⚠️ Rubrikani soddalashtiring, qayta sinang; yordam bermasa → Sonnet |
| Haiku MAE > 12 | ❌ Sonnet 5 ga o'ting — **$163/oy** ($109/oy qo'shimcha, bu 15 xodimni to'g'ri baholash uchun arzimas) |

**Opus 5 ning roli** — u barcha call'larni baholamaydi (qimmat), balki:
- Kalibratsiyada **"oltin standart"** vazifasini bajaradi (inson bahosiga eng yaqin model)
- Agent apellyatsiya qilganda qayta baholaydi
- Har oy tasodifiy 8% sampl'ni tekshiradi (asosiy model "drift" qilmaganini nazorat qilish)
→ **$22/oy**

#### Xarajatni optimallashtirish (juda muhim)

| Texnika | Ta'sir | Qanday |
|---|---|---|
| **Batch API** | −50% | Call'lar real-time kerak emas. Tunda 02:00 da kunlik batch yuboriladi, ertalab natija tayyor |
| **Prompt caching** | Rubrika tokenlari −90% | Rubrika + tizim prompti ~3,000 token, har call'da takrorlanadi. `cache_control: ephemeral, ttl: 1h` bilan 0.1× narx |
| **Haiku pre-filter** | −15–20% hajm | 60 soniyadan qisqa, javobsiz, texnik call'lar baholanmaydi |
| **Structured output** | Retry'larni yo'qotadi | `output_config.format` + JSON schema → parse xatosi yo'q |

> ⚠️ **Prompt caching nozikligi:** Rubrika **bayt-ma-bayt bir xil** bo'lishi kerak. Prompt ichiga `datetime.now()`, call ID, agent ismi qo'shmang — bularni cache breakpoint'dan **keyin** joylashtiring. Aks holda cache hech qachon ishlamaydi.

#### Baholash rubrikasi (v1 — savdo direktori bilan tasdiqlanadi)

**Umumiy ball: 0–100.** 5 blok, har birida og'irlik (weight).

**Blok A — Skript va struktura (25 ball)**
| Kriteriya | Ball | Nima tekshiriladi |
|---|---|---|
| A1. Salomlashish + o'zini tanishtirish | 5 | "Assalomu alaykum, men [ism], [kompaniya]dan" |
| A2. Ehtiyojni aniqlash (savol berdimi?) | 8 | Ochiq savollar, mahsulot ehtiyojini so'radi |
| A3. Mahsulotni to'g'ri taqdim etdi | 7 | Model, xususiyat, narx to'g'ri aytildi |
| A4. Keyingi qadam kelishildi | 5 | "Ertaga qo'ng'iroq qilaman" / zakaz tasdiqlandi |

**Blok B — Muloqot madaniyati (25 ball)**
| Kriteriya | Ball | Nima tekshiriladi |
|---|---|---|
| B1. Hurmatli ohang | 8 | Siz'lash, xushmuomalalik |
| B2. Haqorat/so'kinish yo'q | 10 | ❌ **Avtomatik 0** — butun call uchun red flag |
| B3. Client'ni bo'lmadi | 4 | Overlap/interruption tahlili (akustik) |
| B4. Ovoz toni mos | 3 | Prosodika: baqirish, asabiylik |

**Blok C — Muammoni hal qilish (25 ball)**
| Kriteriya | Ball |
|---|---|
| C1. Client savoliga to'g'ri javob berdi | 10 |
| C2. E'tirozlarni ishlab chiqdi (objection handling) | 8 |
| C3. Mos taklif berdi (mahsulot ehtiyojga to'g'ri keldimi) | 7 |

**Blok D — Savdo qobiliyati (15 ball)** — *D3 qaroriga ko'ra qayta yozildi*

> ⚠️ **Muhim o'zgarish:** SAP integratsiyasi qamrovda yo'q, shuning uchun bu blok **haqiqiy savdo faktini emas, xodimning savdo qilish mahoratini** o'lchaydi. Bu aslida siz aytgan narsaga aynan mos: *"savdo xodimlarimizni gaplashishini tekshiramiz, savdo qilolish darajasini skriptdan aniqlasa zo'r bo'lardi"*.

| Kriteriya | Ball | Nima tekshiriladi (faqat transkriptdan) |
|---|---|---|
| D1. Yopish urinishi (closing) | 5 | Xodim aniq taklif qildimi? ("Nechta olamiz?", "Bugun jo'natamizmi?") yoki suhbatni osilgan holda tugatdimi |
| D2. Upsell / cross-sell urinishi | 4 | Qo'shimcha model/miqdor taklif qilindimi |
| D3. Aniq keyingi qadam belgilandi | 3 | "Payshanba qo'ng'iroq qilaman" — mavhum "keyinroq gaplashamiz" emas |
| D4. Shoshilinchlik/qiymat argumenti | 3 | Nega hozir olish kerakligini asosladimi (aksiya, qoldiq, mavsum) |

**Alohida (ball bermaydi, faqat signal sifatida yoziladi):**
```json
"outcome_signal": {
  "type": "order_agreed | follow_up | rejected | info_only | unclear",
  "products_mentioned": ["Model X-200", "Model Y-50"],
  "quantity_mentioned": 50,
  "confidence": 0.72,
  "evidence": "12:04 — 'Mayli, 50 ta X-200 dan jo'nating'"
}
```

**Nega ball bermaydi:** transkriptdan zakaz aniqlash ~80–85% aniqlikda ishlaydi. Buni **ball** qilsak, xodim ASR xatosi sababli jazolanadi. Shuning uchun:
- ✅ Dashboardda **agregat trend** sifatida ko'rsatiladi ("Sardor call'larining 34% da zakaz kelishuvi belgilari bor")
- ✅ Menejer uchun **filtr** ("zakaz kelishilgan call'larni ko'rsat")
- ❌ Xodim bahosiga to'g'ridan-to'g'ri qo'shilmaydi

**Kelajakda (ixtiyoriy, 6+ oy):** agar SAP'dan **kunlik CSV eksport** olish mumkin bo'lsa (to'liq integratsiya emas, faqat `sana, client, xodim, summa` fayli), uni AI signali bilan solishtirib "yuqori ball ↔ ko'proq savdo" korrelyatsiyasini isbotlash mumkin. Bu 2–3 kunlik ish va SAP'ga tegmaydi. **Hozircha qamrovda emas.**

**Blok E — Red Flag'lar (jarima, −ball)**
| Holat | Jarima |
|---|---|
| Haqorat, so'kinish | Umumiy ball → 0, darhol menejerga alert |
| Baqirish (prosodika + kontekst tasdig'i) | −20 |
| Bajarib bo'lmaydigan va'da ("ertaga yetkazamiz" — imkonsiz) | −15 |
| Kompaniya/hamkasb haqida salbiy gap | −15 |
| Rasmiy narxdan tashqari kelishuv | −25 + alert |
| Client shikoyatini e'tiborsiz qoldirish | −10 |

#### LLM chiqish formati (structured output)

```json
{
  "call_id": "uuid",
  "language_detected": "uz | ru | mixed",
  "transcript_quality": "high | medium | low",
  "overall_score": 78,
  "blocks": {
    "A_script":  { "score": 20, "max": 25, "criteria": [
        { "id": "A1", "score": 5, "verdict": "pass",
          "evidence": "00:03 — 'Assalomu alaykum, men Sardor, ...'" },
        { "id": "A2", "score": 4, "verdict": "partial",
          "evidence": "01:12 — faqat 1 ta ochiq savol berdi",
          "improvement": "Ehtiyojni aniqlash uchun kamida 3 savol kerak" }
    ]},
    "B_communication": { "...": "..." },
    "C_resolution":    { "...": "..." },
    "D_business":      { "...": "..." }
  },
  "red_flags": [
    { "type": "unrealistic_promise", "severity": "high",
      "timestamp": "07:42",
      "quote": "Ertaga ertalab yetkazib beramiz",
      "penalty": -15 }
  ],
  "call_outcome": "order_placed | follow_up | rejected | info_only",
  "order_mentioned": { "product": "…", "quantity": 50, "confidence": 0.85 },
  "client_sentiment": "positive | neutral | negative",
  "coaching_note": "Sardor mahsulotni yaxshi taqdim etdi, lekin client'ning byudjet e'tiroziga javob bermadi. Tavsiya: e'tiroz bilan ishlash treningi.",
  "confidence": 0.88,
  "needs_human_review": false
}
```

**Muhim dizayn qarorlari:**
- ✅ Har ball uchun **evidence (dalil) + timestamp** majburiy. Bu menejerga "nega 4 ball?" savoliga javob beradi va AI hallucination'ini kamaytiradi.
- ✅ `confidence` past bo'lsa (< 0.7) yoki `transcript_quality: low` bo'lsa → `needs_human_review: true`, dashboardda alohida navbatga tushadi.
- ✅ Ball **hech qachon avtomatik jazo bermaydi** — bu koučing vositasi. HR qarori har doim odam orqali.

### 3.5 Prosodika (ovoz toni, detsibel) — realistik yondashuv

Siz ovoz tonini (baqirish, asabiylik) tahlil qilishni so'radingiz. Buni **to'g'ri** qilish kerak, aks holda noto'g'ri ayblovlar bo'ladi.

#### ❌ Nima ishlamaydi

**Mutlaq detsibel (dB) o'lchash — ishlamaydi.** Sabablari:
- Telefon mikrofonlari har xil (Samsung ≠ Xiaomi ≠ iPhone)
- Android'da **AGC (Automatic Gain Control)** yoqilgan — ovozni avtomatik tekislaydi
- Agent mikrofonga yaqin (baland), client eshitgichdan (past) → doim agent balandroq ko'rinadi
- Muhit shovqini (do'kon, ko'cha) fon darajasini o'zgartiradi

> **Xulosa: "60 dB dan yuqori = baqirdi" degan qoida yaramaydi va noto'g'ri ayblovga olib keladi.**

#### ✅ Nima ishlaydi — nisbiy (relative) xususiyatlar

Har agent uchun **shaxsiy baseline** hisoblanadi (oxirgi 30 kunlik call'lari), keyin har call shu baseline'ga nisbatan o'lchanadi (z-score).

| Xususiyat | Kutubxona | Nima ko'rsatadi |
|---|---|---|
| **RMS energiya z-score** | `librosa` | Agent o'zining odatiy ovozidan qancha balandroq gapirdi |
| **F0 (asosiy chastota) o'rtacha + dispersiya** | `parselmouth` (Praat) | Ovoz balandligi ko'tarilishi = hayajon/g'azab belgisi |
| **Jitter, shimmer, HNR** | `openSMILE` (eGeMAPS) | Ovoz sifati — asabiylik, titrash |
| **Nutq tezligi (so'z/min)** | ASR timestamp'dan | Tez gapirish = bosim, shoshilish |
| **Overlap / bo'lish soni** | Diarizatsiya | Client gapirayotganda agent gapirdimi (eng ishonchli signal) |
| **Talk ratio** | Diarizatsiya | Agent gapirgan vaqt / umumiy. Yaxshi savdoda 40–50% |
| **Uzun pauzalar** | VAD | > 5 soniya jimlik = noaniqlik, tayyor emaslik |
| **Vokal affekt (emotion)** | `audEERING wav2vec2-dim` yoki `emotion2vec` | Arousal/valence o'lchovi |

#### 🔑 Oltin qoida: prosodika **yakka o'zi hech qachon ball bermaydi**

Prosodika faqat **matn bilan birga** ishlatiladi:

```
Agar (RMS z-score > 2.0) VA (F0 z-score > 1.5) VA (overlap yuqori)
    → "Yuqori arousal segmenti" deb belgilanadi (timestamp bilan)
    → LLM'ga shu segment matni + "bu qismda ovoz keskin ko'tarilgan" konteksti beriladi
    → LLM qaror qiladi: bu g'azabmi, hayajonmi, yoki shovqinli muhitda ovozni ko'tarishmi?
```

**Nega:** Agent bozorda shovqinda gapirayotgan bo'lsa ovozini ko'taradi — bu baqirish emas. Yoki client'ni tabriklayotgan bo'lsa hayajonlanadi — bu ijobiy. Faqat **kontekst** farqni ko'rsatadi.

#### Xarajat
Prosodika CPU'da ishlaydi, GPU kerak emas. 1,560 soat/oy ≈ kichik server. **~$30–50/oy**.

### 3.6 Kalibratsiya va sifat nazorati (AI'ga qanday ishonamiz?)

**AI baholashi tekshirilmasa — bu ishonchsiz raqam, xodimlar to'g'ri aytadi.**

#### Gold Set (etalon to'plam)
1. **150 ta call** tanlang (turli agent, region, natija).
2. **2 ta mustaqil odam** (savdo direktori + sifat menejeri) rubrika bo'yicha qo'lda baholaydi.
3. Ularning o'zaro kelishuvini o'lchang (**inter-rater agreement**, Cohen's kappa). Agar odamlar o'zaro kelisha olmasa — **rubrika noaniq**, avval uni tuzating.
4. AI'ni shu 150 ta call'ga qo'ying, o'lchang:
   - **MAE** (o'rtacha absolyut xato) — maqsad: < 8 ball (100 balllik shkalada)
   - **Korrelyatsiya** (Pearson r) — maqsad: > 0.75
   - **Red flag recall** — maqsad: > 90% (haqoratni o'tkazib yubormaslik kritik)
   - **Red flag precision** — maqsad: > 85% (yolg'on ayblov bo'lmasin)

#### Doimiy nazorat
| Nima | Chastota |
|---|---|
| Tasodifiy 20 ta call'ni menejer qo'lda tekshiradi | Har hafta |
| Rubrika qayta ko'rib chiqiladi (savdo direktori bilan) | Har oyda |
| Gold set kengaytiriladi (+30 call) | Har chorakda |
| Agentlar apellyatsiya qilishi mumkin ("bu baho noto'g'ri") | Doim — dashboardda tugma |

> **Apellyatsiya mexanizmi majburiy.** Agentlar tizimga ishonishi uchun "men rozi emasman" tugmasi bo'lishi kerak. Har apellyatsiya gold set'ga qo'shiladi va rubrikani yaxshilaydi.

---

## 4. Xarajat hisob-kitobi

**Kurs taxmini:** 1 USD ≈ 12,500 so'm *(tasdiqlashingiz kerak)*

### 4.1 Oylik operatsion xarajat — 4 stsenariy (1,560 soat/oy)

| Komponent | **A. Maksimal tejamkorlik** | **B. Muvozanatli (tavsiya)** | C. Sifat ustuvor | D. To'liq mahalliy |
|---|---|---|---|---|
| **ASR** | Groq turbo: $62 | ElevenLabs Scribe: $343 | ElevenLabs Scribe: $343 | Kotib: **$2,246** |
| **Diarizatsiya** | pyannote GPU: $80 | ichida: $0 | ichida: $0 | pyannote: $80 |
| **LLM baholash** | Haiku 4.5 + batch + cache: $54 | Haiku 4.5: $54 | Sonnet 5: $163 | Haiku: $54 |
| **LLM audit** (Opus 5, 8%) | $22 | $22 | $22 | $22 |
| **Prosodika (CPU)** | $40 | $40 | $40 | $40 |
| **Server** (backend+DB+bot) | $50 | $80 | $80 | $80 |
| **Object storage** ⭐ | $15 | $15 | $60 | $15 |
| **JAMI** | **~$323/oy** | **~$554/oy** | **~$708/oy** | **~$2,537/oy** |
| **So'mda** | **~4.0 mln** | **~6.9 mln** | ~8.9 mln | ~31.7 mln |
| 1 xodimga | **$22/oy** | $37/oy | $47/oy | $169/oy |
| 1 daqiqaga | **$0.0035** | $0.0059 | $0.0076 | $0.027 |
| **Risk** | 🔴 ASR sifati o'tmasligi mumkin | 🟢 Past | 🟢 Eng past | 🟡 Faqat qonun talab qilsa |

⭐ **Storage optimizatsiyasi (bepul tejash):** xom audio'ni **Opus 16 kbps mono** ga konvertatsiya qiling — sifat ASR uchun yetarli, hajm **~10× kichrayadi** (1.5 TB → ~150 GB/oy). Bu $60 → $15 qiladi. Xom faylni transkripsiyadan keyin o'chiring, faqat siqilganini saqlang.

> **Tavsiyam: B stsenariy ($554/oy ≈ 6.9 mln so'm).** A dan atigi $231/oy qimmat, lekin ASR sifat riski yo'q va ikkita vendor o'rniga bitta (diarizatsiya ichida — kamroq kod, kamroq nosozlik).
> **Lekin qaror benchmarkdan keyin.** Agar Groq turbo WER < 20% chiqsa — A stsenariyni oling, yiliga $2,772 (≈35 mln so'm) tejaysiz.

### 4.1.1 Qo'shimcha tejash imkoniyatlari (kod bilan, bepul)

| Texnika | Tejash | Qanday |
|---|---|---|
| **Sukunatni kesish (VAD)** | ASR −15–25% | Qo'ng'iroqning 15–25% — jimlik va gudok. `silero-vad` bilan kesib tashlang, keyin ASR'ga yuboring. **Eng katta bitta tejamkorlik** |
| **Qisqa call filtri** | −5–8% | < 45 soniya call'lar (javob bermagan, noto'g'ri raqam) umuman qayta ishlanmasin |
| **Takroriy call birlashtirish** | −3% | Bir client bilan 10 daqiqada 3 marta gaplashilsa — bitta seans sifatida baholash |
| **Prompt caching** | LLM −40% | Rubrika (~3,000 token) har call'da 0.1× narxda |
| **Batch API** | LLM −50% | Tunda paketda yuborish |
| **Opus siqish** | Storage −90% | Yuqorida |

**Hammasi qo'llanilsa:** B stsenariy $554 → **~$430/oy (≈5.4 mln so'm)**. VAD + qisqa call filtri MVP'ga darhol kiritilsin.

### 4.2 LLM hisob-kitobi tafsiloti

```
Bir call (8 daqiqa):
  Transkript (diarizatsiya + timestamp bilan)       ≈ 4,000 token
  Rubrika + tizim prompti (cached → 0.1× narx)      ≈ 3,000 → effektiv 300 token
  Prosodika xulosasi                                ≈   200 token
  ─────────────────────────────────────────────────────────────
  Effektiv input                                    ≈ 4,500 token
  Output (JSON, dalillar bilan)                     ≈ 1,000 token

Oyiga 11,700 call → 52.7M input token, 11.7M output token
```

| Model | Input xarajat | Output xarajat | **JAMI/oy** |
|---|---|---|---|
| **Haiku 4.5** (batch) | 52.7M × $0.50 = $26 | 11.7M × $2.50 = $29 | **$55** |
| Sonnet 5 (batch) | 52.7M × $1.50 = $79 | 11.7M × $7.50 = $88 | $167 |
| Opus 5 (batch) | 52.7M × $2.50 = $132 | 11.7M × $12.50 = $146 | $278 |
| *Gemini 3.x Flash (batch)* | *52.7M × $0.375 = $20* | *11.7M × $1.875 = $22* | *$42* |

**Caching'siz Haiku:** $59 + $29 = $88/oy → ya'ni caching bitta o'zi **$33/oy tejaydi**. Batch'siz esa narx 2× bo'lardi. Ikkalasi ham majburiy.

### 4.3 Tayyor platforma bilan taqqoslash (build vs buy)

Kotib STT ochiq narxi 300 so'm/min. Analitika platformasi odatda STT ustiga 2–3× marja qo'yadi → realistik **600–900 so'm/min**.

| | Qurish (build) — B stsenariy | Sotib olish (buy) |
|---|---|---|
| Oylik operatsion | **$554** (optimizatsiya bilan $430) | 93,600 min × 700 so'm = 65.5 mln so'm ≈ **$5,240** |
| Bir martalik ishlab chiqish | ~$18,000–25,000 (3–4 oy, 2.5 dev) | $0 |
| **Yillik (1-yil)** | ~$26,600 | **~$63,000** |
| **Yillik (2-yil)** | ~$6,600 | **~$63,000** |
| Moslashuvchanlik | ✅ To'liq (o'z rubrikangiz, Telegram integratsiya, o'z metrikalaringiz) | ❌ Ularning rubrikasi |
| Ma'lumot egaligi | ✅ Sizniki | ⚠️ Ularda |
| Client reyting tizimi | ✅ Bor | ❌ Odatda yo'q — bu sizning noyob talabingiz |
| Risk | Dev risk, ASR sifat riski | Vendor lock-in, narx oshishi |

> **Xulosa: qurish 1-yildayoq ~2.4× arzon, 2-yildan boshlab ~7× arzon.** Va client-reyting moduli tayyor platformalarda yo'q — baribir qurish kerak bo'lardi.

> **Muhim eslatma:** Bu solishtirish Kotib narxlarining STT'dan ekstrapolyatsiyasi. **Aniq taklif so'rang** — Kotib, Deepsales, Muxlisa va ovozai.uz'ga 1,560 soat/oy hajm uchun rasmiy narx so'rovi yuboring. Ular volume discount berishi mumkin.

---

## 5. Integratsiyalar

### 5.1 MoyZvonki

**API tafsilotlari (moizvonki.ru, O'zbekiston versiyasi shu platformada):**
- Base URL: `https://<domain>.moizvonki.ru/api/v1`
- Autentifikatsiya: JSON body ichida `user_name` (email) + `api_key` (Sozlamalar → Integratsiya)
- Metod: HTTP POST, `Content-Type: application/json`

**Bizga kerakli metodlar:**
| Metod | Vazifa |
|---|---|
| `calls.list` | Qo'ng'iroqlar ro'yxati. Parametrlar: `from_date`/`from_id` (majburiy), `to_date`, `max_results`, `from_offset`, `supervised=1` (barcha xodimlar) |
| `webhook.subscribe` | Real-time hodisalar: `call.start`, `call.answer`, **`call.finish`** ← bizga shu kerak |
| `company.list_employee` | Xodimlar ro'yxati (agent mapping uchun) |

**Yozuvni olish:** `calls.list` javobida javob berilgan qo'ng'iroqlar uchun `recording` maydonida URL keladi.

**🔴 KRITIK: 30 kunlik saqlash limiti.**
> MoyZvonki serverida audio yozuvlar **30 kun** saqlanadi. Bu bizning arxivimiz emas.
> **Yechim:** `call.finish` webhook kelishi bilan **darhol** yozuvni o'z object storage'imizga ko'chirish. Kechikish ruxsat etilmaydi.
> Qo'shimcha: kunlik `calls.list` reconciliation job — webhook o'tkazib yuborilgan call'larni topib yuklaydi.

**Tarif:** 230 ₽/qurilma/oy (yozuv bilan). 15 xodim = 3,450 ₽/oy ≈ $37/oy. Yillik to'lovda −20%.

**⚠️ Tekshirish kerak:**
- MoyZvonki O'zbekistonda qanday yuridik shaxs orqali ishlaydi? Shartnoma kim bilan?
- Barcha telefonlar Android'mi? (iPhone'da yozib olish ishlamaydi — Apple cheklovi)
- Audio formati va bitrate? (m4a/AMR past bitrate ASR sifatini tushiradi)
- Qurilmalarda yozib olish qaysi modellarda ishlaydi? (MoyZvonki hujjatlari "telefon modeliga bog'liq" deydi)

### 5.2 Telegram Bot

**Kutubxona:** `aiogram 3.x` (Python) yoki `grammY` (Node.js). Ikkalasi ham yaxshi.

**Bot arxitekturasi:**

```
Bot funksiyalari:
├── Guruh boshqaruvi
│   ├── Guruhga qo'shilganda → client'ni ro'yxatga olish
│   ├── Guruh ↔ (client_id, agent_id) mapping saqlash
│   └── Guruhdan chiqarilganda → deaktivatsiya
├── So'rovnoma yuborish (scheduled job)
│   ├── Har hafta: keyingi navbatdagi client'lar tanlanadi
│   ├── Guruhga: matn + inline button (deep-link + token)
│   └── Suppression: oxirgi 10 kunda so'ralgan bo'lsa — o'tkazib yuborish
├── Shaxsiy chatda baholash (FSM state machine)
│   ├── /start srv_<token> → token validatsiya → so'rovnoma boshlanadi
│   ├── Savol 1: 5 ta inline button (⭐1–5)
│   ├── Savol 2: 3 ta button (Ha/Qisman/Yo'q)
│   ├── Savol 3: matn (yoki "O'tkazib yuborish")
│   └── Rahmat + saqlash
├── Fallback
│   ├── Bot bloklangan / shaxsiy chat ochilmagan → Eskiz SMS
│   └── 3 kun javob yo'q → 1 marta eslatma (guruhda emas, shaxsiyda)
└── Menejer buyruqlari (faqat ruxsat berilgan user_id'lar)
    ├── /stats — umumiy holat
    └── /pending — javob bermagan client'lar
```

**Token dizayni:** `srv_<base62(uuid)>` — bazada `(client_id, agent_id, period_start, period_end, expires_at, used_at)` bilan bog'langan. Bir martalik, 7 kun amal qiladi.

**Telegram rate limitlari (e'tiborda tuting):**
- Guruhga: ~20 xabar/daqiqa
- Umumiy: ~30 xabar/soniya
- 500 client uchun → 25 daqiqa. Queue orqali sekin yuborish kerak.

### 5.3 Eskiz.uz (SMS fallback)

- **Narx:** 95 so'm/SMS (oddiy), 175 so'm/SMS (Ucell/Uzmobile/Mobiuz reklama)
- **API:** HTTP/HTTPS, Postman hujjatlari mavjud, ro'yxatdan o'tishda 100 test SMS bepul
- **Limit:** 1 SMS = 160 lotin belgi / 70 kirill belgi
- **Ishlatilishi:** Faqat Telegram'i yo'q yoki botni bloklagan client'lar (~10%). Oyiga ~100 SMS ≈ 9,500 so'm. Deyarli bepul.
- **⚠️ Muhim:** Reklama SMS uchun shablon (template) oldindan tasdiqlanishi kerak. So'rovnoma linki "reklama" deb hisoblanishi mumkin — Eskiz bilan aniqlashtiring.

---

## 6. Dashboard dizayni

### 6.1 Rollar va ruxsatlar

| Rol | Ko'radi | Ko'rmaydi |
|---|---|---|
| **Boss** | Hamma narsa, barcha xodimlar, barcha call'lar, moliyaviy kesim | — |
| **Menejer** | O'z guruhidagi xodimlar, ularning call'lari, client izohlari | Boshqa menejer guruhi |
| **Savdo xodimi** | **Faqat o'zining** ballari, transkriptlari, koučing izohlari, o'z reyting o'rtachasi | Boshqa xodimlar ballari, client izohlarining muallifi, reyting tafsilotlari |
| **Sifat menejeri (QA)** | Barcha call'lar, apellyatsiyalar navbati, kalibratsiya vositasi | Moliyaviy ma'lumot |

> **Muhim prinsip:** Savdo xodimi o'z ballarini **ko'rishi kerak** — bu koučing vositasi, jazo emas. Yashirin baholash tizimi ishonchni yo'q qiladi va xodimlar ketishiga sabab bo'ladi.

### 6.2 Asosiy ekranlar

#### Ekran 1: Umumiy ko'rinish (Boss/Menejer)
```
┌───────────────────────────────────────────────────────────────────┐
│  Filtrlar: [Sana ▾] [Region ▾] [Xodim ▾] [Mahsulot ▾] [Til ▾]     │
├───────────────────────────────────────────────────────────────────┤
│  📞 Qo'ng'iroqlar   ⭐ AI o'rtacha   👤 Client o'rtacha   🚩 Flag  │
│      11,240            76.4 / 100        4.3 / 5.0          18     │
│      ▲ +4%             ▲ +2.1           ▼ −0.1            ▼ −5    │
├───────────────────────────────────────────────────────────────────┤
│  Trend grafigi: AI bahosi vs Client bahosi (vaqt bo'yicha)        │
│  [ikki chiziqli chart — korrelyatsiyani ko'rsatadi]                │
├───────────────────────────────────────────────────────────────────┤
│  Xodimlar reytingi                                                 │
│  ┌────────┬──────────┬───────┬──────────┬───────┬────────┬──────┐│
│  │ Xodim  │ Region   │ Call  │ AI ball  │Client │ Divergen│ Flag ││
│  ├────────┼──────────┼───────┼──────────┼───────┼────────┼──────┤│
│  │ Sardor │ Toshkent │  812  │ 84.2 ↑   │ 4.6★  │  +0.2  │  0   ││
│  │ Aziz   │ Vodiy    │  744  │ 79.1 →   │ 4.4★  │  −0.1  │  2   ││
│  │ Jasur  │ Buxoro   │  690  │ 61.3 ↓   │ 4.8★  │ 🚩+1.4 │  5   ││ ← divergensiya!
│  │ Nodir  │ Xorazm   │  598  │ 72.0 ↑   │ n<5   │   —    │  1   ││
│  └────────┴──────────┴───────┴──────────┴───────┴────────┴──────┘│
└───────────────────────────────────────────────────────────────────┘
```

#### Ekran 2: Xodim profili
- AI ball trendi (blok bo'yicha razrez: skript / muloqot / hal qilish / natija)
- Client reytingi + ishonch oralig'i + izohlar (anonim)
- Eng past baholangan 10 ta call (koučing uchun)
- Eng yaxshi 5 ta call (namuna sifatida)
- Red flag'lar tarixi
- Prosodika: o'rtacha talk-ratio, bo'lish soni, nutq tezligi (baseline'ga nisbatan)

#### Ekran 3: Call detali (eng muhim ekran)
```
┌─────────────────────────────────────────────────────────────────┐
│  🔊 [══════▶════════════════] 08:42    Sardor ↔ Akmal (Qo'qon) │
│      ▲ waveform, red flag'lar rangli belgilangan                │
├─────────────────────────────────────────────────────────────────┤
│  Ball: 68/100    Til: uz/ru aralash   Ishonch: 0.91             │
│                                                                  │
│  📝 Transkript (diarizatsiya bilan)  │  ⭐ Baholash              │
│  ┌────────────────────────────────┐  │  ┌────────────────────┐  │
│  │ 00:03 🧑‍💼 Assalomu alaykum...  │  │  │ A. Skript   20/25 ✅│  │
│  │ 00:09 👤 Vaalaykum assalom...  │  │  │ B. Muloqot  18/25 ⚠️│  │
│  │ 01:12 🧑‍💼 Sizga qaysi model...│  │  │ C. Hal qilish 22/25✅│  │
│  │ 07:42 🧑‍💼 Ertaga yetkazamiz  │◄─┼──┤ 🚩 Bajarilmas va'da │  │
│  │       ⚠️ RED FLAG              │  │  │ D. Natija    8/15 ⚠️│  │
│  └────────────────────────────────┘  │  └────────────────────┘  │
│                                                                  │
│  💡 Koučing izohi: "Mahsulotni yaxshi taqdim etdi, lekin        │
│     byudjet e'tiroziga javob bermadi. Tavsiya: ..."             │
│                                                                  │
│  [ ✍️ Menejer izohi ]  [ ⚖️ Apellyatsiya ]  [ ⭐ Namuna qilish ] │
└─────────────────────────────────────────────────────────────────┘
```

#### Ekran 4: Client fikrlari
- So'nggi izohlar (anonim, lekin regionga bog'langan)
- Sentiment trendi
- Response rate monitoringi
- Eng ko'p takrorlanuvchi shikoyat mavzulari (LLM orqali klasterlangan)

### 6.3 Filtrlar (siz so'ragan "bir necha xil filterlar")
| Filtr | Qiymatlar |
|---|---|
| Vaqt | Bugun / 7 kun / 30 kun / Chorak / Ixtiyoriy oraliq |
| Xodim | Ko'p tanlov |
| Region | Toshkent, Vodiy, Buxoro, Xorazm, Samarqand, Surxondaryo… |
| Mahsulot turi | 4–5 tur (LLM transkriptdan aniqlaydi) |
| Call natijasi | Zakaz / Follow-up / Rad / Faqat ma'lumot |
| Ball diapazoni | Slider 0–100 |
| Red flag | Bor / Yo'q / Tur bo'yicha |
| Til | uz / ru / aralash |
| Davomiylik | < 5 min / 5–15 / > 15 |
| Client bahosi | 1–5 |

---

## 7. Ma'lumotlar modeli (asosiy jadvallar)

```sql
-- Xodimlar
agents(id, moizvonki_employee_id, full_name, region, phone,
       voice_embedding vector(192), hired_at, is_active)

-- Clientlar
clients(id, name, shop_name, region, phone, telegram_user_id,
        telegram_group_id, assigned_agent_id, client_bias numeric,
        created_at, is_active)

-- Qo'ng'iroqlar
calls(id, moizvonki_call_id, agent_id, client_id, direction,
      started_at, duration_sec, audio_url, audio_storage_key,
      status, language_detected, created_at)

-- Transkriptlar
transcripts(call_id, asr_provider, raw_json jsonb, full_text text,
            wer_estimate numeric, quality text, embedding vector(1536),
            processed_at)

transcript_segments(id, call_id, speaker, speaker_confidence,
                    start_ms, end_ms, text)

-- Akustik xususiyatlar
audio_features(call_id, agent_rms_zscore, agent_f0_mean, agent_f0_std,
               jitter, shimmer, hnr, speech_rate_wpm, talk_ratio,
               interruption_count, overlap_ratio, long_pause_count,
               high_arousal_segments jsonb)

-- AI baholari
ai_scores(id, call_id, model, rubric_version, overall_score,
          blocks jsonb, red_flags jsonb, call_outcome,
          coaching_note, confidence, needs_human_review,
          scored_at, cost_usd)

-- Client so'rovnomalari
surveys(id, client_id, agent_id, period_start, period_end,
        token, channel, sent_at, opened_at, completed_at,
        expires_at, reminder_sent_at)

survey_responses(survey_id, csat smallint, resolution text,
                 comment text, comment_sentiment, responded_at,
                 response_time_sec)

-- Apellyatsiyalar (kalibratsiya uchun)
appeals(id, call_id, agent_id, reason, status,
        reviewer_id, human_score, resolved_at)

-- Gold set (kalibratsiya)
gold_labels(call_id, rater_id, blocks jsonb, overall_score, labeled_at)
```

**Indekslar:** `calls(agent_id, started_at)`, `ai_scores(call_id)`, `surveys(client_id, period_start)`, `transcripts` uchun `pgvector` HNSW indeks (semantik qidiruv: "qaysi call'larda narx e'tirozi bo'lgan?").

---

## 8. Texnologiya stack

### 8.0 Qisqa javob

**2 ta til, 4 ta servis.** Boshqa hech narsa kerak emas.

| Til | Nima uchun | Majburiymi |
|---|---|---|
| **Python 3.12** | Backend API + workerlar + audio tahlil + Telegram bot | ✅ **Majburiy** (sabab pastda) |
| **TypeScript** | Frontend dashboard | ✅ Amalda majburiy (React ekotizimi) |

**"Backend kerakmi?"** — Ha, **albatta kerak**, va u eng katta qism. Frontend faqat "oyna" — u hech narsa hisoblamaydi. Butun ish backendda:

```
Frontend (Next.js)  ← 20% ish. Faqat ko'rsatadi.
   │
   ▼  HTTP/JSON
Backend (Python)    ← 80% ish. Hamma narsa shu yerda:
   ├── MoyZvonki'dan qo'ng'iroqlarni tortib olish
   ├── Audio konvertatsiya, sukunatni kesish
   ├── ASR'ga yuborish, transkript olish
   ├── Diarizatsiya (kim gapirdi)
   ├── Prosodika hisoblash (ovoz toni, tempo)
   ├── LLM'ga yuborish, ballarni olish
   ├── Telegram botni boshqarish
   ├── So'rovnomalarni jadval bo'yicha yuborish
   ├── Statistika, normalizatsiya, bias tuzatish
   └── Bazaga yozish
```

Frontend'siz ham tizim ishlaydi (natijalar bazada bo'ladi). Backend'siz **hech narsa** ishlamaydi.

---

### 8.1 🔴 Nega aynan Python — bu tanlov emas, cheklov

Loyihaning yuragi — audio tahlil. Kerakli kutubxonalarning **hammasi faqat Python'da mavjud**:

| Vazifa | Kutubxona | Boshqa tilda bormi? |
|---|---|---|
| Diarizatsiya (kim gapirdi) | `pyannote.audio` | ❌ Yo'q |
| Prosodika (jitter, shimmer, HNR) | `praat-parselmouth`, `openSMILE` | ❌ Yo'q |
| Sukunat kesish (VAD) | `silero-vad` | ⚠️ Faqat Python/C++ |
| Spektral tahlil | `librosa` | ❌ Yo'q |
| Ovoz izi (agent identifikatsiyasi) | `speechbrain` | ❌ Yo'q |
| Whisper fine-tune (kelajakda) | `transformers` + PyTorch | ❌ Yo'q |

> **Xulosa:** jamoangiz PHP, Java yoki .NET bilsa ham, **audio worker baribir Python'da yoziladi**. Savol faqat shu: qolgan qismini ham Python'da yozamizmi (oddiy, 1 til) yoki ikkinchi tilda (murakkab, 2 til, 2 xil deploy)?
>
> **Tavsiyam: hammasini Python'da.** Jamoa kichik (2–3 kishi), bitta til = kamroq muammo.

---

### 8.2 To'liq stack — qatlama-qatlam

#### Backend (Python 3.12)

| Komponent | Tanlov | Nega |
|---|---|---|
| **Web framework** | **FastAPI** | Async (bir vaqtda ko'p ASR/LLM so'rovi), avtomatik OpenAPI hujjat → frontend tiplari avtomatik generatsiya bo'ladi |
| **Validatsiya / modellar** | **Pydantic v2** | LLM structured output sxemasi bilan **bir xil modellar** ishlatiladi — ikki marta yozmaymiz |
| **ORM** | **SQLAlchemy 2.0** + **Alembic** | Migratsiyalar, tip xavfsizligi |
| **Queue (workerlar)** | **Celery + Redis** | Uzoq vazifalar (ASR 30 sek, LLM 20 sek). Retry, rate limit, jadval — hammasi ichida |
| **Scheduler** | **Celery Beat** | So'rovnoma jadvali (14 kunlik kadans), tungi LLM batch, kunlik reconciliation |
| **HTTP klient** | **httpx** (async) | ASR/LLM API'lariga parallel so'rovlar |
| **LLM SDK** | **`anthropic`** | Batch API, prompt caching, structured output — hammasi qo'llab-quvvatlanadi |
| **Telegram bot** | **aiogram 3.x** | Async, FSM (so'rovnoma bosqichlari) ichida, deep-link qo'llab-quvvatlaydi |
| **Test** | **pytest** + `pytest-asyncio` | |

> **Muqobil:** agar jamoa **Django** bilsa — Django + DRF + Celery ham to'g'ri tanlov. Bonus: **Django Admin bepul** keladi, ya'ni agentlar/clientlar/rubrikalarni boshqarish paneli 0 kod bilan tayyor. Bu real 1–2 hafta tejaydi. FastAPI tezroq va zamonaviyroq, Django ko'proq "batareyka" bilan keladi. Ikkalasi ham to'g'ri.

#### Audio pipeline (Python — alohida worker)

```python
# requirements: audio worker
ffmpeg-python          # format konvertatsiya, Opus siqish
silero-vad             # sukunat kesish (ASR xarajatini 15-25% kamaytiradi)
pyannote.audio>=3.1    # diarizatsiya (agar ASR provayderi bermasa)
librosa                # RMS, spektral xususiyatlar
praat-parselmouth      # F0, jitter, shimmer, HNR
opensmile              # eGeMAPS to'plami
speechbrain            # ovoz izi → agent identifikatsiyasi
numpy, scipy
```

#### Frontend (TypeScript)

| Komponent | Tanlov | Nega |
|---|---|---|
| **Framework** | **Next.js 15** (App Router) | React ekotizimi, SSR, O'zbekistonda dasturchi topish oson |
| **Til** | **TypeScript** | Backend'dan OpenAPI orqali tiplar generatsiya qilinadi → xato kamayadi |
| **Stillar** | **Tailwind CSS 4** | Tez, dizayner shart emas |
| **UI komponentlar** | **shadcn/ui** | Tayyor jadval, modal, form, dropdown — bepul, kod sizniki |
| **Jadvallar** | **TanStack Table** | Saralash, filtrlash, virtualizatsiya (11,700 qator uchun kerak) |
| **Grafiklar** | **Recharts** | Trend chiziqlari, bar chart — yetarli |
| **Ma'lumot olish** | **TanStack Query** | Cache, refetch, loading holatlari |
| **Audio player** | **wavesurfer.js v7** + regions plugin | Waveform + red flag'larni rangli belgilash + timestamp'ga sakrash |
| **Auth** | **JWT (httpOnly cookie)** FastAPI'dan | 20 foydalanuvchi — Clerk/Auth0 ortiqcha |

> **Muqobil:** Vue/Nuxt ham to'liq mos. Agar jamoa Vue bilsa — o'zgartirmang. **Django tanlansa** — Django Templates + HTMX ham yetarli (frontend dasturchi umuman kerak emas), lekin audio player va interaktiv grafiklar biroz qiyinroq bo'ladi.

#### Ma'lumotlar va infratuzilma

| Komponent | Tanlov | Nega |
|---|---|---|
| **Baza** | **PostgreSQL 16 + pgvector** | Strukturali ma'lumot + semantik qidiruv bitta bazada |
| **Cache / broker** | **Redis 7** | Celery broker + sessiya cache |
| **Object storage** | **Cloudflare R2** yoki **MinIO** | R2: $0.015/GB, **egress bepul** → 150 GB ≈ $2.3/oy. MinIO: o'z serveringizda |
| **Reverse proxy** | **Caddy** | Avtomatik HTTPS, 5 qatorli config (Nginx'dan sodda) |
| **Konteynerlar** | **Docker + Docker Compose** | |
| **CI/CD** | **GitHub Actions** | |
| **Xatolar** | **Sentry** (bepul tarif yetarli) | |
| **Uptime** | **Uptime Kuma** (self-host, bepul) | |
| **Server** | Hetzner / Contabo VPS, 4–8 GB RAM | ~$20–40/oy |

---

### 8.3 ⚡ Muhim: GPU kerakmi yoki yo'qmi — ASR tanlovi hal qiladi

Bu stack va ops yukiga katta ta'sir qiladi:

| ASR tanlovi | Diarizatsiya | **GPU kerakmi?** | Ops murakkabligi |
|---|---|---|---|
| **ElevenLabs Scribe** | ✅ ichida | ❌ **YO'Q** | 🟢 Bitta oddiy VPS yetarli |
| Groq Whisper | ❌ yo'q | ✅ **HA** (pyannote uchun) | 🔴 GPU server + drayverlar + monitoring |
| Kotib | ❌ yo'q | ✅ HA | 🔴 Xuddi shunday |

> **Bu 4-bo'limdagi $201/oy farqdan muhimroq.** Scribe tanlansa — butun tizim bitta $40/oy VPS'da ishlaydi, GPU infratuzilmasi umuman kerak emas. Groq tanlansa — GPU server, CUDA, drayver versiyalari, VRAM monitoringi qo'shiladi. Kichik jamoa uchun bu bir necha hafta qo'shimcha ish.
>
> **Prosodika CPU'da ishlaydi** — u GPU talab qilmaydi.

---

### 8.4 Repozitoriya strukturasi (monorepo)

```
zvonki/
├── apps/
│   ├── api/                 # FastAPI — REST API, auth, dashboard uchun endpointlar
│   ├── worker/              # Celery — barcha fon vazifalari
│   │   ├── tasks/ingest.py     # MoyZvonki → storage
│   │   ├── tasks/audio.py      # ffmpeg, VAD, prosodika
│   │   ├── tasks/asr.py        # transkripsiya + diarizatsiya
│   │   ├── tasks/scoring.py    # LLM batch baholash
│   │   └── tasks/surveys.py    # so'rovnoma jadvali
│   ├── bot/                 # aiogram — Telegram bot
│   └── web/                 # Next.js — dashboard
├── packages/
│   └── core/                # Umumiy: Pydantic modellar, rubrika sxemasi,
│                            #   ASR adapter protokoli, DB modellari
├── infra/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   └── migrations/          # Alembic
├── ml/
│   ├── benchmark/           # Bosqich 0: ASR WER/DER o'lchash skriptlari
│   ├── calibration/         # Gold set, MAE hisoblash
│   └── finetune/            # Kelajak: Whisper fine-tune
└── docs/
    ├── PLAN.md
    └── rubric_v1.md
```

`api`, `worker`, `bot` — bir xil Python muhitni va `packages/core` ni bo'lishadi. Ya'ni **bitta `pyproject.toml`, bitta virtualenv**, uchta ishga tushirish nuqtasi.

---

### 8.5 Agar jamoangiz boshqa til bilsa

| Jamoa biladi | Moslashtirish | Python baribir kerakmi? |
|---|---|---|
| **PHP / Laravel** | Laravel: API + Inertia dashboard + Horizon queue + Telegram bot | ✅ Ha — audio worker alohida Python mikroservis (HTTP yoki Redis orqali) |
| **Node / TypeScript** | NestJS yoki Fastify + BullMQ + grammY bot. Frontend baribir Next.js | ✅ Ha — audio worker Python |
| **Java / Spring** | Ishlaydi, lekin 2–3 kishilik jamoa uchun og'ir | ✅ Ha |
| **.NET** | Xuddi shunday | ✅ Ha |
| **Python** | ✅ Hammasi bitta tilda | — |

**Universal qoida: audio worker = Python.** Undan qochib bo'lmaydi.

---

### 8.6 ❌ Nima ishlatmaslik kerak (ortiqcha murakkablik tuzoqlari)

Kichik jamolar shu yerda oylab vaqt yo'qotadi:

| Ishlatmang | Nega | O'rniga |
|---|---|---|
| **Kubernetes** | 20 foydalanuvchi, 4 servis | Docker Compose |
| **Kafka / RabbitMQ** | Kuniga 450 xabar — bu hech narsa | Redis + Celery |
| **TimescaleDB** | Yiliga 140,000 qator — oddiy Postgres uchun kichik | Oddiy PostgreSQL + indekslar |
| **Elasticsearch** | Qo'shimcha servis, qo'shimcha RAM | Postgres full-text + pgvector |
| **Pinecone / Weaviate** | Alohida vektor bazasi shart emas | pgvector (bir xil bazada) |
| **GraphQL** | Bitta klient, bitta jamoa | REST + OpenAPI |
| **Mikroservislar** (4 tadan ko'p) | Distributed tracing, versiyalash muammolari | Monorepo + 4 servis |
| **O'z ML modelingizni 1-kundan trening qilish** | 6 oy ketadi | Avval API, ma'lumot yig'ing, keyin fine-tune |

---

### 8.7 Jamoa tarkibi

| Rol | Yuklama | Nima qiladi |
|---|---|---|
| **Python backend** | 100% | API, workerlar, ASR/LLM integratsiya, bot — **eng katta qism** |
| **Frontend (Next.js)** | 100% (3–4 hafta), keyin 30% | Dashboard, 4 ta asosiy ekran |
| **ML/Data** | 50% | ASR benchmark, kalibratsiya, prosodika sozlash, rubrika iteratsiyasi |
| **Savdo direktori** | 25% | Rubrika, gold set baholash, natijalarni talqin qilish |

**Minimal ishlaydigan jamoa: 2 kishi** — 1 kuchli Python backend (ML ni ham o'zi qiladi) + 1 frontend.
**Qulay: 3 kishi.**

Agar tashqi jamoa yollasangiz — **Python backend dasturchisini birinchi yollang**, frontend'ni 2 oydan keyin qo'shsangiz ham bo'ladi (avval pipeline ishlashi kerak, ko'rsatadigan narsa bo'lishi uchun).

---

## 9. Bosqichma-bosqich reja (Roadmap)

**Umumiy muddat: 14 hafta.** Jamoa: 1 backend, 1 frontend, 0.5 ML/data muhandis, 0.25 savdo direktori (rubrika uchun).

### 🔹 Bosqich 0 — Discovery va Benchmark (2 hafta)
> **Bu bosqichni o'tkazib yubormang. U keyingi barcha qarorlarni belgilaydi.**

| # | Vazifa | Natija |
|---|---|---|
| 0.1 | MoyZvonki API kirish, test call'lar yuklab olish | Ishlaydigan API ulanish |
| 0.2 | 30 ta real call tanlash (regionlar bo'yicha) | Benchmark to'plami |
| 0.3 | Qo'lda "gold" transkript yozish | Etalon matnlar |
| 0.4 | **ASR benchmark:** Groq turbo / Groq large-v3 / ElevenLabs Scribe / Kotib | WER + DER jadvali, **ASR qarori** |
| 0.5 | Rubrika v1 ni savdo direktori bilan yozish | Tasdiqlangan rubrika hujjati |
| 0.6 | Kotib/Deepsales/Muxlisa'dan rasmiy narx so'rash (zaxira variant sifatida) | Build vs buy raqamlari tasdiqlanadi |
| 0.7 | ~~Huquqiy maslahat~~ → ✅ D2 bilan hal qilindi, o'rniga: **VAD (sukunat kesish) prototipi** | ASR hajmini 15–25% kamaytirish tasdiqlanadi |
| 0.8 | 15 xodim + N client ro'yxati, Telegram guruh inventarizatsiyasi | Mapping jadvali |
| 0.9 | Telefonlar auditi: qaysi modellar, Android/iPhone, yozib olish ishlaydimi | Qamrov foizi (%) |

**🚦 Gate:** ASR WER > 25% bo'lsa — to'xtang va strategiyani qayta ko'rib chiqing.

### 🔹 Bosqich 1 — Ingest Pipeline (2 hafta)
| # | Vazifa |
|---|---|
| 1.1 | MoyZvonki webhook + `calls.list` reconciliation job |
| 1.2 | Audio yuklab olish + object storage (30 kunlik limitni yopish) |
| 1.3 | PostgreSQL sxemasi + migratsiyalar |
| 1.4 | Celery queue infratuzilmasi |
| 1.5 | ASR worker (tanlangan provider) + retry/error handling |
| 1.6 | Diarizatsiya + agent identifikatsiyasi (voice embedding) |
| 1.7 | Monitoring: kunlik call'lar soni, muvaffaqiyat foizi |

**✅ Deliverable:** Har kuni 450 ta call avtomatik transkripsiya qilinadi va bazada saqlanadi.

### 🔹 Bosqich 2 — AI Baholash (3 hafta)
| # | Vazifa |
|---|---|
| 2.1 | Rubrika → LLM prompt (structured output schema bilan) |
| 2.2 | Prompt caching sozlash (rubrika bayt-barqaror) |
| 2.3 | Batch API integratsiyasi (tungi job) |
| 2.4 | Haiku pre-filter (arzimas call'larni chiqarish) |
| 2.5 | Prosodika worker (librosa + parselmouth + openSMILE) |
| 2.6 | Prosodika xulosasini LLM promptiga qo'shish |
| 2.7 | **Kalibratsiya:** 150 ta gold call, MAE/korrelyatsiya o'lchash |
| 2.8 | Rubrika iteratsiyasi (kalibratsiya natijasiga ko'ra) |

**🚦 Gate:** MAE < 8 ball VA korrelyatsiya > 0.75 VA red flag recall > 90%. Aks holda rubrikani qayta ishlang.

**✅ Deliverable:** Har call avtomatik baholanadi, sifat o'lchangan va hujjatlashtirilgan.

### 🔹 Bosqich 3 — Dashboard (3 hafta)
| # | Vazifa |
|---|---|
| 3.1 | Auth + rollar (boss / menejer / xodim / QA) |
| 3.2 | Ekran 1: Umumiy ko'rinish + filtrlar |
| 3.3 | Ekran 2: Xodim profili |
| 3.4 | Ekran 3: Call detali (player + transkript + baholash) |
| 3.5 | Apellyatsiya oqimi |
| 3.6 | Eksport (Excel/PDF hisobotlar) |

**✅ Deliverable:** Menejerlar tizimni real ishda ishlatishni boshlaydi.

### 🔹 Bosqich 4 — Client Reyting Tizimi (3 hafta)
| # | Vazifa |
|---|---|
| 4.1 | Telegram bot: guruh registratsiyasi + mapping |
| 4.2 | Deep-link + token tizimi |
| 4.3 | Shaxsiy chatda so'rovnoma FSM |
| 4.4 | Scheduler (staggered 14-kunlik kadans + suppression) |
| 4.5 | Eskiz SMS fallback |
| 4.6 | **Pilot: 30 ta client** (2 hafta kuzatish) → response rate o'lchash |
| 4.7 | Bias normalizatsiyasi + minimal N logikasi |
| 4.8 | Ekran 4: Client fikrlari |
| 4.9 | To'liq rollout (500 client) |

**🚦 Gate:** Pilotda response rate > 30% bo'lsa davom eting. Past bo'lsa — xabar matnini, vaqtini, savol sonini o'zgartirib qayta sinang.

**✅ Deliverable:** Ikki xil baho (AI + client) bitta dashboardda.

### 🔹 Bosqich 5 — Yetuklashtirish (1 hafta + davomiy)
| # | Vazifa |
|---|---|
| 5.1 | Alert'lar: red flag → menejerga Telegram xabar |
| 5.2 | Haftalik avtomatik hisobot (boss'ga Telegram/email) |
| 5.3 | Divergensiya paneli (gaming aniqlash) |
| 5.4 | Semantik qidiruv ("narx e'tirozi bo'lgan call'lar") |
| 5.5 | Xodimlar bilan tizimni tanishtirish sessiyasi |

**Davomiy (har oy):** rubrika review, gold set kengaytirish, ASR fine-tune ma'lumot yig'ish.

---

## 10. Risklar va mitigatsiya

| # | Risk | Ehtimol | Ta'sir | Mitigatsiya |
|---|---|---|---|---|
| R1 | **O'zbek dialektlarida ASR WER yuqori** | Yuqori | Kritik | Bosqich 0 benchmark. Gibrid ASR. Uzoq muddatda o'z ma'lumotimiz bilan fine-tune |
| R2 | **uz/ru kod-almashinuv** (bir gapda ikki til) | Yuqori | Yuqori | Multilingual model tanlash. Til aniqlash segment darajasida, call darajasida emas |
| R3 | **MoyZvonki 30 kunlik limit — yozuv yo'qoladi** | O'rta | Yuqori | Webhook + kunlik reconciliation. Monitoring alert: "24 soatda 0 ta yozuv keldi" |
| R4 | **Client survey response rate past (<20%)** | O'rta | Yuqori | Pilot avval. A/B test: xabar matni, vaqt, savol soni. Rag'bat (chegirma, sovg'a) qo'shish |
| R5 | **Xodimlar qarshiligi ("kuzatuv")** | Yuqori | Yuqori | ⬇️ Pastda alohida bo'lim |
| R6 | **AI noto'g'ri ayblov (false red flag)** | O'rta | Yuqori | Prosodika yolg'iz ball bermaydi. Har red flag'da evidence. Apellyatsiya majburiy. Precision > 85% talab |
| R7 | **Ma'lumot lokalizatsiyasi qonuni buzilishi** | O'rta | Kritik | ⬇️ Pastda alohida bo'lim. Yuridik maslahat Bosqich 0'da |
| R8 | **iPhone'da yozib olish ishlamaydi** | O'rta | O'rta | Xodimlarni Android'ga o'tkazish yoki VoIP PBX'ga o'tish |
| R9 | **Shovqinli muhit (do'kon, bozor)** | Yuqori | O'rta | ASR'ga noise suppression preprocessing. Sifat past bo'lgan call'lar `needs_human_review` |
| R10 | **Hajm oshib xarajat portlashi** | Past | O'rta | Har oy xarajat monitoringi. Haiku pre-filter. Batch API. Budget alert |
| R11 | **Xodim client'ga "5 qo'ying" deyishi** | O'rta | O'rta | Divergensiya paneli. Anonim baho. Statistik anomaliya aniqlash |
| R12 | **Rubrika savdo jarayoniga mos emas** | O'rta | Yuqori | Savdo direktori Bosqich 0'da to'liq ishtirok etadi. Har oy review |

### R5 tafsiloti: Xodimlar qarshiligi (eng ko'p e'tibordan chetda qoladigan risk)

**Muammo:** "Bizni kuzatishyapti" hissi → moral tushishi, eng yaxshi xodimlarning ketishi. Bu texnik emas, tashkiliy risk va **loyihani o'ldirishi mumkin**.

**Mitigatsiya rejasi:**
1. **Ochiq e'lon.** Tizim yashirin ishga tushirilmasin. Boshlashdan oldin yig'ilish: nima o'lchanadi, nega, natija qanday ishlatiladi.
2. **Koučing, jazo emas.** Birinchi 3 oy — ballar KPI/bonusga **umuman ta'sir qilmaydi**. Faqat trening uchun.
3. **Xodim o'z ballini ko'radi.** Shaffoflik ishonch beradi.
4. **Apellyatsiya huquqi.** Har baho ustidan e'tiroz bildirish mumkin.
5. **Ijobiy ishlatish.** Eng yaxshi call'lar "namuna" sifatida boshqalarga ko'rsatiladi. Oylik "eng yaxshi qo'ng'iroq" mukofoti.
6. **Client bahosini ham ko'rsating** — bu xodimga "mening client'im mendan rozi" degan ijobiy signal beradi.

---

## 11. Huquqiy va etik masalalar

### 11.1 Ma'lumotlar lokalizatsiyasi — 🔴 MUHIM O'ZGARISH

**Vaziyat:**
- **ZRU-547** ("Shaxsga doir ma'lumotlar to'g'risida", 2019) dastlab O'zbekiston fuqarolarining barcha shaxsiy ma'lumotlarini **O'zbekiston hududidagi serverlarda** saqlashni talab qilgan.
- **2026-yil 26-martda** qonunga tuzatishlar kiritildi (№1125, 27-martdan kuchga kirdi): mandatory lokalizatsiya **yumshatildi** — ma'lumotlarning ko'p qismi endi xalqaro serverlarda saqlanishi mumkin.
- **LEKIN:** **biometrik va genetik ma'lumotlar** hamda telekom operatorlari foydalanuvchilarining ma'lumotlari **hali ham O'zbekistonda saqlanishi shart**.

**🚨 Kritik savol: ovoz yozuvi biometrik ma'lumotmi?**

Ovoz izi (voiceprint) ko'p yurisdiksiyalarda biometrik ma'lumot hisoblanadi. Agar O'zbekiston regulyatori shunday talqin qilsa:
- ❌ Call yozuvlarini ElevenLabs (AQSh) yoki boshqa chet el ASR'iga yuborish **noqonuniy** bo'lishi mumkin
- ❌ Transkriptlarni Anthropic API'ga yuborish ham savol ostida (garchi matn biometrik emas)

**📌 Sizning qaroringiz (D2):** bu masala ustuvor emas, chet el API'lari ishlatiladi, ustuvorlik — sifat va arzonlik.

Men riskni ko'rsatib o'tdim, siz qaror qabul qildingiz — reja shunga muvofiq tuzilgan. Quyidagilar **majburiy emas, lekin arzon sug'urta** sifatida tavsiya etiladi (qo'shimcha xarajat yo'q, faqat kod):

1. **ASR/LLM adapter pattern** (3.2-bo'limda) — provayder `.env` orqali almashadi. Ertaga auditor talab qilsa yoki qonun o'zgarsa, 1–2 kunda mahalliy provayderga o'tiladi.
2. **Pseudonimizatsiya qatlami** — transkript LLM'ga ketishdan oldin ismlar/telefon/manzillar maskalanadi. Bu **bepul** va bonus sifatida prompt tokenlarini kamaytiradi.
3. **Zero-retention rejimi** — Anthropic va boshqa provayderlarda so'rov bo'yicha yoqiladi (ma'lumot saqlanmaydi). Bepul, bir marta sozlanadi.
4. Kelajakda kerak bo'lsa: yuridik maslahat + Davlat Personalizatsiya Markazi bilan maslahatlashuv + ma'lumotlar bazasini Davlat reyestrida ro'yxatdan o'tkazish.

**Arxitektura (D2 qaroriga muvofiq — tavsiya, majburiy emas):**
```
┌─────────────────────────────────────────────────────────────┐
│  BIZNING SERVER (joylashuvi ixtiyoriy — narx/latency bo'yicha)│
│  • Audio arxiv (Opus 16kbps, object storage)                │
│  • PostgreSQL (client PII: ism, telefon, do'kon)            │
│  • Ovoz embeddinglari                                        │
└─────────────┬───────────────────────────────────────────────┘
              │  Pseudonimizatsiya qatlami (bepul, tavsiya)
              │  • Ismlar → [CLIENT_1], [AGENT_2]
              │  • Telefon raqamlari → [PHONE]
              │  • Manzillar → [ADDRESS]
              ▼
┌─────────────────────────────────────────────────────────────┐
│  CHET EL API — ✅ D2 bo'yicha ruxsat etilgan                 │
│  • ASR: Groq / ElevenLabs (benchmark g'olibi)               │
│  • LLM: Anthropic Claude (pseudonimizatsiyalangan transkript)│
│  • Zero-retention rejimi yoqilgan                            │
└─────────────────────────────────────────────────────────────┘
```

**Agar kelajakda to'liq lokalizatsiya talab qilinsa** → adapter almashtiriladi: self-hosted Whisper + self-hosted LLM (Qwen 3 / Llama) O'zbekiston DC'sida, ~$400–600/oy GPU. Kod o'zgarmaydi.

### 11.2 Roziliklar (consent)

| Kim | Nima uchun rozilik | Qanday |
|---|---|---|
| **Savdo xodimi** | Ovozi yozib olinishi, AI tomonidan baholanishi | Mehnat shartnomasiga ilova + alohida imzo |
| **Client** | Qo'ng'iroq yozib olinishi + so'rovnoma yuborilishi | Call boshida ovozli xabar ("Suhbat sifat nazorati uchun yoziladi") + shartnomada band |
| **Client (Telegram)** | Botga ma'lumot berish | Bot birinchi ochilganda qisqa maxfiylik matni + "Roziman" tugmasi |

### 11.3 Ma'lumotlarni saqlash muddati (retention policy)

| Ma'lumot | Saqlash | Sabab |
|---|---|---|
| Xom audio | **12 oy** | Apellyatsiya va kalibratsiya uchun. Keyin o'chiriladi |
| Transkript | **24 oy** | Trend tahlili |
| AI ballari (aggregate) | **Cheksiz** | Statistika |
| Client izohlari | **24 oy** | |
| Client PII | Shartnoma amal qilgunicha + 1 yil | |

Avtomatik o'chirish job'i yoziladi.

### 11.4 Etik chegaralar
- ❌ Tizim **avtomatik ishdan bo'shatish** qarorini qabul qilmasin. Har qanday HR qarori odam tomonidan, dalillar bilan.
- ❌ Xodimning shaxsiy hayoti haqidagi ma'lumot (agar call'da tasodifan aytilsa) baholashda ishlatilmasin — LLM promptiga aniq ko'rsatma.
- ✅ Xodim o'z ma'lumotlarini ko'rish va tuzatish huquqiga ega.

---

## 12. Muvaffaqiyat mezonlari (KPI)

### Texnik KPI
| Metrika | Maqsad | O'lchash |
|---|---|---|
| Pipeline qamrovi | > 97% call'lar avtomatik qayta ishlanadi | Kunlik |
| ASR WER | < 20% (real call'larda) | Choraklik benchmark |
| AI–inson kelishuvi (MAE) | < 8 ball / 100 | Choraklik gold set |
| Red flag recall | > 90% | Choraklik |
| Red flag precision | > 85% | Choraklik |
| Pipeline kechikishi | < 12 soat (kechqurun call → ertalab baho) | Kunlik |
| Xarajat | < $0.01 / daqiqa | Oylik |

### Biznes KPI
| Metrika | Baza | 6 oydan keyin maqsad |
|---|---|---|
| O'rtacha AI ball | o'lchanadi | +10% |
| Client CSAT | o'lchanadi | > 4.3 / 5.0 |
| Survey response rate | — | > 35% |
| Red flag'lar soni | o'lchanadi | −50% |
| Konversiya (call → zakaz) | o'lchanadi | +5–10% |
| Xodimlar tizimga ishonchi | so'rovnoma | > 70% "foydali" |

---

## 13. ❓ Ochiq savollar (sizdan aniqlashtirish kerak)

> ✅ **Javob berilganlar (v1.1):**
> — *Client baholash usuli* → gibrid model (D1)
> — *Chet el API'lari / lokalizatsiya* → cheklov yo'q, sifat+arzonlik ustuvor (D2)
> — *CRM/SAP integratsiyasi* → kerak emas, natija transkriptdan aniqlanadi (D3)

Qolgan savollar, muhimlik tartibida:

### A. Hajm va ma'lumot (hisob-kitoblarga to'g'ridan-to'g'ri ta'sir qiladi)
1. **Aniq nechta savdo xodimi bor hozir?** 12 mi, 15 mi, 18 mi? Yil oxirigacha o'sish rejasi bormi?
2. **Aniq nechta faol client bor?** (Telegram guruhi bor bo'lganlari). 200 mi, 500 mi, 1000 mi?
3. **Bitta xodim o'rtacha nechta client bilan ishlaydi?**
4. **Qo'ng'iroqlarning taxminan necha foizi o'zbek, necha foizi rus tilida?** Aralash gapirish qanchalik keng tarqalgan?
5. **Ish kunlari:** haftada 6 kunmi (shanba ham)? Oyiga necha ish kuni?

### B. Texnik infratuzilma
6. **MoyZvonki hozir ishlayaptimi?** Qancha vaqtdan beri? API kaliti bormi?
7. **Barcha xodimlarda Android telefonmi?** iPhone bor bo'lsa nechta? *(iPhone'da qo'ng'iroq yozib olish Apple cheklovi sababli ishlamaydi — bu jiddiy to'siq)*
8. **Yozuvlar qayerda saqlanmoqda hozir?** MoyZvonki bulutidami yoki boshqa joydami? 30 kundan eski yozuvlar bormi?
9. ~~CRM integratsiyasi~~ → ✅ **Hal qilindi (D3):** kerak emas
10. **IT jamoangiz bormi?** Nechta dasturchi? Yoki tashqi jamoa yollaysizmi?

### C. Client baholash dizayni
11. **Telegram guruhlarida odatda nechta odam bor?** Client tomondan 1 kishimi yoki bir nechtami (masalan, do'kon egasi + sotuvchi)?
12. **Guruhlarni kim yaratgan/boshqaradi?** Botni guruhga qo'shish uchun admin huquqi kimda?
13. **Client'lar bot bilan shaxsiy chatga o'tishga rozi bo'ladi deb o'ylaysizmi?** Yoki bu ham to'siq bo'ladimi?
14. **Baholash uchun rag'bat (chegirma, bonus) berishga tayyormisiz?** Bu response rate'ni 2× oshirishi mumkin, lekin bahoni buzishi ham mumkin.
15. **14 kunlik davr sizga mos keladimi?** Yoki 10 kun / 1 oy afzalroqmi?

### D. Baholash mazmuni
16. **Savdo skriptingiz yozilganmi?** Bo'lsa — menga bering, rubrikani aynan shunga moslashtiraman.
17. **4–5 tur mahsulot nima?** (umumiy nomlari) — LLM mahsulot nomlarini tanishi uchun
18. **Hozir xodimlarni qanday baholaysiz?** (faqat savdo hajmimi? boshqa mezonlar bormi?)
19. **Ballar bonus/KPI ga bog'lanadimi?** Qachondan boshlab?
20. **"Red flag" deb nimani hisoblaysiz?** Menikidan tashqari yana nima muhim? (masalan, raqobatchi haqida gapirish, narx aytish qoidalari)

### E. Byudjet va muddat
21. **Oylik operatsion byudjet chegarangiz qancha?** ($330 / $550 / $700 — qaysi stsenariy sizga mos?)
22. **Ishlab chiqish byudjeti va muddati?** Qachon ishga tushishi kerak?
23. **Kim ishlab chiqadi?** Siz o'zingizmi, ichki jamoami, yoki tashqi?
24. **Bir martalik $2,500–3,500 apparat xarajatiga (GPU ish stansiyasi) tayyormisiz?** Bu 9 oyda qoplanadi va uzoq muddatda ASR xarajatini ≈$0 qiladi

### F. Huquqiy va tashkiliy
25. ~~Chet el API'lari~~ → ✅ **Hal qilindi (D2):** ruxsat berilgan
26. **Client'lar bilan shartnomada qo'ng'iroq yozib olish haqida band bormi?** *(Bu qonuniy talab emas, lekin nizo chiqsa himoya bo'ladi)*
27. **Xodimlar bilan qanday muloqot qilamiz?** Tizim ochiq e'lon qilinadimi yoki jim ishga tushiriladimi? *(Tavsiyam — ochiq, sabablari 10-bo'lim R5'da)*

---

## 14. Keyingi qadamlar (darhol bajariladigan)

| # | Ish | Kim | Muddat |
|---|---|---|---|
| 1 | **13-bo'limdagi qolgan savollarga javob berish** | Siz | 2–3 kun |
| 2 | MoyZvonki API kalitini olish + test so'rov | Siz + IT | 1 kun |
| 3 | **30 ta real call yuklab olish** (6 regiondan 5 tadan, uz/ru/aralash) | Siz | 2 kun |
| 4 | Telefonlar auditi (Android/iPhone, yozib olish ishlaydimi) | Siz | 1 kun |
| 5 | Kotib / Deepsales / Muxlisa / ovozai.uz'ga narx so'rovi (1,560 soat/oy hajm bilan) | Siz | 2 kun |
| 6 | **Savdo skriptini va mahsulot nomlari ro'yxatini berish** | Siz | 1 kun |
| 7 | Savdo direktori bilan rubrika v1 sessiyasi (2 soat) | Siz + savdo dir. | 1 hafta |
| 8 | ASR benchmark o'tkazish (Groq / Scribe / Kotib) | Dev | 1 hafta |

> **Eng tez qadam:** 3-punkt (30 ta call). Bu bo'lmasa boshqa hech narsa boshlanmaydi — ASR qarori, rubrika kalibratsiyasi, xarajat prognozi hammasi shu ma'lumotga bog'liq.

---

## Ilova A — Manbalar

**AI / ASR / LLM:**
- [ElevenLabs Scribe — Speech to Text](https://elevenlabs.io/docs/overview/capabilities/speech-to-text) · [Uzbek STT](https://elevenlabs.io/speech-to-text/uzbek) · [API narxlari](https://elevenlabs.io/pricing/api)
- [KotibAI Integration API — STT](https://developer.kotib.ai/docs/stt/) · [Kotib Analytics](https://analytics.kotib.ai/en)
- [Muxlisa AI (Uzinfocom)](https://muxlisa.uz/en) · [Muxlisa AI loyihasi](https://uzinfocom.uz/en/projects/muxlisa-ai-ru-3) · [Gazeta.uz maqolasi](https://www.gazeta.uz/ru/2025/11/13/uzinfocom/)
- [Groq Speech-to-Text (Whisper) narxlari va imkoniyatlari](https://apio.sh/apis/groq-speech-to-text) · [Groq pricing 2026](https://www.cloudzero.com/blog/groq-pricing/) · [Whisper API narxlari taqqoslash](https://tokenmix.ai/blog/whisper-api-pricing)
- [Deepgram narxlari 2026](https://diyai.io/ai-tools/speech-to-text/deepgram-pricing-2026/) · [Nova-3 tafsilotlari](https://convertaudiototext.com/blog/deepgram-nova-3-explained)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Whisper self-hosting benchmark (Salad)](https://blog.salad.com/whisper-large-v3/) · [Self-hosted Whisper 2026 qo'llanma](https://www.digitalapplied.com/blog/local-speech-to-text-whisper-self-hosted-transcription-2026)
- [openSMILE hujjatlari](https://audeering.github.io/opensmile/get-started.html) · [openSMILE (audEERING)](https://www.audeering.com/research/opensmile/)
- [Kotib uzbek_stt_v1 (HuggingFace)](https://huggingface.co/Kotib/uzbek_stt_v1) · [Qwen3-ASR Uzbek](https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2)
- Claude API narxlari va Batch/caching — Anthropic rasmiy hujjatlari

**Integratsiyalar:**
- [MoiZvonki API qo'llanmasi](https://www.moizvonki.ru/guide/api/) · [Tariflar](https://www.moizvonki.ru/price/) · [Imkoniyatlar](https://www.moizvonki.ru/features/)
- [Eskiz.uz SMS tariflari](https://eskiz.uz/oz/sms) · [Eskiz API (Postman)](https://documenter.getpostman.com/view/663428/TVK5eMco)
- [Telegram Bot API — Polls](https://core.telegram.org/api/poll) · [Polls 2.0](https://telegram.org/blog/polls-2-0-vmq) · [PollAnswer](https://docs.python-telegram-bot.org/telegram.pollanswer.html)

**So'rovnoma benchmarklari:**
- [WhatsApp vs SMS/Email survey response rates 2026](https://www.askyazi.com/articles/whatsapp-survey-response-rates-vs-email-sms-and-phone-the-2026-benchmarks)
- [Survey response rate benchmarks](https://www.askyazi.com/articles/survey-response-rates-a-complete-guide-to-nps-and-post-interaction-feedback) · [NPS/CSAT benchmarks](https://www.zonkafeedback.com/blog/product-feedback-benchmarks)

**Huquqiy:**
- [Uzbekistan dismantles strict data localization regime (Dentons, 2026-03)](https://www.dentons.com/en/insights/articles/2026/march/31/uzbekistan-dismantles-strict-data-localization-regime)
- [Uzbekistan amends personal data law (Kun.uz, 2026-03-27)](https://kun.uz/en/news/2026/03/27/uzbekistan-amends-personal-data-law-to-facilitate-global-payment-systems)
- [Personal Data Compliance in Uzbekistan (Legal500)](https://www.legal500.com/developments/thought-leadership/personal-data-compliance-in-uzbekistan/)
- [ZRU-547 to'liq matni](https://cis-legislation.com/document.fwx?rgn=116961)

**O'zbekistondagi raqobatchilar:**
- [Kotib AI — 100% call analysis (Daryo)](https://daryo.uz/en/2026/04/13/15-in-sales-how-analyzing-100-of-calls-is-transforming-call-centers-in-uzbekistan/)
- [ZorCall](https://zorcall.uz/) · [Techna](https://techna.uz/)
