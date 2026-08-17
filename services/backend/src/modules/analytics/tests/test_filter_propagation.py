"""Filtr HAR BIR ko'rsatkichga bir xil tushadimi?

Bu testlarning mavjudlik sababi bitta hodisa: admin hudud filtrini
qo'yadi, AI bahosi toraydi, client bahosi esa butun kompaniyaniki
bo'lib qolaveradi. Bir ekranda ikkita zid raqam — foydalanuvchi
qaysi biriga ishonishni bilmaydi.

Har test ikkita ALOHIDA hududda ikkita xodim yaratadi va filtr
haqiqatan ikkinchisini kesib tashlayotganini tekshiradi.
"""

import uuid

import pytest

OVERVIEW = "/api/v1/analytics/overview"
TIMESERIES = "/api/v1/analytics/timeseries"
LEADERBOARD = "/api/v1/analytics/agents"


def _unique_region() -> str:
    """Bazadagi haqiqiy hududlar bilan to'qnashmaydigan nom."""
    return f"pytest-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_hudud_filtri_qongiroqlarga_qollanadi(admin_client, dataset) -> None:
    """Nazorat testi: hudud filtri AI tomonida ishlaydi."""
    region_a, region_b = _unique_region(), _unique_region()
    a = await dataset(scores=[90, 90], region=region_a)
    await dataset(scores=[10, 10], region=region_b)

    response = await admin_client.get(
        OVERVIEW, params={"days": 30, "regions": region_a}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["calls"]["value"] == 2
    assert body["ai_score"]["value"] == pytest.approx(90.0)
    assert a.avg_score == 90.0


@pytest.mark.asyncio
async def test_hudud_filtri_client_bahosiga_ham_qollanadi(
    admin_client, dataset
) -> None:
    region_a, region_b = _unique_region(), _unique_region()
    await dataset(scores=[90], ratings=[5, 5], region=region_a)
    await dataset(scores=[10], ratings=[1, 1], region=region_b)

    response = await admin_client.get(
        OVERVIEW, params={"days": 30, "regions": region_a}
    )
    body = response.json()

    # Faqat A hududining 2 ta bahosi (5, 5) → 5.0
    assert body["client_rating"]["count"] == 2
    assert body["client_rating"]["value"] == pytest.approx(5.0, abs=0.01)


@pytest.mark.asyncio
async def test_hudud_filtri_grafik_client_chizigiga_qollanadi(
    admin_client, dataset
) -> None:
    region_a, region_b = _unique_region(), _unique_region()
    await dataset(scores=[90], ratings=[5], rating_days_ago=[1], region=region_a)
    await dataset(scores=[10], ratings=[1], rating_days_ago=[2], region=region_b)

    response = await admin_client.get(
        TIMESERIES, params={"days": 30, "bucket": "day", "regions": region_a}
    )
    points = response.json()

    ratings = [p["client_rating"] for p in points if p["client_rating"] is not None]
    # Faqat A hududining bahosi ko'rinishi kerak
    assert ratings == [pytest.approx(5.0)]


@pytest.mark.asyncio
async def test_xodim_filtri_barcha_korsatkichlarga_qollanadi(
    admin_client, dataset
) -> None:
    """`agent_ids` — eng ko'p ishlatiladigan filtr, hamma joyda ishlashi shart."""
    a = await dataset(scores=[100, 80], ratings=[5])
    await dataset(scores=[20, 20], ratings=[1])

    response = await admin_client.get(
        OVERVIEW, params={"days": 30, "agent_ids": str(a.agent_id)}
    )
    body = response.json()

    assert body["calls"]["value"] == 2
    assert body["ai_score"]["value"] == pytest.approx(90.0)
    assert body["client_rating"]["count"] == 1
    assert body["client_rating"]["value"] == pytest.approx(5.0, abs=0.01)


@pytest.mark.asyncio
async def test_ball_oraligi_filtri(admin_client, dataset) -> None:
    data = await dataset(scores=[95, 60, 30])

    response = await admin_client.get(
        OVERVIEW,
        params={"days": 30, "agent_ids": str(data.agent_id), "score_min": 60},
    )
    body = response.json()

    # 95 va 60 qoladi → (95 + 60) / 2 = 77.5
    assert body["calls"]["value"] == 2
    assert body["ai_score"]["value"] == pytest.approx(77.5)


@pytest.mark.asyncio
async def test_qoidabuzarlik_filtri(admin_client, dataset) -> None:
    data = await dataset(scores=[90, 80, 70], red_flags=[1, 0, 0])

    response = await admin_client.get(
        OVERVIEW,
        params={
            "days": 30,
            "agent_ids": str(data.agent_id),
            "has_red_flags": "true",
        },
    )
    body = response.json()

    assert body["calls"]["value"] == 1
    assert body["ai_score"]["value"] == pytest.approx(90.0)


# ══════════════════════════════════════════════════════════════
#  Ko'rsatkichlar izchilligi — bitta raqam, bitta qiymat
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_leaderboard_ai_bahosi_overview_bilan_mos(
    admin_client, dataset
) -> None:
    """Bitta xodim, bitta davr — ikki endpoint bir xil raqam berishi shart."""
    data = await dataset(scores=[91, 77, 63])

    params = {"days": 30, "agent_ids": str(data.agent_id)}
    overview = (await admin_client.get(OVERVIEW, params=params)).json()
    rows = (await admin_client.get(LEADERBOARD, params=params)).json()

    row = next(r for r in rows if r["agent_id"] == str(data.agent_id))
    assert row["calls"] == overview["calls"]["value"]
    assert row["ai_score"] == pytest.approx(overview["ai_score"]["value"])
    assert row["ai_score"] == pytest.approx(77.0)


@pytest.mark.asyncio
async def test_grafikdagi_qongiroqlar_yigindisi_kpi_ga_teng(
    admin_client, dataset
) -> None:
    """Kunlik nuqtalar yig'indisi KPI kartasidagi songa teng bo'lishi kerak."""
    data = await dataset(scores=[90, 80, 70, 60], days_ago=[1, 2, 2, 5])

    params = {"days": 30, "agent_ids": str(data.agent_id)}
    overview = (await admin_client.get(OVERVIEW, params=params)).json()
    points = (
        await admin_client.get(TIMESERIES, params={**params, "bucket": "day"})
    ).json()

    assert sum(p["calls"] for p in points) == overview["calls"]["value"] == 4
