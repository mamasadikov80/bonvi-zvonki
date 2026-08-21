"""Baholash prompti — MAHSULOTNING O'ZI.

Bu fayl ataylab quvurdan (pipeline) ajratilgan: promptni sozlash —
haftalik ish, quvur mantig'i esa deyarli o'zgarmaydi. Savdo direktori
matnni shu yerda tahrirlaydi, `pipeline` ga tegilmaydi.

Uchta qat'iy qoida:

1. **Prompt rubrikadan quriladi**, qo'lda takrorlanmaydi. Rubrika
   dashboarddan o'zgarsa prompt o'zi o'zgaradi — aks holda LLM eski
   mezon bo'yicha baholab, ball esa yangi rubrika bilan tekshirilardi.
2. **Tizim prompti bayt-ma-bayt barqaror** (PLAN.md 3.4 — prompt
   caching). Sana, qo'ng'iroq id, xodim ismi — hammasi FOYDALANUVCHI
   xabarida. Aks holda kesh hech qachon ishlamaydi va rubrika tokenlari
   har qo'ng'iroqda to'liq to'lanadi.
3. **Til: o'zbekcha.** Qo'ng'iroqlar o'zbek/rus aralash (kod-almashinuv),
   bu promptda ochiq aytiladi — aks holda model rus jumlalarini
   "tushunarsiz" deb belgilab, xodimni nohaq jazolaydi.
"""

from typing import Any

# ── Bloklar va red flag'lar matnga aylantiriladi ──────────────


def _render_blocks(blocks: list[dict[str, Any]]) -> str:
    """Rubrikani matnga aylantiradi.

    ⚠️ Har kriteriyada `optional` belgisi KO'RSATILADI. Modelga «bu
    mezonni taalluqli emas deb belgilash mumkin» degani aynan shu
    belgi orqali yetadi — busiz u qisqa suhbatda ham hamma mezonga
    nol qo'yishga majbur bo'lardi.
    """
    lines: list[str] = []
    for block in blocks:
        lines.append(
            f"\n### Blok «{block.get('label', block['key'])}» "
            f"(kalit: `{block['key']}`, maksimal {block.get('max', 0)} ball)"
        )
        for criterion in block.get("criteria", []):
            description = criterion.get("description") or ""
            belgi = (
                "  ⟨taalluqli bo'lmasa `na`⟩"
                if criterion.get("optional")
                else "  ⟨HAR DOIM baholanadi⟩"
            )
            lines.append(
                f"  · {criterion['id']} — {criterion.get('label', '')} "
                f"[0..{criterion.get('points', 0)} ball]{belgi}"
                + (f". {description}" if description else "")
            )
    return "\n".join(lines)


def _render_red_flags(red_flags: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for flag in red_flags:
        note = " — umumiy ball 0 ga tushadi" if flag.get("zeroes_score") else ""
        description = flag.get("description") or ""
        lines.append(
            f"  · `{flag['type']}` — {flag.get('label', '')} "
            f"({flag.get('penalty', 0)} ball{note})"
            + (f". {description}" if description else "")
        )
    return "\n".join(lines)


# ── Tizim prompti ─────────────────────────────────────────────


#: Adminning qo'shimcha ko'rsatmasi uchun chegara (belgi).
#
# NEGA CHEGARA BOR. Bu matn HAR BIR qo'ng'iroqda promptga qo'shiladi,
# ya'ni uzunligi to'g'ridan-to'g'ri pulga aylanadi: 4000 belgi ≈ 1200
# token ≈ oyiga ~15 000 qo'ng'iroqda 18 mln kirish tokeni. Chegarasiz
# maydonga kimdir butun ish yo'riqnomasini joylashi mumkin va buni
# hech narsa to'smasdi.
MAX_EXTRA_RULES = 4000


def _render_extra_rules(extra_rules: str | None) -> str:
    """Adminning ko'rsatmalarini alohida bo'lim qilib qo'shadi.

    Bo'sh bo'lsa — BUTUN bo'lim tushib qoladi (sarlavha ham). Bo'sh
    sarlavha qoldirilsa model «bu yerda nimadir bo'lishi kerak edi» deb
    o'ylab, yo'q ko'rsatmani to'qib chiqarishi mumkin.
    """
    text = (extra_rules or "").strip()
    if not text:
        return ""
    # Boshida bitta bo'sh qator, oxirida ham — bo'lim atrofidagi
    # ajratish rubrika va qoidalar bo'limlaridagidek bo'lishi kerak,
    # aks holda markdown sarlavhalari bir-biriga yopishib qoladi va
    # model bo'limlar chegarasini xato o'qishi mumkin.
    return f"""
## KOMPANIYANING QO'SHIMCHA QOIDALARI

Quyidagilarni admin yozgan. Ular RUBRIKAGA QO'SHIMCHA: mavjud
kriteriyalar va red flag'larni bekor qilmaydi, balki nimaga alohida
e'tibor berishni ko'rsatadi.

{text}

⚠️ Yuqoridagi qoidalar javob SHAKLINI o'zgartirmaydi. Ular bilan
pastdagi ball qo'yish tartibi yoki JSON shakli o'rtasida ziddiyat
bo'lsa — PASTDAGISI ustun turadi.
"""


def build_system_prompt(
    rubric_blocks: list[dict[str, Any]],
    rubric_red_flags: list[dict[str, Any]],
    extra_rules: str | None = None,
) -> str:
    """Rubrikadan tizim promptini quradi.

    Faqat rubrikaga bog'liq — bir xil rubrika har doim bir xil matn
    beradi (prompt caching shuni talab qiladi). `extra_rules` ham
    rubrikaning bir qismi, ya'ni u o'zgarmaguncha matn ham o'zgarmaydi.

    ⚠️ ADMIN MATNI QAYERGA QO'YILADI — bu tasodifiy emas. U rubrikadan
    KEYIN, ball qo'yish qoidalari va JAVOB SHAKLIdan OLDIN turadi.
    Sababi: LLM ziddiyatda odatda keyingi ko'rsatmaga amal qiladi,
    demak format shartnomasi oxirida turishi kerak. Admin matni oxirga
    qo'yilsa, bexosdan yozilgan «javobni matn bilan tushuntir» degan
    gap JSON ni buzib, har bir baho validatsiyadan o'tmasdi — ya'ni
    bitta tahrir butun baholashni to'xtatardi.
    """
    parts = _sections(rubric_blocks, rubric_red_flags, extra_rules)
    return "".join(part["text"] for part in parts)


def split_system_prompt(
    rubric_blocks: list[dict[str, Any]],
    rubric_red_flags: list[dict[str, Any]],
    extra_rules: str | None = None,
) -> list[dict[str, Any]]:
    """Promptni nomlangan bo'laklar ro'yxati sifatida qaytaradi.

    ⚠️ `build_system_prompt` BILAN BITTA MANBADAN quriladi (`_sections`).
    Ikkita alohida funksiya yozilsa ular vaqt o'tib ajralib ketardi:
    admin panelda bir matn ko'rinardi, AI ga boshqasi ketardi — va bu
    eng yomon turdagi xato, chunki hech qanday belgisi bo'lmaydi.
    """
    return _sections(rubric_blocks, rubric_red_flags, extra_rules)


def _sections(
    rubric_blocks: list[dict[str, Any]],
    rubric_red_flags: list[dict[str, Any]],
    extra_rules: str | None,
) -> list[dict[str, Any]]:
    """Promptning barcha bo'laklari, TARTIB BILAN.

    Tartib muhim: admin matni rubrikadan keyin, qoidalar va formatdan
    OLDIN turadi (sababi `build_system_prompt` izohida).
    """
    block_keys = ", ".join(f"`{b['key']}`" for b in rubric_blocks)
    flag_keys = ", ".join(f"`{f['type']}`" for f in rubric_red_flags)
    total = sum(int(b.get("max", 0)) for b in rubric_blocks)

    return [
        {"key": "intro", "editable": False, "text": """Siz — Bonvi kompaniyasining savdo sifati bo'yicha tajribali auditorisiz.
Vazifangiz: savdo xodimining mijoz bilan telefon suhbati transkriptini
quyidagi rubrika bo'yicha xolis baholash.

## TIL HAQIDA — DIQQAT

Qo'ng'iroqlar O'ZBEK va RUS tillarida, ko'pincha ARALASH olib boriladi
(bir gapda ikkala til: «Assalomu alaykum, я по поводу заказа»).
Bu — O'zbekistonda MEYOR, kamchilik EMAS.

  · Til aralashtirilgani uchun ball KAMAYTIRILMAYDI.
  · Rus tilidagi gap ham xuddi o'zbekchadek to'liq baholanadi.
  · Transkriptda so'z buzilgan bo'lishi mumkin (nutqni matnga o'girish
    xatosi). Ma'no kontekstdan tushunarli bo'lsa — xodim aybdor emas.
  · Mahsulot nomi yoki raqam buzilgan ko'rinsa, buni xodimning xatosi
    deb hisoblamang; `transcript_quality` ni pasaytiring.

Sizning javobingiz — o'zbek tilida. Dalil (evidence) va iqtibos (quote)
esa transkriptdagi ASL tilda, o'zgartirilmasdan keltiriladi.

"""},
        {"key": "rubric", "editable": False, "text": f"""## RUBRIKA (jami {total} ball)
{_render_blocks(rubric_blocks)}

## RED FLAG'LAR (faqat shu kalitlar)
{_render_red_flags(rubric_red_flags)}
"""},
        {"key": "context", "editable": False, "text": """
## SUHBAT KONTEKSTI — ENG MUHIM QOIDA

Bonvi mijozlarining KO'PCHILIGI eski, doimiy mijoz: do'kon egasi,
usta, ulgurji xaridor. Ular skript bo'yicha gaplashmaydi va ularga
skript KERAK EMAS. Odatiy qo'ng'iroq shunday ko'rinadi:

  «Aka, menga o'sha 50 tadan chiqarib qo'ying»
  «Yangi narxlarni tashlang»
  «Metan bormi hozir? Ertaga borsam bo'ladimi?»

Bunday suhbat 30 soniyada tugaydi va bu YAXSHI ish. Mijoz nima
olishini biladi, xodim tez va aniq javob berdi — savdo bo'ldi.

⚠️ SHUNDAY SUHBATNI TO'LIQ SKRIPT BO'YICHA TEKSHIRMANG. «Ehtiyojni
aniqlamadi», «mahsulotni taqdim etmadi», «upsell qilmadi» deb ball
kesish — XATO baho. Bu mezonlar shu suhbatga umuman TAALLUQLI EMAS,
xodim esa hamma ishni to'g'ri qilgan.

### `na` — «taalluqli emas»

Rubrikada ⟨taalluqli bo'lmasa `na`⟩ deb belgilangan kriteriyalarga
`verdict: "na"` va `score: 0` qo'yish MUMKIN. Bunday kriteriya ball
hisobidan butunlay chiqariladi: u nol ham olmaydi, maksimum ham
olmaydi — go'yo rubrikada yo'q. Umumiy ball QOLGAN, ya'ni haqiqatan
qo'llanilgan mezonlar ichida hisoblanadi.

`na` QACHON to'g'ri bo'ladi:
  · mijoz aniq buyurtma aytdi → ehtiyojni aniqlash kerak emas (A2);
  · mijoz mahsulotni biladi, faqat qoldiq/narx so'radi → taqdim
    etish kerak emas (A3);
  · e'tiroz umuman bildirilmadi → e'tiroz bilan ishlash yo'q (C2);
  · mijozning o'zi sotib olyapti → yopish urinishi shart emas (D1);
  · qisqa texnik so'rov → upsell va qiymat argumenti o'rinsiz (D2, D4).

`na` QACHON NOTO'G'RI:
  · xodim mezonni bajarishi MUMKIN va FOYDALI edi, lekin bajarmadi —
    bu `fail`, `na` emas. Farqi shu: `na` — «vaziyat talab qilmadi»,
    `fail` — «vaziyat imkon berdi, xodim foydalanmadi». Masalan
    mijoz buyurtma bergach «yana nima kerak edi?» deb so'rash real
    imkoniyat edi — bunda upsell `na` emas, `fail`;
  · ⟨HAR DOIM baholanadi⟩ deb belgilangan kriteriya. Salomlashish,
    muomala madaniyati, savolga to'g'ri javob va kelishuvning
    aniqligi HAR QANDAY suhbatda tekshiriladi — eng qisqasida ham;
  · suhbat UZUN bo'lsa (2 daqiqadan ortiq) `na` kamdan-kam to'g'ri
    bo'ladi: vaqt bo'lgan, demak bosqichlar ham bo'lishi mumkin edi.

Har bir `na` uchun `evidence` da SABAB yoziladi: nega bu mezon shu
suhbatga tegishli emas. Sababsiz `na` — yashirin ball ko'tarish.

### ⚠️ `na` — MEZON TANLASHDAGI yengillik, BALL QO'YISHDAGI emas

Bu ikkisini ARALASHTIRMANG. Qaysi mezon qo'llanishini vaziyat hal
qiladi; qo'llanadigan mezon esa HAR DOIMGIDEK qat'iy baholanadi.

Ya'ni «suhbat qisqa edi, mayli, hammasiga to'liq ball qo'yaman» —
XATO. Qisqa suhbatda ham xodim salomlashmasligi, kompaniya nomini
aytmasligi, mijozni bo'lishi yoki kelishuvni mavhum qoldirishi
mumkin. Bularning har biri o'z mezonida ball yo'qotadi.

To'liq ball (maksimum) faqat mezon TO'LIQ bajarilganda qo'yiladi.
Agar `improvement` maydonida «... qilsa yaxshi bo'lardi» deb yozsangiz,
demak mezon to'liq bajarilmagan — u holda ball maksimal BO'LMAYDI.
Bu ikkisi bir-biriga zid va shunday javob ishonchsiz ko'rinadi.

### Qisqalik kamchilik EMAS

Suhbatning qisqaligi uchun ball kesilmaydi. Savol shu emas: «xodim
ko'p gapirdimi?» Savol shu: «mijoz nima uchun qo'ng'iroq qilgan
bo'lsa, o'shani oldimi va bunda unga hurmat bilan muomala qilindimi?»
Agar javob «ha» bo'lsa — bu yuqori ball, suhbat 20 soniya bo'lsa ham.

`call_scenario` maydonida suhbat qanday bo'lganini belgilang — menejer
`na` qarorlarini shu bilan tekshiradi.
"""},
        {
            "key": "extra_rules",
            "editable": True,
            "text": _render_extra_rules(extra_rules),
        },
        {"key": "rules", "editable": False, "text": f"""
## BALL QO'YISH QOIDALARI

1. Har bir kriteriyaga 0 dan uning maksimal balligacha butun son qo'ying.
   Kriteriya shu suhbatga taalluqli bo'lmasa (va rubrikada ⟨taalluqli
   bo'lmasa `na`⟩ deb belgilangan bo'lsa) — `verdict: "na"`, `score: 0`.

   Verdikt va ball BIR XIL narsani aytishi kerak:
     · `pass`    — mezon TO'LIQ bajarilgan, transkriptda aniq dalil bor
                   → maksimal ball;
     · `partial` — qisman bajarilgan yoki dalil kuchsiz → maksimumning
                   yarmi atrofida;
     · `fail`    — bajarilmagan → 0 yoki juda kam;
     · `na`      — vaziyat talab qilmagan → 0, hisobga kirmaydi.

   ⚠️ Maksimal ball ISBOT talab qiladi. Transkriptda mezonni tasdiqlovchi
   aniq iqtibos bo'lmasa, `pass` ham, maksimal ball ham qo'yilmaydi —
   `partial` qo'ying. «Yomon narsa ko'rmadim» — bu dalil emas.
2. Blok baliga va umumiy ballga SIZ TEGMAYSIZ — ular kriteriya
   ballaridan hisoblanadi. Sizning ishingiz faqat har bir mezonga
   halol ball va halol verdikt qo'yish.

   ⚠️ FOYDALANUVCHI XABARIDA `na` UCHUN CHEGARA ko'rsatiladi va u shu
   suhbat uzunligidan kelib chiqadi. Qisqa suhbatda chegara amalda
   yo'q, uzun suhbatda esa kichik: 8 daqiqa gaplashilgan bo'lsa,
   ehtiyojni aniqlash ham, taqdimot ham, e'tiroz bilan ishlash ham
   BO'LISHI MUMKIN edi — ular «taalluqli emas» emas, «qilinmagan».
   Chegaradan oshsa javob rad etiladi va qayta so'raladi.

   ⚠️ `na` MEZONNING BALLI BOSHQA MEZONLARGA TAQSIMLANMAYDI. Blok
   maksimumini «to'ldirish» kerak emas: A2 va A3 taalluqli bo'lmasa,
   qolgan mezonlarning bali oshmaydi — ular baribir foizga
   aylantiriladi va xodim yutqazmaydi. Hech bir mezon o'z
   maksimumidan oshiq ball ololmaydi.
3. Umumiy ball shunday hisoblanadi: qo'llanilgan mezonlar bo'yicha
   olingan ball ularning maksimumiga nisbatan foizga aylantiriladi,
   keyin red flag jarimalari ayiriladi.
4. Har bir kriteriya uchun DALIL majburiy: transkriptdan qisqa iqtibos.
   Vaqt belgisi bor bo'lsa (`[04:12]`) uni ham keltiring. Dalil topilmasa
   ball past bo'ladi va `evidence` da «dalil topilmadi» deb yoziladi.
   `na` uchun `evidence` da NEGA taalluqli emasligi yoziladi.
   HECH QACHON transkriptda yo'q gapni o'ylab topmang.
5. Red flag faqat quyidagi kalitlardan biri bo'lishi mumkin: {flag_keys}.
   Boshqa kalit yozilsa — butun javob rad etiladi. Red flag har doim
   iqtibos bilan tasdiqlanadi; shubha bo'lsa — QO'YMANG.
   Bir xil tur bir necha marta takrorlansa — HAR BIR hodisani alohida
   yozing (o'z vaqti va o'z iqtiboti bilan). Menejer nima bo'lganini
   to'liq ko'rishi kerak; jarima esa baribir bir marta hisoblanadi.
   `profanity` bo'lsa umumiy ball 0 ga tushadi.
6. Baqirish (`shouting`) faqat matndan aniqlanmaydi. Transkriptda
   ochiq-oydin dalil (BOSH HARFLAR, «nega baqiryapsiz» degan javob)
   bo'lmasa — qo'ymang.
7. `confidence` — o'z bahoingizga ishonch (0..1). Transkript qisqa,
   uzuq-yuluq yoki mijoz gapi yetishmasa — 0.7 dan past qo'ying.
   ⚠️ Suhbat SHUNCHAKI qisqa bo'lgani (mijoz tez buyurtma berib
   qo'ygani) ishonchni pasaytirmaydi — bunda hammasi tushunarli.
   Ishonch transkript SIFATI haqida, suhbat uzunligi haqida emas.
8. `outcome_signal` — zakaz belgisi. Bu BALL EMAS, faqat signal;
   ishonchingiz past bo'lsa `unclear` deb belgilang.
9. `call_scenario` — suhbat qanday bo'ldi: `new_client` (yangi mijoz,
   to'liq tanishtirish talab qilinadi), `repeat_order` (tanish mijoz
   buyurtma berdi), `price_check` (qoldiq/narx so'rovi), `issue`
   (shikoyat, muammo, yetkazib berish), `personal` (ishga aloqasi
   yo'q suhbat), `no_content` (suhbatda ish mazmuni UMUMAN yo'q),
   `other`. Bu maydon `na` qarorlaringizni tushuntiradi.

   ⚠️ `no_content` — ALOHIDA HOLAT. Ba'zi qo'ng'iroqlarda baholash
   uchun material yo'q: salomlashib «keyinroq qo'ng'iroq qilaman» deb
   tugaydi, noto'g'ri raqam, aloqa uzilgan, faqat hol-ahvol so'rashilgan.
   Bunday suhbatga yuqori ball qo'yish ko'rsatkichni YOLG'ON qiladi —
   xuddi past ball qo'ygandek zararli. Shuning uchun `no_content` da
   `confidence` ni 0.6 dan PAST qo'ying: bu «material yetarli emas»
   degan signal va menejer bunday bahoni tekshiruv navbatida ko'radi.
10. `coaching_note` — xodimga 2–3 jumlalik amaliy maslahat, o'zbek
   tilida. Ayblov emas, o'sish uchun ko'rsatma: nima yaxshi, nimani
   qanday yaxshilash mumkin. Suhbat qisqa va to'g'ri o'tgan bo'lsa —
   buni tan oling, sun'iy kamchilik izlamang.

Bu baho — KOUCHING vositasi. Odamning ishi haqidagi qaror emas.
Shubhali holatda xodim foydasiga hal qiling va `confidence` ni pasaytiring.

"""},
        {"key": "format", "editable": False, "text": f"""## JAVOB SHAKLI

Faqat JSON qaytaring. Izoh, markdown belgilari va matn — YO'Q.
Bloklar kalitlari aynan shular: {block_keys}.

Ikkita eng ko'p uchraydigan xato — javob shu sababli rad etiladi:

  · HAR BIR kriteriya javobda BO'LISHI SHART, `na` deb belgilangani
    HAM. Uni ro'yxatdan tushirib qoldirmang: `na` — bu javob, «javob
    yo'q» emas.
  · `verdict: "na"` faqat rubrikada ⟨taalluqli bo'lmasa `na`⟩ deb
    belgilangan kriteriyada bo'ladi. ⟨HAR DOIM baholanadi⟩ da `na`
    qo'yilsa butun javob rad etiladi — u yerda `fail` yoki `partial`
    ishlatiladi."""},
    ]


# ── Foydalanuvchi xabari ──────────────────────────────────────


def build_user_prompt(
    *,
    transcript: str,
    duration_sec: int,
    direction: str,
    started_at: str,
    client_label: str | None = None,
    na_budget: int | None = None,
) -> str:
    """Bitta qo'ng'iroq. Kesh chegarasidan KEYIN turadigan qism.

    ⚠️ `client_label` — MIJOZ TANISHMI degan signal, ismning o'zi emas.
    MoyZvonki nomni faqat kontaktlar kitobida saqlangan raqamga beradi;
    ya'ni nom bor bo'lsa, bu raqam bilan ilgari ham ishlanganini
    bildiradi. Bu baholashda muhim: tanish mijozdan to'liq tanishtirish
    ham, ehtiyojni noldan aniqlash ham talab qilinmaydi.
    """
    direction_uz = "Chiquvchi (xodim qo'ng'iroq qilgan)" if direction == "outbound" \
        else "Kiruvchi (mijoz qo'ng'iroq qilgan)"
    minutes, seconds = divmod(max(duration_sec, 0), 60)

    header = [
        "## QO'NG'IROQ",
        f"Sana: {started_at}",
        f"Yo'nalish: {direction_uz}",
        f"Davomiyligi: {minutes} daq {seconds} son",
    ]
    if na_budget is not None:
        # ⚠️ Budjet AYNAN SHU qo'ng'iroq uchun: uzunligiga bog'liq.
        # Chegarasiz qoldirilganda model 10 daqiqalik suhbatda ham
        # yettita mezonni tashlab yuborardi va 100 ball qo'yardi.
        header.append(
            f"⚠️ `na` CHEGARASI: {na_budget} ball. `na` deb belgilangan "
            "mezonlarning BALLARI yig'indisi shundan oshmasligi kerak "
            "(masalan 6 + 5 = 11 — mumkin; 8 + 7 + 8 = 23 — mumkin emas). "
            "Chegara shu suhbatning uzunligidan kelib chiqadi: vaqt "
            "bo'lgan bo'lsa, bosqich ham bo'lishi mumkin edi. Oshib "
            "ketsa javob RAD ETILADI."
        )
    if client_label:
        header.append(
            f"Mijoz: {client_label} — TANISH mijoz (kontaktlar kitobida "
            "saqlangan, ya'ni u bilan ilgari ham ishlangan)"
        )
    else:
        header.append(
            "Mijoz: kontaktlar kitobida yo'q — yangi yoki tasodifiy raqam "
            "bo'lishi mumkin"
        )

    return (
        "\n".join(header)
        + "\n\n## TRANSKRIPT\n\n"
        + (transcript or "").strip()
        + "\n\n## VAZIFA\n"
        + "Yuqoridagi rubrika bo'yicha baholang va faqat JSON qaytaring."
    )


def build_retry_prompt(previous_error: str) -> str:
    """Validatsiyadan o'tmagan javobdan keyingi qayta so'rov qo'shimchasi."""
    return (
        "\n\n## ⚠️ OLDINGI JAVOBINGIZ RAD ETILDI\n"
        f"Sabab: {previous_error}\n"
        "Xatoni tuzatib, YANA BIR BOR to'liq JSON qaytaring. "
        "Har blokda `na` bo'lmagan kriteriyalar yig'indisi blok baliga "
        "aniq teng bo'lsin. `overall_score` ni qaytarish shart emas — "
        "uni tizim o'zi hisoblaydi."
    )


# ── Structured output sxemasi ─────────────────────────────────


def build_schema(
    rubric_blocks: list[dict[str, Any]], rubric_red_flags: list[dict[str, Any]]
) -> dict[str, Any]:
    """JSON Schema — `LLMClient.complete(schema=...)` ga beriladi.

    Sxema rubrikadan quriladi: blok kalitlari va red flag turlari
    ro'yxati aynan rubrikadagidek bo'ladi, shuning uchun model o'ylab
    topilgan kalitni qaytara olmaydi (schema qo'llab-quvvatlanmagan
    provayderlarda ham sxema promptga qo'shiladi).
    """
    block_properties: dict[str, Any] = {}
    for block in rubric_blocks:
        criteria_properties: dict[str, Any] = {}
        for criterion in block.get("criteria", []):
            points = int(criterion.get("points", 0))
            optional = bool(criterion.get("optional"))
            # ⚠️ Verdikt ro'yxati HAR KRITERIYAGA ALOHIDA. `na` faqat
            # ixtiyoriy mezonda bo'ladi va buni sxemaning o'zi to'sadi —
            # validatorgacha yetib kelmaydi, ya'ni qayta so'rov (pul)
            # ham bo'lmaydi.
            verdicts = ["pass", "partial", "fail"] + (["na"] if optional else [])
            criteria_properties[criterion["id"]] = {
                "type": "object",
                "description": (
                    f"{criterion.get('label', '')} — 0..{points} ball"
                    + (
                        ". Taalluqli bo'lmasa: verdict=na, score=0"
                        if optional
                        else ". Har qanday suhbatda baholanadi"
                    )
                ),
                "properties": {
                    # ⚠️ Yuqori chegara AYNAN shu mezonniki.
                    #
                    # NEGA MUHIM. Ilgari kriteriyalar ro'yxat (array)
                    # bo'lib kelardi va chegara umumiy edi. `na` paydo
                    # bo'lgach model tashlangan mezonning ballini
                    # qolganlariga TAQSIMLASHGA urindi: A4 ga 5
                    # o'rniga 15 qo'ydi — blok maksimumini «to'ldirish»
                    # uchun. Validator rad etardi, model yana urinardi,
                    # va beshta qo'ng'iroqning ikkitasi umuman
                    # baholanmay qolardi (uch marta so'rov = uch marta
                    # pul, natija esa yo'q).
                    #
                    # Obyekt ko'rinishida har mezon o'z chegarasini
                    # oladi va bunday javob TUZILISHIGA ko'ra mumkin
                    # emas.
                    "score": {"type": "integer", "minimum": 0, "maximum": points},
                    "verdict": {"type": "string", "enum": verdicts},
                    "evidence": {"type": "string"},
                    "improvement": {"type": "string"},
                },
                "required": ["score", "verdict", "evidence"],
                "additionalProperties": False,
            }

        block_properties[block["key"]] = {
            "type": "object",
            "description": f"{block.get('label', '')} — {block.get('max', 0)} ball",
            "properties": {
                # ⚠️ `score` maydoni YO'Q va ataylab yo'q. Blok bali —
                # kriteriyalar yig'indisi, ya'ni HISOBLANADIGAN qiymat.
                # Modeldan uni so'rash faqat xato manbai edi: `na`
                # bilan tashlangan mezondan keyin u blok maksimumini
                # «to'ldirishga» urinardi va javob rad etilardi.
                "criteria": {
                    "type": "object",
                    "properties": criteria_properties,
                    # Har mezon MAJBURIY — `na` bo'lgani ham. Ilgari
                    # model ularni ro'yxatdan tushirib qoldirardi.
                    "required": list(criteria_properties),
                    "additionalProperties": False,
                }
            },
            "required": ["criteria"],
            "additionalProperties": False,
        }

    flag_types = [f["type"] for f in rubric_red_flags]

    return {
        "type": "object",
        "properties": {
            "language_detected": {
                "type": "string",
                "enum": ["uz", "ru", "mixed", "other"],
            },
            "transcript_quality": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "blocks": {
                "type": "object",
                "properties": block_properties,
                "required": list(block_properties),
                "additionalProperties": False,
            },
            "red_flags": {
                "type": "array",
                # Har HODISA alohida element: bir xil `type` bir necha marta
                # kelishi mumkin (har biri o'z vaqti va iqtiboti bilan).
                # Jarima esa har tur uchun bir marta hisoblanadi — buni
                # `validator._validate_red_flags` kafolatlaydi.
                "description": (
                    "Aniqlangan qoidabuzarliklar. Bir xil tur bir necha marta "
                    "uchrasa — har hodisa alohida element bo'ladi, jarima esa "
                    "`overall_score` da bir marta hisoblanadi."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": flag_types},
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "timestamp": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["type", "severity", "quote"],
                    "additionalProperties": False,
                },
            },
            "outcome_signal": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "order_agreed",
                            "follow_up",
                            "rejected",
                            "info_only",
                            "unclear",
                        ],
                    },
                    "products_mentioned": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "quantity_mentioned": {"type": ["integer", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {"type": "string"},
                },
                "required": ["type", "confidence"],
                "additionalProperties": False,
            },
            "client_sentiment": {
                "type": "string",
                "enum": ["positive", "neutral", "negative"],
            },
            "coaching_note": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            # Suhbat qanday bo'lgani. BALL EMAS — `na` qarorlarini
            # tushuntiradigan kontekst: menejer «nega 5 ta mezon
            # tashlab ketilgan?» degan savolga javobni shu yerdan
            # topadi.
            "call_scenario": {
                "type": "string",
                "enum": [
                    "new_client",
                    "repeat_order",
                    "price_check",
                    "issue",
                    "personal",
                    # Baholash uchun material yo'q: salomlashish,
                    # qayta qo'ng'iroq kelishuvi, noto'g'ri raqam
                    "no_content",
                    "other",
                ],
            },
        },
        # ⚠️ `overall_score` RO'YXATDA YO'Q va ataylab yo'q.
        #
        # Ilgari model umumiy ballni o'zi hisoblab qaytarardi, validator
        # esa arifmetikani tekshirardi. Endi hisob-kitobda BO'LISH bor
        # (qo'llanilgan mezonlar ichidagi foiz), ya'ni modeldan uni
        # so'rash — javobning rad etilishi va qayta so'rov (ya'ni ikki
        # baravar pul) ehtimolini oshirish degani. Umumiy ballni tizim
        # o'zi hisoblaydi; modelning ishi — har mezonga halol ball.
        "required": [
            "language_detected",
            "transcript_quality",
            "blocks",
            "red_flags",
            "outcome_signal",
            "client_sentiment",
            "coaching_note",
            "confidence",
            "call_scenario",
        ],
        "additionalProperties": False,
    }
