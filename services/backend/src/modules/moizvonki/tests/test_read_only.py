"""MoyZvonki integratsiyasi FAQAT O'QIYDI — buni qulflab qo'yadigan test.

NEGA BU TEST BOR. MoyZvonki — mijozning ish tizimi. U yerda biror
narsani o'zgartirish, qo'shish yoki o'chirish bizning vakolatimizda
emas: bitta noto'g'ri `action` haqiqiy qo'ng'iroq yozuvini yoki xodim
kartochkasini buzishi mumkin.

Qoida izohga ishonib qoldirilmagan — `MoizvonkiClient._post()` da
oq ro'yxat bor. Bu testlar o'sha qulf ishlayotganini va ro'yxat
kengayib ketmaganini tekshiradi.
"""

import pytest

from src.modules.moizvonki.domain.entities import (
    MoizvonkiCredentials,
    MoizvonkiError,
)
from src.modules.moizvonki.infrastructure.client import MoizvonkiClient

#: Ro'yxat ATAYLAB shu yerda TAKRORLANGAN. Kod tomonidan import
#: qilinsa, kimdir `READ_ONLY_ACTIONS` ga yangi action qo'shganda test
#: ham «o'zi bilan» kengayib ketardi va hech narsa ushlanmasdi.
KUTILGAN = {
    "calls.list",
    "company.list_group",
    "company.list_employee",
}

#: MoyZvonki hujjatida uchraydigan (yoki uchrashi mumkin bo'lgan)
#: o'zgartiruvchi amallar. Hech biri o'tmasligi kerak.
YOZUV_AMALLARI = [
    "calls.add",
    "calls.delete",
    "calls.update",
    "company.add_employee",
    "company.update_employee",
    "company.delete_employee",
    "company.add_group",
    "contacts.add",
    "contacts.update",
    "contacts.delete",
]


def _client() -> MoizvonkiClient:
    return MoizvonkiClient(
        MoizvonkiCredentials(
            base_url="https://example.moizvonki.ru",
            user_name="test@example.com",
            api_key="test-key",
        )
    )


def test_oq_royxat_kengaymagan() -> None:
    """Ro'yxatga yangi action qo'shilsa — bu test darhol yiqiladi.

    Bu ataylab «qattiq» test: MoyZvonki'ga yangi so'rov qo'shish
    ONGLI qaror bo'lishi kerak, tasodifan sodir bo'lmasligi kerak.
    """
    assert set(MoizvonkiClient.READ_ONLY_ACTIONS) == KUTILGAN


def test_barcha_ruxsat_etilganlar_faqat_oqish() -> None:
    """Har bir ruxsat etilgan action nomi `list` bilan bog'liq bo'lsin."""
    for action in MoizvonkiClient.READ_ONLY_ACTIONS:
        assert "list" in action, f"«{action}» o'qish amaliga o'xshamaydi"


@pytest.mark.parametrize("action", YOZUV_AMALLARI)
@pytest.mark.asyncio
async def test_yozuv_amali_yuborilmaydi(action: str) -> None:
    """Yozuv action i TARMOQQA CHIQMASDAN to'xtatiladi.

    Diqqat: klient hech qanday HTTP so'rov qilmaydi — xato `_post()`
    ning birinchi qatorida ko'tariladi. Shuning uchun bu test tarmoqsiz
    ham ishlaydi va haqiqiy MoyZvonki'ga hech narsa yubormaydi.
    """
    client = _client()
    try:
        with pytest.raises(MoizvonkiError) as exc:
            await client._post(action)
        assert "faqat" in str(exc.value).lower()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_xato_xabari_ruxsat_etilganlarni_koarsatadi() -> None:
    """Xato xabari nima mumkinligini aytsin — dasturchi taxmin qilmasin."""
    client = _client()
    try:
        with pytest.raises(MoizvonkiError) as exc:
            await client._post("company.update_employee")
        message = str(exc.value)
        for allowed in MoizvonkiClient.READ_ONLY_ACTIONS:
            assert allowed in message
    finally:
        await client.aclose()
