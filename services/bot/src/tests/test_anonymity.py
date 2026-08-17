"""`core/anonymity.py` — loyihaning BUZILMAS qoidasi.

Guruhda kim qanday baho qo'yganini hech kim bila olmasligi kerak: na
savdo xodimi, na admin, na backend, na loglarni o'qigan odam. Telegram
ID bot jarayonidan tashqariga CHIQMAYDI — u faqat hash hisoblash uchun
ishlatiladi.

Bu testlar shu va'daning uchta qismini tekshiradi:

  1. QAYTARILADIGANLIK — bir xil kirishga bir xil natija, aks holda
     «bir odam bir marta» qoidasi ishlamaydi.
  2. BOG'LANMASLIK — token tuz (salt) vazifasini bajaradi: bitta
     odamning turli so'rovnomalardagi javoblari bir-biriga bog'lanmaydi.
  3. ANONIMLIK — xom Telegram ID natijada hech qanday shaklda YO'Q.

Sof unit test: Telegram API ga chiqmaydi, tarmoq talab qilmaydi.
"""

from src.core.anonymity import HASH_LENGTH, respondent_hash, short

TOKEN = "srv_abc123"
BOSHQA_TOKEN = "srv_xyz789"
USER_ID = 123456789


# ══════════════════════════════════════════════════════════════
#  1. Qaytariladiganlik
# ══════════════════════════════════════════════════════════════


def test_bir_xil_kirish_bir_xil_natija_beradi() -> None:
    """«Siz allaqachon baho bergansiz» shu tenglikka tayanadi."""
    assert respondent_hash(TOKEN, USER_ID) == respondent_hash(TOKEN, USER_ID)


def test_natija_uzunligi_shartnomadagidek() -> None:
    """Backend ustuni `String(64)` — undan uzun qiymat kesilib ketardi."""
    digest = respondent_hash(TOKEN, USER_ID)

    assert len(digest) == HASH_LENGTH == 64
    assert all(c in "0123456789abcdef" for c in digest)


# ══════════════════════════════════════════════════════════════
#  2. Bog'lanmaslik
# ══════════════════════════════════════════════════════════════


def test_turli_tokenda_bir_odam_boshqa_hash_oladi() -> None:
    """Aks holda «shu odam har safar 2 qo'yadi» degan profil tuzilardi."""
    assert respondent_hash(TOKEN, USER_ID) != respondent_hash(BOSHQA_TOKEN, USER_ID)


def test_bir_so_rovnomada_turli_odam_turli_hash_oladi() -> None:
    assert respondent_hash(TOKEN, USER_ID) != respondent_hash(TOKEN, USER_ID + 1)


def test_qoshni_id_lar_ham_butunlay_boshqa_natija_beradi() -> None:
    """sha256 — bitta bitning farqi butun natijani o'zgartiradi."""
    birinchi = respondent_hash(TOKEN, 1)
    ikkinchi = respondent_hash(TOKEN, 2)

    umumiy = sum(a == b for a, b in zip(birinchi, ikkinchi, strict=True))
    assert umumiy < 20, "Hash'lar juda o'xshash — namuna sezilib qolardi"


def test_token_va_id_chegarasi_chalkashmaydi() -> None:
    """`"a:1" + "23"` va `"a:12" + "3"` bir xil hash bermasligi kerak."""
    assert respondent_hash("srv_a", 123) != respondent_hash("srv_a:1", 23)


# ══════════════════════════════════════════════════════════════
#  3. Anonimlik kafolati
# ══════════════════════════════════════════════════════════════


def test_xom_telegram_id_natijada_yoq() -> None:
    """Eng muhim tekshiruv: ID hech qanday ko'rinishda sizib chiqmasin."""
    digest = respondent_hash(TOKEN, USER_ID)

    assert str(USER_ID) not in digest
    assert f"{USER_ID:x}" not in digest
    assert TOKEN not in digest


def test_haqiqiy_telegram_id_lar_sizib_chiqmaydi() -> None:
    """Telegram ID lari kamida 6-7 xonali — aynan shular tekshiriladi.

    (Qisqa raqamlar sinalmaydi: «1» yoki «42» 64 belgili hexdigest
    ichida tasodifan uchraydi va bu hech narsani anglatmaydi.)
    """
    for user_id in (999_999, 123_456_789, 7_123_456_789, 8_999_999_999):
        digest = respondent_hash(TOKEN, user_id)

        assert str(user_id) not in digest, f"{user_id} hash ichida ko'rinib qoldi"
        assert f"{user_id:x}" not in digest
        assert f"{user_id:o}" not in digest


def test_short_faqat_qisqartma_beradi() -> None:
    """To'liq hash ham logga tushmasligi ma'qul — u bazadagi qator bilan
    solishtirilsa, kim qachon baho berganini taxmin qilish oson bo'lardi."""
    digest = respondent_hash(TOKEN, USER_ID)

    qisqa = short(digest)

    assert qisqa == f"{digest[:8]}…"
    assert len(qisqa) < len(digest)
    assert str(USER_ID) not in qisqa


def test_short_bosh_qiymatda_chiziqcha_beradi() -> None:
    """Log satri «—» bo'lsin, `None` yoki bo'shliq emas."""
    assert short("") == "—"
