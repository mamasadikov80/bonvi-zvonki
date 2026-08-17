"""`GET /surveys` — yig'ma ko'rsatkichlar matematikasi.

Har test o'ziga xos xodim yaratadi va AYNAN o'sha xodim bo'yicha
filtrlab so'raydi, shuning uchun bazadagi boshqa baholar natijaga
qo'shilmaydi. Kutilayotgan raqam test ichida qo'lda hisoblangan.

NEGA BU YERDA IKKITA AGREGAT ALOHIDA TEKSHIRILADI
  `average`, `count` va `distribution` uchta ALOHIDA SQL so'rovidan
  keladi (`router.py:251-269`). Ular bir xil filtrdan o'tadi degan
  narsa kafolat emas, tekshiriladigan da'vo — shuning uchun har testda
  «taqsimot yig'indisi = count» sharti ham qo'shib boriladi.
"""

from datetime import UTC, datetime, timedelta

import pytest

FEEDBACK = "/api/v1/surveys"


async def _feedback(client, agent_id, **params):
    response = await client.get(
        FEEDBACK, params={"days": 90, "agent_id": str(agent_id), **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_ortacha_csat_togri_hisoblanadi(admin_client, dataset) -> None:
    data = await dataset(scores=[90], ratings=[5, 4, 3], rating_days_ago=[1, 2, 3])

    body = await _feedback(admin_client, data.agent_id)

    # (5 + 4 + 3) / 3 = 4.0
    assert data.avg_rating == pytest.approx(4.0)
    assert body["count"] == 3
    assert body["average"] == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_taqsimot_yigindisi_count_ga_teng(admin_client, dataset) -> None:
    """Har yulduz alohida sanaladi va yig'indisi umumiy songa tushadi.

    Bu ikkalasi turli so'rovdan kelgani uchun bir-biridan «uzilib»
    qolishi mumkin: ekranda «5 ta baho» yozilib, ustunlarda 4 tasi
    chizilgan holat aynan shunday tug'iladi.
    """
    data = await dataset(
        scores=[90],
        ratings=[5, 5, 4, 3, 1],
        rating_days_ago=[1, 2, 3, 4, 5],
    )

    body = await _feedback(admin_client, data.agent_id)

    assert body["count"] == 5
    assert body["distribution"] == {"1": 1, "2": 0, "3": 1, "4": 1, "5": 2}
    assert sum(body["distribution"].values()) == body["count"]


@pytest.mark.asyncio
async def test_bitta_sorovnomaning_uchta_javobi_dublikat_bermaydi(
    admin_client, dataset, survey_factory
) -> None:
    """Guruh oqimi: BITTA so'rovnoma, unga uchta odam javob bergan.

    So'rov `survey_responses → surveys → agents` bo'ylab JOIN qiladi va
    ustiga `telegram_groups` ni LEFT JOIN qo'shadi. Agar bog'lanishlardan
    biri bir javobni ikki qatorga ko'paytirsa, `count` ham, `average` ham
    jimgina siljiydi — hech qanday xato chiqmaydi, shunchaki raqam yolg'on
    bo'ladi.
    """
    data = await dataset(scores=[])  # baholari yo'q xodim — hammasini o'zimiz yozamiz
    now = datetime.now(UTC)

    await survey_factory(
        agent_id=data.agent_id,
        client_id=data.client_id,
        responses=[
            {"csat": 5, "responded_at": now - timedelta(days=3)},
            {"csat": 4, "responded_at": now - timedelta(days=2)},
            {"csat": 3, "responded_at": now - timedelta(days=1)},
        ],
    )

    body = await _feedback(admin_client, data.agent_id)

    # Uchta javob — uchta qator, so'rovnoma bittaligi hech narsani buzmaydi
    assert body["count"] == 3
    assert body["average"] == pytest.approx(4.0, abs=0.01)
    assert sum(body["distribution"].values()) == 3


@pytest.mark.asyncio
async def test_javobsiz_xodimda_null_va_nol(admin_client, dataset) -> None:
    """Bo'sh natijada 500 emas, tartibli nol qaytishi kerak.

    `AVG` bo'sh to'plamda NULL beradi, `count / sent` esa nolga bo'linish —
    ikkalasi ham javobsiz xodimda har kuni yuz beradigan oddiy holat.
    """
    data = await dataset(scores=[])

    body = await _feedback(admin_client, data.agent_id)

    assert body["average"] is None
    assert body["count"] == 0
    assert body["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    assert body["ready"] is False
    assert body["response_rate"] is None
    assert body["items"] == []


@pytest.mark.asyncio
async def test_limit_faqat_itemsga_tasir_qiladi(admin_client, dataset) -> None:
    """`limit` — ro'yxatning uzunligi, statistikaning emas.

    Agar u agregatlarga ham tushib qolsa, sahifani varaqlagan odam
    o'rtacha bahoning har safar o'zgarayotganini ko'radi.
    """
    data = await dataset(
        scores=[90],
        ratings=[5, 4, 3, 2],
        rating_days_ago=[1, 2, 3, 4],
    )

    body = await _feedback(admin_client, data.agent_id, limit=2)

    assert len(body["items"]) == 2
    # (5 + 4 + 3 + 2) / 4 = 3.5 — limitdan qat'i nazar
    assert body["count"] == 4
    assert body["average"] == pytest.approx(3.5, abs=0.01)
    assert sum(body["distribution"].values()) == 4
