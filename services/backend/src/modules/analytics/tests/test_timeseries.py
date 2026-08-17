"""`GET /analytics/timeseries` — trend grafigi ma'lumoti.

Bu yerdagi asosiy qoida: javob TANLANGAN DAVRNI to'liq qamrashi
kerak. Faqat qo'ng'iroq bo'lgan kunlarni qaytarish grafikni
yolg'onchi qiladi — o'q toifaviy bo'lgani uchun 5 ta kun 7 kunlik
davrda ham, 90 kunlikda ham bir xil chiziladi va davr filtri
«ishlamayotgandek» ko'rinadi.
"""

import pytest

API = "/api/v1/analytics/timeseries"


async def _points(client, data, **params):
    response = await client.get(
        API,
        params={
            "days": 30,
            "bucket": "day",
            "agent_ids": str(data.agent_id),
            **params,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_davr_toliq_qamraladi(admin_client, dataset) -> None:
    """7 kunlik davr — 8 ta nuqta (ikkala chegara ham kiradi)."""
    data = await dataset(scores=[90], days_ago=[1])

    points = await _points(admin_client, data, days=7)

    assert len(points) == 8
    assert sum(p["calls"] for p in points) == 1


@pytest.mark.asyncio
async def test_davr_uzayganda_nuqtalar_ham_koapayadi(admin_client, dataset) -> None:
    """Davr filtri grafikka SEZILARLI ta'sir qilishi kerak.

    Ilgari ikkala so'rov ham bir xil natija berardi va admin
    «filtr ishlamayapti» degan xulosaga kelardi.
    """
    data = await dataset(scores=[90], days_ago=[1])

    hafta = await _points(admin_client, data, days=7)
    oy = await _points(admin_client, data, days=30)

    assert len(hafta) == 8
    assert len(oy) == 31
    # Ma'lumot o'zgarmadi — faqat oyna kengaydi
    assert sum(p["calls"] for p in hafta) == sum(p["calls"] for p in oy) == 1


@pytest.mark.asyncio
async def test_qongiroqsiz_kun_nol_bilan_toldiriladi(admin_client, dataset) -> None:
    """Bo'sh kunda `calls: 0` va `ai_score: null` — qator TUSHIB QOLMAYDI."""
    data = await dataset(scores=[90, 70], days_ago=[1, 5])

    points = await _points(admin_client, data, days=7)

    bosh = [p for p in points if p["calls"] == 0]
    tola = [p for p in points if p["calls"] > 0]

    assert len(tola) == 2
    assert len(bosh) == len(points) - 2
    assert all(p["ai_score"] is None for p in bosh)


@pytest.mark.asyncio
async def test_bir_kundagi_qongiroqlar_ortachalanadi(admin_client, dataset) -> None:
    """Bir kunning ichida bir nechta qo'ng'iroq — bitta nuqta, o'rtacha ball."""
    data = await dataset(scores=[100, 80, 60], days_ago=[2, 2, 2])

    points = await _points(admin_client, data, days=7)
    tola = [p for p in points if p["calls"] > 0]

    assert len(tola) == 1
    assert tola[0]["calls"] == 3
    # (100 + 80 + 60) / 3 = 80.0
    assert tola[0]["ai_score"] == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_nuqtalar_sana_boyicha_tartiblangan(admin_client, dataset) -> None:
    data = await dataset(scores=[90, 70, 50], days_ago=[1, 3, 5])

    points = await _points(admin_client, data, days=10)
    sanalar = [p["date"] for p in points]

    assert sanalar == sorted(sanalar)


@pytest.mark.asyncio
async def test_hafta_razreziga_yigiladi(admin_client, dataset) -> None:
    """`bucket=week` — kunlar haftalarga yig'iladi, nuqtalar kamayadi."""
    data = await dataset(scores=[90, 70], days_ago=[1, 20])

    kunlik = await _points(admin_client, data, days=30, bucket="day")
    haftalik = await _points(admin_client, data, days=30, bucket="week")

    assert len(haftalik) < len(kunlik)
    assert sum(p["calls"] for p in haftalik) == sum(p["calls"] for p in kunlik) == 2


@pytest.mark.asyncio
async def test_malumotsiz_xodimda_ham_davr_chiziladi(admin_client, dataset) -> None:
    """Qo'ng'irog'i yo'q xodim — bo'sh ro'yxat emas, nolli davr.

    Aks holda grafik «ma'lumot yo'q» o'rniga umuman chizilmasdi.
    """
    data = await dataset(scores=[])

    points = await _points(admin_client, data, days=7)

    assert len(points) == 8
    assert all(p["calls"] == 0 for p in points)
    assert all(p["ai_score"] is None for p in points)
