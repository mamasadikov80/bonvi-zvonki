"""`GET /surveys` — filtrlar HAR BIR ko'rsatkichga bir xil tushadimi?

Xavf shundaki, endpoint ichida to'rtta alohida SQL so'rov bor
(`items`, `avg + count`, `distribution`, `response_rate`) va filtr
ularning har biriga QO'LDA qo'shiladi. Bittasidan tushib qolsa,
bir ekranda «2 ta baho» yozilib, ustunlarda butun kompaniyaniki
chizilib turadi.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

FEEDBACK = "/api/v1/surveys"


def _unique_region() -> str:
    """Bazadagi haqiqiy hududlar bilan to'qnashmaydigan nom."""
    return f"pytest-{uuid.uuid4().hex[:8]}"


async def _get(client, **params):
    response = await client.get(FEEDBACK, params={"days": 90, **params})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_xodim_filtri_hamma_korsatkichga_qollanadi(
    admin_client, dataset
) -> None:
    a = await dataset(scores=[90], ratings=[5, 5], rating_days_ago=[1, 2])
    await dataset(scores=[10], ratings=[1, 1, 1], rating_days_ago=[1, 2, 3])

    body = await _get(admin_client, agent_id=str(a.agent_id))

    assert body["count"] == 2
    assert body["average"] == pytest.approx(5.0, abs=0.01)
    # Ikkinchi xodimning uchta bir yulduzi taqsimotga TUSHMASLIGI kerak
    assert body["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 2}
    assert sum(body["distribution"].values()) == body["count"]
    assert {item["agent_id"] for item in body["items"]} == {str(a.agent_id)}


@pytest.mark.asyncio
async def test_hudud_filtri_ikkinchi_hududni_kesib_tashlaydi(
    admin_client, dataset
) -> None:
    """Ikkita ALOHIDA hududda ikkita xodim — filtr birinchisini qoldiradi.

    Hudud nomlari tasodifiy: bazadagi haqiqiy «Toshkent» yozuvlari
    natijaga qo'shilib, testni yolg'on yashil qilib qo'ymasligi kerak.
    """
    region_a, region_b = _unique_region(), _unique_region()
    a = await dataset(
        scores=[90], ratings=[5, 4], rating_days_ago=[1, 2], region=region_a
    )
    await dataset(
        scores=[10], ratings=[1, 1, 1], rating_days_ago=[1, 2, 3], region=region_b
    )

    body = await _get(admin_client, region=region_a)

    # (5 + 4) / 2 = 4.5 — faqat A hududi
    assert body["count"] == 2
    assert body["average"] == pytest.approx(4.5, abs=0.01)
    assert body["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 1, "5": 1}
    assert {item["region"] for item in body["items"]} == {region_a}
    assert {item["agent_id"] for item in body["items"]} == {str(a.agent_id)}


@pytest.mark.asyncio
async def test_oraliqdan_tashqaridagi_javob_hisobga_olinmaydi(
    admin_client, dataset, survey_factory
) -> None:
    """`date_from` / `date_to` — oraliqdan chetdagi javob kesiladi.

    Vaqtlar `survey_factory` orqali soatigacha aniq qo'yiladi: kun
    chegarasi tekshirilayotganda «taxminan bir kun oldin» yetarli emas.
    """
    data = await dataset(scores=[])
    now = datetime.now(UTC)
    # Sana chegarasi bilan chalkashmaslik uchun javoblar kun o'rtasida
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)

    await survey_factory(
        agent_id=data.agent_id,
        client_id=data.client_id,
        responses=[
            {"csat": 5, "responded_at": noon - timedelta(days=2)},  # oraliqda
            {"csat": 4, "responded_at": noon - timedelta(days=5)},  # oraliqda
            {"csat": 1, "responded_at": noon - timedelta(days=10)},  # oraliqdan tashqarida
        ],
    )

    body = await _get(
        admin_client,
        agent_id=str(data.agent_id),
        date_from=(now - timedelta(days=6)).date().isoformat(),
        date_to=(now - timedelta(days=1)).date().isoformat(),
    )

    # (5 + 4) / 2 = 4.5 — 10 kun oldingi bir yulduz kirmaydi
    assert body["count"] == 2
    assert body["average"] == pytest.approx(4.5, abs=0.01)
    assert body["distribution"]["1"] == 0
    assert sum(body["distribution"].values()) == 2


@pytest.mark.asyncio
async def test_foiz_belgisi_hammani_qaytarmaydi(admin_client, dataset) -> None:
    """Bitta `%` — filtrni o'chiruvchi shablon emas, izlanadigan belgi.

    `ILIKE '%%%'` har qanday qatorga tushadi: qidiruv o'rniga filtr
    yechilib qolardi va odam «%» yozib butun kompaniyani ko'rardi.
    """
    data = await dataset(scores=[90], ratings=[5, 4], rating_days_ago=[1, 2])

    boyicha = await _get(admin_client, agent_id=str(data.agent_id))
    foiz = await _get(admin_client, agent_id=str(data.agent_id), search="%")

    assert boyicha["count"] == 2  # ma'lumot bor — nol yolg'on yashil emas
    # Bu xodimning ismida ham, hududida ham `%` belgisi yo'q
    assert foiz["count"] == 0
    assert foiz["items"] == []


@pytest.mark.asyncio
async def test_pastki_chiziq_ixtiyoriy_belgiga_aylanmaydi(
    admin_client, dataset
) -> None:
    """«Toshkent_shahri» so'ragan odam «Toshkent-shahri» ni olmasligi kerak."""
    region = f"{_unique_region()}aXb"
    data = await dataset(
        scores=[90], ratings=[5, 4], rating_days_ago=[1, 2], region=region
    )

    body = await _get(
        admin_client,
        agent_id=str(data.agent_id),
        search=region.replace("aXb", "a_b"),
    )

    # `a_b` — hech qayerda yo'q, `aXb` esa boshqa matn
    assert body["count"] == 0
