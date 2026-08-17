"""`GET /pipeline/status` — admin quvurni shu endpoint orqali ko'radi.

NEGA MUHIM: worker o'chiq bo'lsa ham endpoint ISHLASHI kerak —
`workers: []` va navbat uzunligi aynan admin bilishi kerak bo'lgan
holat. Agar Celery yoki Redis javob bermaganda 500 qaytsa, admin
«tizim qanday ahvolda?» degan savolga umuman javob ololmaydi.

Himoya ham tekshiriladi: quvur PUL SARFLAYDI, shuning uchun tokensiz
kirish 401 bo'lishi shart.
"""

import pytest

API = "/api/v1/pipeline"


@pytest.mark.asyncio
async def test_admin_holatni_ola_oladi(admin_client) -> None:
    response = await admin_client.get(f"{API}/status")

    assert response.status_code == 200, response.text
    body = response.json()

    # Navbat va workerlar
    assert "queue_depth" in body  # Redis yo'q bo'lsa `None` — lekin kalit bor
    assert isinstance(body["workers"], list)
    assert body["worker_count"] == len(body["workers"])

    # Baza razrezi (`db_snapshot`)
    assert set(body["stages"]) == {
        "queued",
        "transcribing",
        "scoring",
        "completed",
        "failed",
        "skipped",
    }
    assert body["scored_last_15min"] <= body["scored_last_hour"]
    assert body["per_minute_15min"] == round(body["scored_last_15min"] / 15.0, 2)

    # Chegaralar — DevOps shu yerdan amaldagi sozlamani ko'radi
    assert body["limits"]["concurrency"] >= 1
    assert body["limits"]["min_duration_sec"] >= 0

    assert body["checked_at"], "Ma'lumot qachonligi ko'rinishi kerak"


@pytest.mark.asyncio
async def test_tokensiz_401(anon_client) -> None:
    response = await anon_client.get(f"{API}/status")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_nosozliklar_royxati_ham_himoyalangan(anon_client) -> None:
    response = await anon_client.get(f"{API}/failures")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_navbatga_qoyish_tokensiz_401(anon_client) -> None:
    """`POST /pipeline/run` — eng qimmat tugma, ochiq qolmasin."""
    response = await anon_client.post(
        f"{API}/run",
        json={"date_from": "2026-01-01T00:00:00Z", "date_to": "2026-01-02T00:00:00Z"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_nosozliklar_royxati_admin_uchun_ochiladi(admin_client) -> None:
    response = await admin_client.get(f"{API}/failures", params={"limit": 5})

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) <= 5


@pytest.mark.asyncio
async def test_teskari_sana_oraligi_rad_etiladi(admin_client) -> None:
    """`date_to < date_from` — bu so'rov hech qachon navbat yaratmasin."""
    response = await admin_client.post(
        f"{API}/run",
        json={
            "date_from": "2026-02-01T00:00:00Z",
            "date_to": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 422
    assert "sana" in response.text.lower()


@pytest.mark.asyncio
async def test_yoq_qongiroqni_qayta_yuborish_404(admin_client) -> None:
    from uuid import uuid4

    response = await admin_client.post(f"{API}/calls/{uuid4()}/retry")

    assert response.status_code == 404
