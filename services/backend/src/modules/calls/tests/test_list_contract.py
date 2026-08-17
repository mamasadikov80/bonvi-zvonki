"""`GET /calls` — ro'yxatning buzilmas shartnomasi.

Jadval foydalanuvchi uchun bitta narsani va'da qiladi: «pastdagi
«Jami: N» soni yuqoridagi qatorlar bilan bir xil ma'lumotni sanaydi».
`total` alohida `SELECT count(*)` bilan olinadi (router.py:197-199), qatorlar
esa o'sha so'rovning `LIMIT` li varianti bilan — ikkalasi bir xil `stmt`
dan o'sishi SHART. Bir joyda filtr qo'shilib, ikkinchisida unutilsa
foydalanuvchi «12 ta topildi» yozuvi ostida 7 ta qatorni ko'radi.

Har test o'ziga xos xodim yaratadi va HAR bir so'rovni `agent_id`
bilan toraytiradi — bazadagi boshqa qo'ng'iroqlar natijaga qo'shilmaydi.
"""

from datetime import UTC, datetime, timedelta

import pytest

LIST = "/api/v1/calls"


async def _calls(client, data, **params):
    """AYNAN bitta xodimning qo'ng'iroqlarini so'raydi.

    `page_size=200` — testlardagi to'plam bitta sahifaga sig'sin,
    shunda `total` va qatorlar sonini to'g'ridan-to'g'ri solishtirsa
    bo'ladi.
    """
    response = await client.get(
        LIST, params={"agent_id": str(data.agent_id), "page_size": 200, **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


# ══════════════════════════════════════════════════════════════
#  «Jami» va qatorlar bir xil filtrdan o'tadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filtr",
    ["filtrsiz", "score_min", "score_max", "needs_review", "sana", "qidiruv", "aralash"],
)
async def test_total_va_qatorlar_bir_xil_filtrdan_otadi(
    admin_client, dataset, filtr
) -> None:
    """Qaysi filtr qo'yilmasin, `total` ko'rinayotgan qatorlarni sanaydi."""
    data = await dataset(
        scores=[95, 80, 60, 40],
        days_ago=[1, 2, 3, 4],
        durations=[100, 200, 300, 400],
        red_flags=[1, 0, 2, 0],
        unscored_calls=2,
    )

    params = {
        "filtrsiz": {},
        "score_min": {"score_min": 60},
        "score_max": {"score_max": 80},
        "needs_review": {"needs_review": "false"},
        "sana": {"date_from": data.calls[2].started_at.isoformat()},
        "qidiruv": {"search": data.agent_name},
        "aralash": {"score_min": 60, "score_max": 95, "search": data.agent_name},
    }[filtr]

    body = await _calls(admin_client, data, **params)

    # Filtr hamma narsani kesib tashlasa test bo'sh o'tib ketardi
    assert body["total"] > 0, f"«{filtr}» filtri hech narsa qoldirmadi"
    assert body["total"] == len(body["items"])


@pytest.mark.asyncio
async def test_join_dublikat_yaratmaydi(admin_client, dataset) -> None:
    """N ta qo'ng'iroq → AYNAN N ta qator.

    So'rov uchta jadvalga `JOIN` qiladi (xodim, client, baho). Agar
    bironta bog'lanish «bir qo'ng'iroq — bir qator» qoidasini buzsa
    (masalan bitta qo'ng'iroqqa ikkita baho yozilsa), foydalanuvchi
    bir xil qo'ng'iroqni ro'yxatda ikki marta ko'radi va «Jami» soni
    ham shishib ketadi.
    """
    data = await dataset(scores=[90, 80, 70, 60], unscored_calls=3)

    body = await _calls(admin_client, data)

    ids = [item["id"] for item in body["items"]]
    assert data.call_count == 4
    assert body["total"] == 7  # 4 baholangan + 3 bahosiz
    assert len(ids) == 7
    assert len(set(ids)) == 7, "ro'yxatda takrorlangan qo'ng'iroq bor"


@pytest.mark.asyncio
async def test_bahosiz_qongiroq_filtrsiz_royxatda_qoladi(
    admin_client, dataset
) -> None:
    """Baho — ixtiyoriy bog'lanish: bo'lmasa ham qo'ng'iroq ko'rinadi.

    Bu quyidagi ball filtri testlari uchun nazorat nuqtasi: filtrsiz
    holat va filtrli holat bahosizlarga bir xil munosabatda bo'lishi
    kerak.
    """
    data = await dataset(scores=[90], unscored_calls=2)

    body = await _calls(admin_client, data)

    assert body["total"] == 3
    bahosizlar = [item for item in body["items"] if item["score"] is None]
    assert len(bahosizlar) == 2
    # Bahosi yo'q qo'ng'iroq «tekshiruv kutayotgan» deb ko'rsatilmaydi
    assert all(item["needs_review"] is False for item in bahosizlar)
    assert all(item["red_flag_count"] == 0 for item in bahosizlar)


# ══════════════════════════════════════════════════════════════
#  Sana oralig'i
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_date_from_eski_qongiroqni_kesadi(admin_client, dataset) -> None:
    """Nazorat testi: oraliqning quyi chegarasi ishlaydi."""
    data = await dataset(scores=[90, 70], days_ago=[1, 40])

    chegara = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    body = await _calls(admin_client, data, date_from=chegara)

    assert body["total"] == 1
    assert body["items"][0]["score"] == 90


@pytest.mark.asyncio
async def test_date_to_oxirgi_kunni_yoqotmaydi(admin_client, dataset) -> None:
    """Vaqtsiz chegara — «shu kun ham kirsin» degani."""
    data = await dataset(scores=[90], days_ago=[0])  # bugungi qo'ng'iroq

    bugun = datetime.now(UTC).date().isoformat()
    body = await _calls(admin_client, data, date_to=bugun)

    assert body["total"] == 1
    assert len(body["items"]) == 1


# ══════════════════════════════════════════════════════════════
#  Ball filtri bahosiz qo'ng'iroqlarni yutmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_score_min_bahosiz_qongiroqni_yoqotmaydi(admin_client, dataset) -> None:
    """`score_min=0` — «hech narsani kesma» degani.

    Baho ixtiyoriy bog'lanish bo'lgani uchun ball filtri hali
    baholanmagan qo'ng'iroqni ro'yxatdan chiqarib yubormaydi.
    """
    data = await dataset(scores=[90, 70], unscored_calls=2)

    body = await _calls(admin_client, data, score_min=0)

    assert body["total"] == 4
    assert sum(1 for item in body["items"] if item["score"] is None) == 2


@pytest.mark.asyncio
async def test_needs_review_false_bahosizni_yoqotmaydi(admin_client, dataset) -> None:
    """Bahosiz qator ro'yxatda `needs_review: false` — filtr ham shunday
    o'qiydi, aks holda javob o'z-o'ziga zid bo'lardi."""
    data = await dataset(scores=[90, 70], unscored_calls=2)

    body = await _calls(admin_client, data, needs_review="false")

    assert body["total"] == 4


# ══════════════════════════════════════════════════════════════
#  Kirish parametrlarining chegaralari
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 201},
        {"score_min": -1},
        {"score_max": 101},
        {"sort": "yolgon_ustun"},
        {"order": "yolgon_yonalish"},
    ],
)
async def test_yaroqsiz_parametr_422_beradi(admin_client, params) -> None:
    """Saralash ustuni oq ro'yxatdan olinadi — ixtiyoriy matn o'tmaydi."""
    response = await admin_client.get(LIST, params=params)

    assert response.status_code == 422, response.text
