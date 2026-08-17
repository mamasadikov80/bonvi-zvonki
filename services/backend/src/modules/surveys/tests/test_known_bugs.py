"""Audit topgan xatolar — TUZATILGAN, endi qaytalanmasligini qo'riqlaydi.

  Har biri ilgari `xfail(strict=True)` bilan qotirilgan xato hisoboti
  edi: qanday ma'lumotda, qaysi qatorda va to'g'ri javob nima bo'lishi
  kerakligi. Xatolar tuzatilgach marker'lar olib tashlandi va testlar
  oddiy regressiya testiga aylandi.

  Tuzatilgan xatolar (`surveys/presentation/router.py`):
    1. `response_rate` javob oynasidan emas, faqat `sent_at` dan
       hisoblanardi — javobsiz kunda 100% chiqardi.
    2. `_period()` sanani UTC kuniga kesib, oraliqni bir kunga
       kengaytirardi — `/surveys` va `/analytics/overview` bitta
       parametrda ikki xil son berardi.
    3. `agent_id` NULL bo'lgan SALES hisobi (`if agent_id:` falsy
       tekshiruvi tufayli) butun kompaniya statistikasini ko'rardi.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.users.domain.entities import Role

FEEDBACK = "/api/v1/surveys"
OVERVIEW = "/api/v1/analytics/overview"


@pytest.mark.asyncio
async def test_javobsiz_kunda_javob_darajasi_ham_bosh_boladi(
    admin_client, dataset, survey_factory
) -> None:
    """So'rovnoma X kuni yuborilgan, javob X+1 kuni kelgan.

    X kunini so'raganda javob oynadan tashqarida qoladi (`count == 0`),
    demak o'sha kun uchun javob berish darajasini hisoblashga ASOS YO'Q:
    to'g'ri javob — `None` (yoki hech bo'lmasa `0`), 100% emas.
    """
    data = await dataset(scores=[])
    kun_x = (datetime.now(UTC) - timedelta(days=3)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )

    await survey_factory(
        agent_id=data.agent_id,
        client_id=data.client_id,
        sent_at=kun_x,
        responses=[{"csat": 5, "responded_at": kun_x + timedelta(days=1)}],
    )

    response = await admin_client.get(
        FEEDBACK,
        params={
            "agent_id": str(data.agent_id),
            "date_from": kun_x.date().isoformat(),
            "date_to": kun_x.date().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["count"] == 0  # javob X+1 kuni kelgan — oynaga tushmaydi
    assert body["response_rate"] in (None, 0)


@pytest.mark.asyncio
async def test_surveys_va_overview_bir_xil_parametrda_bir_xil_son_beradi(
    admin_client, dataset, survey_factory
) -> None:
    """Javob X kuni soat 10:00 da kelgan, so'rov esa X kuni 19:00 dan.

    To'g'ri javob — javob oraliqdan TASHQARIDA (10:00 < 19:00), ya'ni
    ikkala endpoint ham 0 berishi kerak. Hozir `/surveys` uni ichkariga
    qo'shib yuboradi.
    """
    data = await dataset(scores=[])
    kun_x = (datetime.now(UTC) - timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    date_from = kun_x.replace(hour=19).isoformat()

    await survey_factory(
        agent_id=data.agent_id,
        client_id=data.client_id,
        responses=[{"csat": 5, "responded_at": kun_x}],
    )

    surveys = await admin_client.get(
        FEEDBACK, params={"agent_id": str(data.agent_id), "date_from": date_from}
    )
    overview = await admin_client.get(
        OVERVIEW, params={"agent_ids": str(data.agent_id), "date_from": date_from}
    )
    assert surveys.status_code == 200, surveys.text
    assert overview.status_code == 200, overview.text

    assert surveys.json()["count"] == overview.json()["client_rating"]["count"]


@pytest.mark.asyncio
async def test_xodimsiz_savdo_hisobi_kompaniya_statistikasini_ochmaydi(
    dataset, login_as
) -> None:
    """`agent_id` yo'q SALES hisobi hech kimning bahosini ko'rmasligi kerak.

    Bo'sh doira — hech narsa emas. «Filtr yo'q, demak hammasi» degan
    tushunish ayni shu joyda maxfiylik teshigiga aylanadi.
    """
    await dataset(scores=[90], ratings=[5, 4, 3], rating_days_ago=[1, 2, 3])
    client = await login_as(role=Role.SALES, agent_id=None)

    response = await client.get(FEEDBACK, params={"days": 90})

    if response.status_code == 403:
        return  # To'g'ri xatti-harakat — bu holatda test XPASS bo'ladi

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0
