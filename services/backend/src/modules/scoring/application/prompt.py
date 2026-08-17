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
    lines: list[str] = []
    for block in blocks:
        lines.append(
            f"\n### Blok «{block.get('label', block['key'])}» "
            f"(kalit: `{block['key']}`, maksimal {block.get('max', 0)} ball)"
        )
        for criterion in block.get("criteria", []):
            description = criterion.get("description") or ""
            lines.append(
                f"  · {criterion['id']} — {criterion.get('label', '')} "
                f"[0..{criterion.get('points', 0)} ball]"
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
        {
            "key": "extra_rules",
            "editable": True,
            "text": _render_extra_rules(extra_rules),
        },
        {"key": "rules", "editable": False, "text": f"""
## BALL QO'YISH QOIDALARI

1. Har bir kriteriyaga 0 dan uning maksimal balligacha butun son qo'ying.
2. Blok bali = shu blok kriteriyalari yig'indisi. Boshqacha bo'lishi mumkin emas.
3. `overall_score` = barcha bloklar yig'indisi + red flag jarimalari
   (jarimalar manfiy). Natija 0 dan past bo'lsa — 0. Agar `profanity`
   red flag'i bo'lsa — `overall_score` aniq 0.
   ⚠️ Bir xil turdagi red flag bir necha marta uchrasa, jarima BIR MARTA
   ayiriladi: ikki marta baqirish ham, uch marta ham — bitta jarima.
   ⚠️ Arifmetikani tekshiring: yig'indi noto'g'ri bo'lsa javob RAD ETILADI
   va qo'ng'iroq baholanmagan qoladi.
4. Har bir kriteriya uchun DALIL majburiy: transkriptdan qisqa iqtibos.
   Vaqt belgisi bor bo'lsa (`[04:12]`) uni ham keltiring. Dalil topilmasa
   ball past bo'ladi va `evidence` da «dalil topilmadi» deb yoziladi.
   HECH QACHON transkriptda yo'q gapni o'ylab topmang.
5. Red flag faqat quyidagi kalitlardan biri bo'lishi mumkin: {flag_keys}.
   Boshqa kalit yozilsa — butun javob rad etiladi. Red flag har doim
   iqtibos bilan tasdiqlanadi; shubha bo'lsa — QO'YMANG.
   Bir xil tur bir necha marta takrorlansa — HAR BIR hodisani alohida
   yozing (o'z vaqti va o'z iqtiboti bilan). Menejer nima bo'lganini
   to'liq ko'rishi kerak; jarima esa (3-qoida) baribir bir marta.
6. Baqirish (`shouting`) faqat matndan aniqlanmaydi. Transkriptda
   ochiq-oydin dalil (BOSH HARFLAR, «nega baqiryapsiz» degan javob)
   bo'lmasa — qo'ymang.
7. `confidence` — o'z bahoingizga ishonch (0..1). Transkript qisqa,
   uzuq-yuluq yoki mijoz gapi yetishmasa — 0.7 dan past qo'ying.
   Bu son menejerlarning tekshiruv navbatini shakllantiradi, shuning
   uchun halol bo'ling.
8. `outcome_signal` — zakaz belgisi. Bu BALL EMAS, faqat signal;
   ishonchingiz past bo'lsa `unclear` deb belgilang.
9. `coaching_note` — xodimga 2–3 jumlalik amaliy maslahat, o'zbek tilida.
   Ayblov emas, o'sish uchun ko'rsatma: nima yaxshi, nimani qanday
   yaxshilash mumkin.

Bu baho — KOUCHING vositasi. Odamning ishi haqidagi qaror emas.
Shubhali holatda xodim foydasiga hal qiling va `confidence` ni pasaytiring.

"""},
        {"key": "format", "editable": False, "text": f"""## JAVOB SHAKLI

Faqat JSON qaytaring. Izoh, markdown belgilari va matn — YO'Q.
Bloklar kalitlari aynan shular: {block_keys}."""},
    ]


# ── Foydalanuvchi xabari ──────────────────────────────────────


def build_user_prompt(
    *,
    transcript: str,
    duration_sec: int,
    direction: str,
    started_at: str,
) -> str:
    """Bitta qo'ng'iroq. Kesh chegarasidan KEYIN turadigan qism."""
    direction_uz = "Chiquvchi (xodim qo'ng'iroq qilgan)" if direction == "outbound" \
        else "Kiruvchi (mijoz qo'ng'iroq qilgan)"
    minutes, seconds = divmod(max(duration_sec, 0), 60)

    header = [
        "## QO'NG'IROQ",
        f"Sana: {started_at}",
        f"Yo'nalish: {direction_uz}",
        f"Davomiyligi: {minutes} daq {seconds} son",
    ]

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
        "Kriteriyalar yig'indisi blok baliga, bloklar yig'indisi + jarimalar "
        "esa `overall_score` ga aniq teng bo'lsin."
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
        criterion_ids = [c["id"] for c in block.get("criteria", [])]
        block_properties[block["key"]] = {
            "type": "object",
            "description": f"{block.get('label', '')} — 0..{block.get('max', 0)} ball",
            "properties": {
                "score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": int(block.get("max", 0)),
                },
                "criteria": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "enum": criterion_ids},
                            "score": {"type": "integer", "minimum": 0},
                            "verdict": {
                                "type": "string",
                                "enum": ["pass", "partial", "fail"],
                            },
                            "evidence": {"type": "string"},
                            "improvement": {"type": "string"},
                        },
                        "required": ["id", "score", "verdict", "evidence"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["score", "criteria"],
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
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": [
            "language_detected",
            "transcript_quality",
            "blocks",
            "red_flags",
            "outcome_signal",
            "client_sentiment",
            "coaching_note",
            "confidence",
            "overall_score",
        ],
        "additionalProperties": False,
    }
