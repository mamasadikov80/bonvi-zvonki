"""Parol xeshlash — `src/core/security.py`.

Asosiy talab: baza qo'lga tushsa ham parollar o'qib bo'lmasin. Ya'ni
`users.password_hash` ustunida HECH QACHON ochiq matn turmasligi kerak.

Testlarning bir qismi — sof unit (bazasiz), bir qismi bazadagi haqiqiy
yozuvni tekshiradi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.database import SessionFactory
from src.core.security import hash_password, verify_password
from src.modules.users.infrastructure.models import UserModel

BCRYPT_PREFIKSLARI = ("$2a$", "$2b$", "$2y$")


# ══════════════════════════════════════════════════════════════
#  Sof unit — bazasiz
# ══════════════════════════════════════════════════════════════


def test_xesh_ochiq_matnni_ozida_saqlamaydi() -> None:
    parol = "juda-maxfiy-parol-123"
    xesh = hash_password(parol)

    assert xesh != parol
    assert parol not in xesh
    assert xesh.startswith(BCRYPT_PREFIKSLARI)


def test_bir_xil_parol_har_safar_boshqa_xesh_beradi() -> None:
    """Har xeshda o'z «tuz»i (salt) bor.

    Bo'lmasa, bir xil parolli ikki foydalanuvchi bazada bir xil qator
    bilan turardi — birining paroli topilsa ikkinchisiniki ham ochilardi.
    """
    parol = "bir-xil-parol"
    birinchi = hash_password(parol)
    ikkinchi = hash_password(parol)

    assert birinchi != ikkinchi
    assert verify_password(parol, birinchi)
    assert verify_password(parol, ikkinchi)


def test_verify_togri_parolni_tasdiqlaydi_notogrisini_rad_etadi() -> None:
    xesh = hash_password("toshkent-2025")

    assert verify_password("toshkent-2025", xesh) is True
    assert verify_password("toshkent-2024", xesh) is False
    assert verify_password("", xesh) is False
    assert verify_password("TOSHKENT-2025", xesh) is False, "registr muhim"


@pytest.mark.parametrize(
    "buzilgan",
    [
        pytest.param("", id="bosh"),
        pytest.param("xesh-emas", id="axlat"),
        pytest.param("$2b$12$", id="tuzsiz"),
        # ⚠️ Bu holat REGRESSIYA sinovi: `bcrypt` ning Rust yadrosi
        # aynan shu shaklda `PanicException` beradi va u `BaseException`
        # dan meros oladi. `verify_password()` dagi `except` toraytirilsa
        # login yana 500 bilan qulaydi.
        pytest.param("$2b$12$qisqa", id="chala-bcrypt"),
    ],
)
def test_verify_buzilgan_xesh_bilan_yiqilmaydi(buzilgan: str) -> None:
    """Bazada buzilgan qator uchrasa — 500 emas, oddiy «rad etildi».

    `password_hash` ustuniga chala qiymat tushib qolishi mumkin:
    to'xtab qolgan migratsiya, qo'lda tahrirlangan yozuv, import
    skriptidagi xato. Bunday holatda kirish oqimi «parol noto'g'ri»
    deb javob berishi kerak — butun endpointni yiqitmasligi kerak.
    """
    assert verify_password("istalgan-parol", buzilgan) is False


def test_bcrypt_72_bayt_chegarasi_yiqilishga_olib_kelmaydi() -> None:
    """bcrypt 72 baytdan uzunini qabul qilmaydi — kod uni o'zi kesadi.

    Kesilmasa uzun parol bilan ro'yxatdan o'tish 500 bilan tugardi.
    """
    uzun = "a" * 200
    xesh = hash_password(uzun)

    assert verify_password(uzun, xesh) is True
    # 72-baytgacha bir xil bo'lgani uchun kesilgandan keyin ham mos keladi
    assert verify_password("a" * 100, xesh) is True
    assert verify_password("b" * 200, xesh) is False


def test_kirill_va_emoji_parollar_ishlaydi() -> None:
    """UTF-8 belgilar bayt chegarasida ham to'g'ri ishlanadi."""
    for parol in ("парол-ЖЖЖ", "паролище-очень-длинное-🔐", "o'zbekcha-ʼparol"):
        assert verify_password(parol, hash_password(parol)) is True


# ══════════════════════════════════════════════════════════════
#  Bazadagi haqiqiy yozuv
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bazada_parol_ochiq_matnda_saqlanmaydi(make_user) -> None:
    """Hisob yaratilgach `password_hash` ustunini o'z ko'zimiz bilan ko'ramiz."""
    parol = "pytest-ochiq-parol-777"
    user = await make_user(password=parol)

    async with SessionFactory() as session:
        row = (
            await session.execute(select(UserModel).where(UserModel.id == user.id))
        ).scalar_one()

    assert row.password_hash != parol
    assert parol not in row.password_hash
    assert row.password_hash.startswith(BCRYPT_PREFIKSLARI)
    assert verify_password(parol, row.password_hash) is True


@pytest.mark.asyncio
async def test_mavjud_hisoblarning_hammasi_xeshlangan() -> None:
    """Bazadagi HAR BIR yozuv bcrypt formatida.

    Bir marta bo'lsa ham ochiq matn yozib qo'yilgan bo'lsa (masalan,
    migratsiya yoki seed skriptida), shu test darhol qizaradi.
    """
    async with SessionFactory() as session:
        xeshlar = (await session.execute(select(UserModel.password_hash))).scalars().all()

    assert xeshlar, "bazada birorta ham foydalanuvchi yo'q — seed ishlamagan"
    xeshlanmagan = [x for x in xeshlar if not str(x).startswith(BCRYPT_PREFIKSLARI)]
    assert xeshlanmagan == [], "bcrypt formatida bo'lmagan parol topildi"
