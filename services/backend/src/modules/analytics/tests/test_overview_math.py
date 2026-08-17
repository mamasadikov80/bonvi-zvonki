"""`GET /analytics/overview` — KPI kartalarning matematikasi.

Har test o'ziga xos xodim yaratadi va `agent_ids` bilan AYNAN o'sha
xodimni so'raydi, shuning uchun bazadagi boshqa ma'lumot natijaga
ta'sir qilmaydi. Kutilayotgan qiymat test ichida qo'lda hisoblanadi.
"""

import pytest

API = "/api/v1/analytics/overview"


async def _overview(client, data, **params):
    response = await client.get(
        API, params={"days": 30, "agent_ids": str(data.agent_id), **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_qongiroqlar_soni_va_ortacha_ball(admin_client, dataset) -> None:
    data = await dataset(scores=[90, 70, 50])

    body = await _overview(admin_client, data)

    assert body["calls"]["value"] == 3
    # (90 + 70 + 50) / 3 = 70.0
    assert body["ai_score"]["value"] == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_bitta_qongiroq_ham_ortacha_beradi(admin_client, dataset) -> None:
    """Bitta yozuvda `AVG` ishlashi kerak — nolga bo'lish yo'q."""
    data = await dataset(scores=[83])

    body = await _overview(admin_client, data)

    assert body["calls"]["value"] == 1
    assert body["ai_score"]["value"] == pytest.approx(83.0)


@pytest.mark.asyncio
async def test_malumotsiz_xodimda_nol_va_null(admin_client, dataset) -> None:
    """Bo'sh natijada 500 emas, tartibli nol qaytishi kerak."""
    data = await dataset(scores=[])

    body = await _overview(admin_client, data)

    assert body["calls"]["value"] == 0
    assert body["ai_score"]["value"] is None
    assert body["avg_duration_sec"] == 0


@pytest.mark.asyncio
async def test_qoidabuzarlikli_qongiroqlar_sanaladi(admin_client, dataset) -> None:
    """KPI kartasi — qoidabuzarligi bor QO'NG'IROQLAR soni.

    ⚠️ `/analytics/red-flags` razrezi esa HAR BIR belgini alohida
    sanaydi. Ikkalasi ataylab boshqa narsani o'lchaydi; shuning uchun
    bu yerda ikkalasining ma'nosi alohida qotirilgan
    (`test_red_flags_kpi_va_razrez_farqi` ga qarang).
    """
    data = await dataset(scores=[90, 70, 50], red_flags=[2, 1, 0])

    body = await _overview(admin_client, data)

    # 3 ta qoidabuzarlik, lekin 2 ta qo'ng'iroqda
    assert data.total_red_flags == 3
    assert data.calls_with_red_flags == 2
    assert body["red_flags"]["value"] == 2


@pytest.mark.asyncio
async def test_client_bahosi_ortachasi(admin_client, dataset) -> None:
    data = await dataset(scores=[80], ratings=[5, 4, 3])

    body = await _overview(admin_client, data)

    # (5 + 4 + 3) / 3 = 4.0
    assert body["client_rating"]["count"] == 3
    assert body["client_rating"]["value"] == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_davr_tashqarisidagi_qongiroq_hisobga_olinmaydi(
    admin_client, dataset
) -> None:
    """Sana filtri ishlashining eng oddiy isboti."""
    data = await dataset(scores=[90, 70], days_ago=[1, 40])

    body = await _overview(admin_client, data, days=30)

    assert body["calls"]["value"] == 1
    assert body["ai_score"]["value"] == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_ortacha_davomiylik_yaxlitlanadi(admin_client, dataset) -> None:
    data = await dataset(scores=[80, 80, 80], durations=[10, 11, 11])

    body = await _overview(admin_client, data)

    # (10 + 11 + 11) / 3 = 10.666… → 11
    assert data.avg_duration == pytest.approx(10.667, abs=0.01)
    assert body["avg_duration_sec"] == 11


@pytest.mark.asyncio
async def test_oldingi_davr_ham_bir_xil_filtrlanadi(admin_client, dataset) -> None:
    """Joriy davrda 95+ ballik 2 ta qo'ng'iroq, oldingisida bittasi ham yo'q.

    To'g'ri javob — `delta_percent: null` («solishtirish uchun asos yo'q»),
    chunki oldingi davrda `score_min=95` shartiga mos qo'ng'iroq yo'q.
    """
    data = await dataset(
        scores=[98, 97, 50, 51],
        days_ago=[1, 2, 6, 7],  # 6–7 kun oldingisi «oldingi davr» ga tushadi
    )

    body = await _overview(admin_client, data, days=5, score_min=95)

    assert body["calls"]["value"] == 2
    assert body["calls"]["delta_percent"] is None
    assert body["ai_score"]["delta_percent"] is None
