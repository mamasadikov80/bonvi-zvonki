"""`GET /calls` — jadval sarlavhasidagi har bir saralash ustuni.

Foydalanuvchi ustun sarlavhasini bosganda kutadigan narsa oddiy:
qatorlar O'SHA ustun bo'yicha, o'zi tanlagan yo'nalishda tizilsin.
Router ustunni oq ro'yxatdan oladi (router.py:203-215), shuning uchun
xato SQL emas — xato NOTO'G'RI USTUN yoki teskari yo'nalish bo'lishi
mumkin, va uni faqat haqiqiy ma'lumot ustida ko'rish mumkin.

USTUNDA HAR XIL QIYMAT BO'LISHI SHART
  `dataset` fixture'i hamma qo'ng'iroqni bir xil til, bir xil client va
  bir xil holat bilan yaratadi. Bunday to'plamda «to'g'ri tartib»
  har doim to'g'ri ko'rinadi va test hech narsani ushlamaydi. Shuning
  uchun `db` fixture'i o'z yozuvlarimizga ataylab farq kiritadi.

NULL LAR OXIRIDA
  Bahosi hali qo'yilmagan qo'ng'iroq — ro'yxatning eng qimmatli emas,
  eng KEYINGI qatori. `nullslast` (router.py:220) shuni ta'minlaydi:
  «ballari o'sish tartibida» so'ralganda bahosizlar ro'yxat boshini
  egallab olmasligi kerak.
"""

import uuid
from datetime import datetime

import pytest

LIST = "/api/v1/calls"


def _token() -> str:
    """Bazadagi haqiqiy yozuvlarga mos kelmaydigan noyob bo'lak."""
    return f"pytest{uuid.uuid4().hex[:10]}"


async def _items(client, **params):
    response = await client.get(LIST, params={"page_size": 200, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _saralangan(qiymatlar: list, order: str) -> bool:
    return qiymatlar == sorted(qiymatlar, reverse=order == "desc")


# ══════════════════════════════════════════════════════════════
#  Ustun bo'yicha tartib
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_sana(admin_client, dataset, order) -> None:
    data = await dataset(scores=[90, 80, 70], days_ago=[3, 1, 2])

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="date", order=order
    )

    vaqtlar = [datetime.fromisoformat(item["started_at"]) for item in items]
    assert len(vaqtlar) == 3
    assert _saralangan(vaqtlar, order)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_davomiylik(admin_client, dataset, order) -> None:
    data = await dataset(scores=[90, 80, 70], durations=[300, 100, 200])

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="duration", order=order
    )

    davomiyliklar = [item["duration_sec"] for item in items]
    assert sorted(davomiyliklar) == [100, 200, 300]
    assert _saralangan(davomiyliklar, order)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_ball(admin_client, dataset, order) -> None:
    data = await dataset(scores=[70, 95, 50])

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="score", order=order
    )

    ballar = [item["score"] for item in items]
    assert sorted(ballar) == [50, 70, 95]
    assert _saralangan(ballar, order)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_holat_qoidabuzarlik_soni_boyicha(
    admin_client, dataset, order
) -> None:
    """«Holat» ustuni qoidabuzarlik sonini ko'rsatadi (router.py:210-215),
    demak saralash ham shu son bo'yicha ketishi kerak."""
    data = await dataset(scores=[90, 80, 70], red_flags=[2, 0, 1])

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="status", order=order
    )

    sonlar = [item["red_flag_count"] for item in items]
    assert sorted(sonlar) == [0, 1, 2]
    assert _saralangan(sonlar, order)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_mijoz_nomi(admin_client, dataset, db, order) -> None:
    token = _token()
    data = await dataset(scores=[90, 80, 70])

    # Uchala qo'ng'iroq uchun uchta har xil client
    await db.client(data.client_id, name=f"{token}aaa")
    ikkinchi = await db.new_client(f"{token}bbb", agent_id=data.agent_id)
    uchinchi = await db.new_client(f"{token}ccc", agent_id=data.agent_id)
    await db.call(data.calls[1].call_id, client_id=ikkinchi)
    await db.call(data.calls[2].call_id, client_id=uchinchi)

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="client", order=order
    )

    nomlar = [item["client_name"] for item in items]
    assert sorted(nomlar) == [f"{token}aaa", f"{token}bbb", f"{token}ccc"]
    assert _saralangan(nomlar, order)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_saralash_xodim_ismi(admin_client, dataset, db, order) -> None:
    """Bitta xodim ichida ismlar bir xil, `agent_id` esa ikkinchi xodimni
    qabul qilmaydi — shuning uchun bu YAGONA test noyob `search` bo'lagi
    bilan toraytiradi. Token tasodifiy, bazadagi boshqa hech qanday
    yozuvga mos kelmaydi, ya'ni izolyatsiya saqlanadi.
    """
    token = _token()
    birinchi = await dataset(scores=[90, 80])
    ikkinchi = await dataset(scores=[70])
    await db.agent(birinchi.agent_id, full_name=f"{token}aaa")
    await db.agent(ikkinchi.agent_id, full_name=f"{token}bbb")

    items = await _items(admin_client, search=token, sort="agent", order=order)

    ismlar = [item["agent_name"] for item in items]
    assert len(ismlar) == 3, "token boshqa yozuvlarni ham tortib keldi"
    assert sorted(set(ismlar)) == [f"{token}aaa", f"{token}bbb"]
    assert _saralangan(ismlar, order)


# ══════════════════════════════════════════════════════════════
#  NULL joylashuvi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_bahosiz_qongiroq_royxat_boshiga_chiqmaydi(
    admin_client, dataset, order
) -> None:
    """`sort=score&order=asc` — «eng past ballar oldinda» degani.

    Bahosi YO'Q qo'ng'iroq «eng past ball» emas: u umuman baholanmagan.
    Agar u ro'yxat boshida tursa, menejer eng muammoli qo'ng'iroqlarni
    ko'rish o'rniga hali qayta ishlanmaganlarni ko'radi.
    """
    data = await dataset(scores=[90, 70], unscored_calls=1)

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="score", order=order
    )

    ballar = [item["score"] for item in items]
    assert len(ballar) == 3
    assert ballar[0] is not None, "bahosiz qo'ng'iroq ro'yxat boshini egalladi"
    assert ballar[-1] is None
    assert ballar == ([70, 90, None] if order == "asc" else [90, 70, None])


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_mijozsiz_qongiroq_ham_oxirida_turadi(
    admin_client, dataset, db, order
) -> None:
    """Client `SET NULL` bo'lishi mumkin — o'sha qator ham oxirida."""
    data = await dataset(scores=[90, 80])
    await db.call(data.calls[0].call_id, client_id=None)

    items = await _items(
        admin_client, agent_id=str(data.agent_id), sort="client", order=order
    )

    nomlar = [item["client_name"] for item in items]
    assert len(nomlar) == 2
    assert nomlar[0] is not None
    assert nomlar[-1] is None
