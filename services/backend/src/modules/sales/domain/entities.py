"""Savdo nazorati domeni — sof Python, na SQLAlchemy, na openpyxl.

Bu yerda uch narsa bor:
  · operatsiya turlari (`SaleOpType`) va SAP nomlaridan ularga xarita;
  · rahbar qarori uchun toifalar (`SaleReviewStatus`, `SaleReviewReason`);
  · filial nomini xodim ismiga solishtirish uchun normalizatsiya.

Qoidalar (R1/R2/R3) BU YERDA YO'Q — ular 2-bosqichda qo'shiladi va
natijasi jadvalga yozilmaydi (shartnomaning 3-bo'limiga qarang).
"""

from enum import StrEnum

# ══════════════════════════════════════════════════════════════
#  Operatsiya turi
# ══════════════════════════════════════════════════════════════


class SaleOpType(StrEnum):
    """`sales.op_type` qiymatlari.

    Nazorat qoidalari FAQAT `SALE` ga qo'llanadi. Qolgan turlar
    ATAYLAB saqlanadi: to'lov va qaytarish mijoz bilan bo'lgan
    munosabatning bir qismi va mijoz kartochkasidagi vaqt chizig'ida
    (3-bosqich) ko'rinishi kerak.
    """

    SALE = "sale"
    PAYMENT_IN = "payment_in"
    PURCHASE = "purchase"
    PAYMENT_OUT = "payment_out"
    SALE_CANCEL = "sale_cancel"
    ACCOUNTING = "accounting"

    OTHER = "other"
    """SAP da yangi tur paydo bo'lsa — qator YO'QOLMASIN.

    Ilgari noma'lum tur qatorni tashlab ketardi degan yechim ko'rilgan
    edi, lekin u JIMGINA ma'lumot yo'qotish demakdir: hisobotda
    «o'qildi 2384» deb tursa-yu bazada 2300 qator bo'lsa, farqni hech
    kim sezmaydi. `other` esa hisobotdagi `unknown_op_type` soni bilan
    birga ko'rinadi va qoidalarga ta'sir qilmaydi."""


#: SAP dagi `Тип` ustuni qiymatlari → bizning turlar.
#
# ⚠️ `Исходящие платежи платежи` — SAP eksportidagi HAQIQIY qiymat,
# so'z ikki marta yozilgan (o'lchandi: 146 qatorda aynan shunday).
# Hujjatda u «Исходящие платежи» deb yozilgan edi. Ikkala ko'rinish
# ham qoldirildi: eksport tuzatilsa ham, tuzatilmasa ham import
# ishlayveradi.
_OP_TYPES: dict[str, SaleOpType] = {
    "продажа": SaleOpType.SALE,
    "входящие платежи": SaleOpType.PAYMENT_IN,
    "закупка": SaleOpType.PURCHASE,
    "исходящие платежи": SaleOpType.PAYMENT_OUT,
    "исходящие платежи платежи": SaleOpType.PAYMENT_OUT,
    "отмена продажа": SaleOpType.SALE_CANCEL,
    "отмена продажи": SaleOpType.SALE_CANCEL,
    "бух.оп": SaleOpType.ACCOUNTING,
    "бух.оп.": SaleOpType.ACCOUNTING,
}


#: Turning SAP dagi ko'rinishi — import oldidagi hisob-kitob uchun.
#
# ⚠️ ATAYLAB RUSCHA. Bu yorliq foydalanuvchi FAYLDA ko'rgan so'z bilan
# bir xil bo'lishi kerak: hisob-kitob oynasidagi sonni u SAP dagi
# hisobot bilan solishtiradi, tarjima qilingan so'z esa solishtirishni
# imkonsiz qilardi. Ekranda tarjima BOR (frontend `type` kaliti bo'yicha
# oladi), bu esa uning zaxirasi — SAP da yangi tur paydo bo'lsa ham
# nimadir ko'rinib turadi.
OP_TYPE_LABELS: dict[SaleOpType, str] = {
    SaleOpType.SALE: "Продажа",
    SaleOpType.PAYMENT_IN: "Входящие платежи",
    SaleOpType.PURCHASE: "Закупка",
    SaleOpType.PAYMENT_OUT: "Исходящие платежи",
    SaleOpType.SALE_CANCEL: "Отмена продажи",
    SaleOpType.ACCOUNTING: "Бух.оп",
    SaleOpType.OTHER: "Прочее",
}


def op_type_from_sap(value: str | None) -> SaleOpType:
    """SAP `Тип` matnini `op_type` ga aylantiradi.

    Tanilmagan tur `OTHER` bo'ladi — chaqiruvchi buni hisobotga
    qo'shadi, lekin qator baribir saqlanadi.
    """
    key = " ".join((value or "").split()).lower()
    return _OP_TYPES.get(key, SaleOpType.OTHER)


# ══════════════════════════════════════════════════════════════
#  Rahbar qarori
# ══════════════════════════════════════════════════════════════


class SaleReviewStatus(StrEnum):
    """`sale_reviews.status` — bazada saqlanadigan YAGONA qaror.

    Qoidaning o'zi natijasi saqlanmaydi (shartnoma, 3-bo'lim):
    qo'ng'iroq savdodan KEYIN sinxronlanishi mumkin va o'shanda eski
    «shubhali» belgisi yolg'onga aylanardi.
    """

    JUSTIFIED = "justified"
    CONFIRMED = "confirmed"


class SaleReviewReason(StrEnum):
    """«Oqlandi» qarorining sababi."""

    WALK_IN = "walk_in"
    TELEGRAM = "telegram"
    VISIT = "visit"
    CONTRACT = "contract"
    OTHER = "other"


# ══════════════════════════════════════════════════════════════
#  Filial nomini xodim ismiga solishtirish
# ══════════════════════════════════════════════════════════════

#: Bir tovushning turli yozilishi. Kalit — SAP va bizning bazada
#: uchraydigan ko'rinish, qiymat — yagona shakl.
#
# ⚠️ YO'NALISH MUHIM. Shartnomada «ж→дж» deb yozilgan, lekin uni
# so'zma-so'z bajarib bo'lmaydi: `Джиззах` dagi `ж` ham almashadi va
# `дджиззах` chiqadi — ya'ni almashtirish O'ZINI BUZADI. Shuning uchun
# teskari yo'nalish tanlandi: `дж → ж`. Natija bir xil (`Жиззах` va
# `Джиззах` bir shaklga tushadi), lekin amal IDEMPOTENT — necha marta
# qo'llansa ham natija o'zgarmaydi.
_LETTER_FOLDS: tuple[tuple[str, str], ...] = (
    ("дж", "ж"),
    ("ё", "е"),
    ("й", "и"),
    ("ъ", ""),
    ("ь", ""),
)


def _collapse_repeats(text: str) -> str:
    """Ketma-ket takrorlangan belgilarni bittaga tushiradi.

    ⚠️ BUSIZ `Навоий` va `Навои` MOS KELMAYDI. `й→и` dan keyin birinchisi
    `навоии` bo'lib qoladi, ikkinchisi esa `навои` — bir harf farq bilan
    biriktirish ishlamas edi. Bu SAP da eng ko'p uchraydigan farq:
    o'zbek nomlarining ruscha yozilishida oxirgi `й` bor-yo'qligi
    tasodifiy.

    Amal IKKALA tomonga ham qo'llanadi (filial nomiga ham, xodim
    ismiga ham), shuning uchun u faqat farqni yo'qotadi — yangi
    to'qnashuv yaratmaydi.
    """
    result: list[str] = []
    for char in text:
        if not result or result[-1] != char:
            result.append(char)
    return "".join(result)


def normalize_branch(name: str | None) -> str:
    """Filial/xodim nomining solishtirish uchun yagona shakli.

    `Навоий` → `навои`, `Жиззах` → `жизах`, `  Тошкент ` → `тошкент`.

    Bu SAP dagi `Подразделение` ni `agents.full_name` ga bog'lash
    uchun ishlatiladi. Qidiruv AYNAN TENGLIK bo'yicha: yaqinlik
    (fuzzy) ataylab yo'q — noto'g'ri xodimga savdo yozib qo'yish
    bo'sh qoldirishdan yomonroq, chunki keyin uni hech kim
    tekshirmaydi.
    """
    text = " ".join((name or "").split()).lower()
    for source, target in _LETTER_FOLDS:
        text = text.replace(source, target)
    return _collapse_repeats(text)


#: «Разовый клиент» — bitta umumiy kod ostidagi bir martalik mijozlar.
#
# Savdolarning ~29% i shu kodda va ularda real mijoz aniqlanmaydi.
# Nazoratdan chiqariladi (shartnoma, 4-bo'lim «Istisnolar»). Bu yerda
# — domenda — turibdi, chunki import ham, qoidalar ham (2-bosqich)
# unga qaraydi.
WALK_IN_PARTNER_CODE = "К00001"

#: UMUMIY KODLAR — bitta kod ostida KO'P odam turadi.
#
# Bularda «shu mijoz bilan gaplashilganmi?» degan savolning O'ZI
# ma'nosiz: kod bitta, mijoz esa yuzta. Shuning uchun qoidalar ularni
# tekshirmaydi va savdo `not_checkable` toifasiga tushadi
# (`skip_reason = "generic_code"`). ⚠️ Bu «toza» degani EMAS —
# uchinchi toifa ekranda alohida son bo'lib turadi.
#
# O'lchandi (22.08.2026, 1039 savdo):
#   · `К00001` «Разовый клиент»                    — 152 savdo
#   · `К02370` «Салл сентр»                        —  20 savdo
#   · `К03223` «Разовый клиент — Тошкент телефон савдо» — 2 savdo
#
# ⚠️ Harf `К` — KIRILL (U+041A), lotin `K` emas. SAP shunday yozadi;
# lotin harfi bilan yozilsa ro'yxat JIMGINA ishlamay qolardi.
#
# Yangi umumiy kod paydo bo'lsa — shu ro'yxatga qo'shiladi. Uni
# sozlamaga chiqarish ko'rib chiqilgan va rad etilgan: ro'yxat yiliga
# bir marta o'zgaradi, sozlama esa noto'g'ri to'ldirilsa butun bo'limni
# jimgina bo'shatib qo'yardi.
GENERIC_PARTNER_CODES: frozenset[str] = frozenset(
    {WALK_IN_PARTNER_CODE, "К02370", "К03223"}
)

#: `Код группы` ning mijoz degan qiymati. Qolganlari (yetkazib
#: beruvchi, taʼsischi, transport…) nazoratdan tashqarida.
CLIENT_GROUP = "Клиенты"
