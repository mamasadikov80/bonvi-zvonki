"""Telegram guruh domeni — sof Python, bazani ham, FastAPI'ni ham bilmaydi.

Guruh — bu mijozlar o'tiradigan Telegram chati. Bitta guruh bitta savdo
xodimiga va bitta hududga biriktiriladi; shu ikkalasi to'lgandagina unga
so'rovnoma yuborish mumkin.

Xodimning hududlari alohida saqlanmaydi — ular biriktirilgan guruhlardan
YIG'ILADI. Anvar Samarqand va Buxoro guruhlarida bo'lsa, uning hududlari
ikkita: qo'shimcha jadval ham, qo'lda kiritish ham kerak emas.
"""

from enum import StrEnum

# ── Taxmin lug'ati (hududlar ro'yxati EMAS) ───────────────────
#
# ⚠️ Bu YAGONA MANBA EMAS. Hududlar ro'yxatini endi admin boshqaradi,
# manbai — `regions` jadvali (`modules/regions/`), `GET /regions` va
# `GET /groups/regions` ikkalasi ham o'sha yerdan o'qiydi.
#
# Bu yerda qolgani — faqat `suggest_region()` uchun lug'at: guruh nomidan
# («Bonvi Samarqand») viloyatni taniydigan atamalar. U TAXMIN qiladi,
# qaror qilmaydi — admin `PATCH` qilganda baribir haqiqiy ro'yxatdan
# tanlaydi, shuning uchun bu lug'atning to'liq bo'lishi shart emas va
# «Samarqand shimol» kabi bo'lingan hududlarni bilishi ham shart emas.

SUGGESTION_REGIONS: list[str] = [
    "Toshkent",
    "Farg'ona vodiysi",
    "Samarqand",
    "Buxoro",
    "Xorazm",
    "Surxondaryo",
    "Andijon",
    "Namangan",
    "Qashqadaryo",
    "Navoiy",
    "Jizzax",
    "Sirdaryo",
    "Qoraqalpog'iston",
]


class BotStatus(StrEnum):
    """Botning guruhdagi holati — Telegram `my_chat_member` dan keladi."""

    MEMBER = "member"
    ADMINISTRATOR = "administrator"
    LEFT = "left"
    KICKED = "kicked"


# Bot chiqib ketgan guruh: so'rovnoma yuborib bo'lmaydi, o'chirish mumkin
GONE_STATUSES: frozenset[str] = frozenset({BotStatus.LEFT, BotStatus.KICKED})


# ⚠️ GURUH TURINI A'ZOLAR SONIDAN ANIQLAMANG.
#
# Avvalgi loyihada `member_count <= 2` → «keraksiz guruh» degan qoida bor
# edi. U NOTO'G'RI: guruhda bir necha odam o'tirib, ichida mijoz umuman
# bo'lmasligi mumkin (ichki guruh, tashkilotchilar guruhi). Bot esa
# ichkarida kim borligini bilmaydi — a'zolar soni bilan taxmin qilish
# ishonch bilan noto'g'ri ma'lumot beradi.
#
# Amaldagi qoida: **ishchi guruhni HUDUD belgilaydi.** Xodimga
# biriktirilgan, lekin hududsiz guruh — ishchi guruh emas. Qo'shimcha
# maydon kerak emas: `_structural_block()` allaqachon hududsiz guruhga
# so'rovnoma yuborishni rad etadi, ya'ni bunday guruh jimgina hech narsa
# olmaydi — aynan kerakli xatti-harakat. Admin guruhni «keraksiz» deb
# belgilashi = hududini bo'shatishi.


class BindSource(StrEnum):
    """Biriktirishni kim qildi.

    `MANUAL` — admin panelda qo'lda. Bunga avtomatika hech qachon
    tegmaydi (`GroupService.autobind` uni birinchi bo'lib tekshiradi).
    """

    AUTO = "auto"
    MANUAL = "manual"


# ── Guruh nomidan hudud taxmini ───────────────────────────────
#
# Guruhlar odatda "Bonvi Samarqand", "Buxoro mijozlar", "Farg'ona savdo"
# deb nomlanadi. Nomdan hududni topib bersak, admin 13 ta variantdan
# tanlash o'rniga tayyor qiymatni tasdiqlaydi — bu eng ko'p takrorlanadigan
# amal, shuning uchun eng arzon bo'lishi kerak.
#
# Taxmin — TAKLIF, qaror emas: bog'lanish baribir admin `PATCH` qilganda
# yoziladi va allaqachon biriktirilgan hudud hech qachon ustidan yozilmaydi.

# O'zbekcha nomlarda apostrof uch xil belgida uchraydi (', ', ʻ) va
# ba'zan umuman yozilmaydi ("Fargona"). Solishtirishdan oldin hammasini
# olib tashlaymiz — "Farg'ona" ham, "Fargʻona" ham, "Fargona" ham mos keladi.
_APOSTROPHES = "'’‘ʻʼ`´"

# Qo'shimcha atamalar: viloyat markazlari va ruscha/inglizcha yozilishi
REGION_ALIASES: dict[str, tuple[str, ...]] = {
    "Toshkent": ("Tashkent",),
    "Farg'ona vodiysi": ("Farg'ona", "Fergana", "Vodiy"),
    "Samarqand": ("Samarkand",),
    "Buxoro": ("Bukhara",),
    "Xorazm": ("Urganch", "Khorezm"),
    "Surxondaryo": ("Termiz",),
    "Andijon": ("Andijan",),
    "Namangan": (),
    "Qashqadaryo": ("Qarshi",),
    "Navoiy": ("Navoi",),
    "Jizzax": ("Jizzakh",),
    "Sirdaryo": ("Guliston",),
    "Qoraqalpog'iston": ("Qoraqalpoq", "Nukus", "Karakalpak"),
}


def normalize_region_text(value: str) -> str:
    """Solishtirish uchun matnni soddalashtiradi.

    Kichik harf, apostroflarsiz, ortiqcha bo'shliqlarsiz.
    """
    lowered = value.casefold()
    stripped = "".join(ch for ch in lowered if ch not in _APOSTROPHES)
    return " ".join(stripped.split())


# (normallashgan atama, hudud) — uzunidan qisqasiga.
# Uzunini oldin tekshiramiz: "Farg'ona vodiysi" "Farg'ona" dan ustun.
_REGION_TERMS: list[tuple[str, str]] = sorted(
    (
        (normalize_region_text(term), region)
        for region in SUGGESTION_REGIONS
        for term in (region, *REGION_ALIASES.get(region, ()))
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def suggest_region(title: str | None, known: list[str] | None = None) -> str | None:
    """Guruh nomidan hududni taxmin qiladi. Topilmasa — `None`.

    `known` — bazadagi haqiqiy hudud nomlari. Ular BIRINCHI tekshiriladi,
    chunki admin viloyatni bo'lib tashlagan bo'lishi mumkin
    («Samarqand shimol»). Faqat shundan keyin kodda yozilgan
    `SUGGESTION_REGIONS` lug'atiga murojaat qilinadi — u endi ro'yxat
    emas, shunchaki taxmin uchun sinonimlar to'plami («Nukus» →
    Qoraqalpog'iston).

    Topilmasa bo'sh qaytadi: noto'g'ri taxmin qilgandan ko'ra hech narsa
    taklif qilmagan yaxshi — admin xato qiymatni ko'r-ko'rona tasdiqlab
    yuborishi mumkin.
    """
    if not title:
        return None

    haystack = normalize_region_text(title)
    if not haystack:
        return None

    # Bazadagi nomlar ustun. Uzunroq nom oldin tekshiriladi, aks holda
    # «Samarqand» «Samarqand shimol» dan oldin topilib qolardi
    for name in sorted(known or [], key=len, reverse=True):
        term = normalize_region_text(name)
        if term and term in haystack:
            return name

    for term, region in _REGION_TERMS:
        if term and term in haystack:
            return region
    return None
