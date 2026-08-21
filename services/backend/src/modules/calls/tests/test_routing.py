"""Tur RAQAM bo'yicha aniqlanadi — sof unit test, bazasiz.

NEGA BU FAYL BOR. Butun tasniflash mantig'i shu yerdagi uchta
funksiyaga tayanadi va ular ishlamasa xato JIMGINA bo'ladi: ichki
suhbat savdo sifatida baholanib, xodimning o'rtachasini pasaytiradi
yoki aksincha — savdo suhbati baholanmay qoladi va buni hech kim
sezmaydi (sukut bo'yicha ro'yxatda faqat savdo ko'rsatiladi).
"""

from src.modules.calls.application.internal_directory import parse_rules
from src.modules.calls.domain.entities import CallType
from src.modules.calls.domain.routing import (
    CompanyLines,
    is_extension,
    phone_key,
    reason_uz,
    resolve_type,
)

#: Kompaniya liniyalari — o'rganilgan aniq raqamlar
BIZNIKI = CompanyLines(keys=frozenset({"997938700", "997928700"}))


# ══════════════════════════════════════════════════════════════
#  Raqam kaliti
# ══════════════════════════════════════════════════════════════


def test_bir_xil_raqam_uch_formatda_bitta_kalit_beradi() -> None:
    """Raqam uch manbadan uch ko'rinishda keladi — kalit BITTA.

    Admin panelda «+998 99 793-87-00», MoyZvonki'da «+998997938700»,
    eksportda «997938700». Uchalasi bitta xodimga tushishi kerak."""
    assert (
        phone_key("+998 99 793-87-00")
        == phone_key("998997938700")
        == phone_key("997938700")
        == "997938700"
    )


def test_qisqa_raqam_kalit_bermaydi() -> None:
    """⚠️ «1234567» kalit sifatida XAVFLI: u istalgan raqamning oxiriga
    mos kelib, begona suhbatni ichki deb belgilab qo'yardi."""
    assert phone_key("1234567") is None
    assert phone_key("") is None
    assert phone_key(None) is None


def test_ats_qisqa_raqami_taniladi() -> None:
    """Tashqaridan bunday raqamga qo'ng'iroq qilib bo'lmaydi."""
    assert is_extension("1042") is True
    assert is_extension("101") is True
    # Bo'sh qiymat ichki raqam EMAS — u haqda hech narsa bilmaymiz
    assert is_extension(None) is False
    assert is_extension("") is False
    # To'liq mobil raqam — tashqi
    assert is_extension("+998901234567") is False


# ══════════════════════════════════════════════════════════════
#  Tur
# ══════════════════════════════════════════════════════════════


def test_kompaniya_liniyasi_ichki() -> None:
    assert resolve_type("+998997938700", BIZNIKI) is CallType.INTERNAL
    # Formatlash farqi ahamiyatsiz
    assert resolve_type("997928700", BIZNIKI) is CallType.INTERNAL


def test_ats_raqami_ichki() -> None:
    assert resolve_type("1042", BIZNIKI) is CallType.INTERNAL


def test_tashqi_raqam_savdo() -> None:
    assert resolve_type("+998901234567", BIZNIKI) is CallType.SALES


def test_nomalum_holatda_savdo() -> None:
    """⚠️ Raqamsiz qo'ng'iroq BAHOLANADI.

    Ikki xatoning narxi teng emas: noto'g'ri «ichki» savdo suhbatini
    jimgina baholashdan chetlatadi va buni hech kim sezmaydi;
    noto'g'ri «savdo» esa menejerga ko'rinadi va tuzatiladi."""
    assert resolve_type(None, BIZNIKI) is CallType.SALES
    assert resolve_type("", BIZNIKI) is CallType.SALES


def test_bosh_royxatda_hammasi_savdo() -> None:
    """Ro'yxat bo'sh bo'lsa hech narsa ichki bo'lolmaydi.

    Quvur bunday holatda umuman ishlamaydi (`DirectoryEmptyError`),
    lekin funksiyaning o'zi ham taxmin qilmasligi kerak."""
    assert resolve_type("+998997938700", CompanyLines()) is CallType.SALES


# ══════════════════════════════════════════════════════════════
#  Suffiks qoidasi (`*700`)
# ══════════════════════════════════════════════════════════════


def test_suffiks_qoidasi_royxatda_yoq_raqamni_ham_tanidi() -> None:
    """⚠️ ENG KO'P UCHRAYDIGAN HOLAT.

    O'lchandi: Bonvi'da «Asosiy Ombor Zakas», «Logistika Bo'limi»,
    «Rejalashtirish», «Bugalteriya», «Transport Bulimi» kabi bo'limlar
    MoyZvonki'da alohida foydalanuvchi EMAS — ularning raqami hech
    qachon `src_number` bo'lib kelmaydi va o'z-o'zidan o'rganilmaydi.
    Shunga qaramay hammasi bitta blokdan: `…700`. Suffikssiz shu
    bo'limlar bilan bo'lgan 908 ta suhbat «savdo» deb baholanardi."""
    lines = CompanyLines(keys=frozenset(), suffixes=("700",))

    assert resolve_type("+998951730700", lines) is CallType.INTERNAL
    assert resolve_type("+998901234567", lines) is CallType.SALES


def test_suffiks_qisqa_raqamni_ushlamaydi() -> None:
    """`700` degan ATS raqami suffiksga «mos» ko'rinadi, lekin u
    baribir ichki — qisqa raqam qoidasi bilan tutiladi. Muhimi:
    suffiks to'liq raqamda tekshiriladi va tasodifiy mos kelish
    bo'lmaydi."""
    lines = CompanyLines(keys=frozenset(), suffixes=("700",))

    assert resolve_type("700", lines) is CallType.INTERNAL  # ATS raqami


def test_sabab_har_doim_raqamni_korsatadi() -> None:
    """Qo'lda tuzatish yo'q — qaror TEKSHIRIB bo'ladigan bo'lishi kerak."""
    ichki = reason_uz(CallType.INTERNAL, "+998997938700")
    tashqi = reason_uz(CallType.SALES, "+998901234567")

    assert "+998997938700" in ichki
    assert "+998901234567" in tashqi
    assert "raqamsiz" in reason_uz(CallType.SALES, None)


# ══════════════════════════════════════════════════════════════
#  Sozlamadagi qo'lda kiritilgan raqamlar
# ══════════════════════════════════════════════════════════════


def test_sozlama_suffiks_qoidasini_ajratadi() -> None:
    """`*700` — qoida, raqam emas."""
    raqamlar, suffikslar = parse_rules("997938700\n*700\n*0")

    assert raqamlar == {"997938700"}
    # `*0` RAD ETILADI: bunday qoida raqamlarning o'ndan birini
    # «ichki» qilib qo'yardi va o'sha savdo suhbatlari jimgina
    # baholanmasdi
    assert suffikslar == ("700",)


def test_sozlama_har_qanday_ajratgichni_tushunadi() -> None:
    """Admin vergul bilan ham, yangi qator bilan ham yozishi mumkin."""
    matn = (
        "+998 99 793-87-00, 998997928700\n"
        "997918700; +998990178700\n"
        "991108700 998957938700"  # bitta qatorda ikkita raqam
    )
    raqamlar, _ = parse_rules(matn)
    assert raqamlar == {
        "997938700",
        "997928700",
        "997918700",
        "990178700",
        "991108700",
        "957938700",
    }


def test_sozlamadagi_buzuq_bolak_royxatni_yiqitmaydi() -> None:
    """Bitta noto'g'ri yozuv butun ro'yxatni yo'q qilmasligi kerak."""
    assert parse_rules("sklad: 997938700, xato")[0] == {"997938700"}
    assert parse_rules(None) == (set(), ())
