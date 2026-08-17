"""`GET /calls/{id}` — bitta qo'ng'iroq kartochkasi.

Bu ekran menejerning ish quroli: u yerda transkript, umumiy ball,
rubrika bloklari va qoidabuzarliklar bo'ladi. Testlar shu tarkibning
har bir qismi haqiqatan javobga tushayotganini tekshiradi — chunki
javob qo'lda yig'iladi (router.py:388-427) va yangi maydon qo'shilganda
uni bu yerga ULASH oson unutiladi.
"""

import uuid

import pytest

LIST = "/api/v1/calls"
DETAIL = "/api/v1/calls/{}"


@pytest.mark.asyncio
async def test_mavjud_bolmagan_id_404(admin_client) -> None:
    response = await admin_client.get(DETAIL.format(uuid.uuid4()))

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_yaroqsiz_uuid_422(admin_client) -> None:
    response = await admin_client.get(DETAIL.format("bu-uuid-emas"))

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_tafsilotda_transkript_ball_va_bloklar_bor(
    admin_client, dataset, db
) -> None:
    data = await dataset(scores=[87], durations=[420], red_flags=[1])
    call = data.calls[0]
    await db.call(call.call_id, transcript="Assalomu alaykum, buyurtma haqida")

    response = await admin_client.get(DETAIL.format(call.call_id))

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["id"] == str(call.call_id)
    assert body["duration_sec"] == 420
    assert body["direction"] == "outbound"
    assert body["status"] == "completed"
    assert body["transcript"] == "Assalomu alaykum, buyurtma haqida"

    assert body["agent"]["id"] == str(data.agent_id)
    assert body["agent"]["full_name"] == data.agent_name
    assert body["client"]["id"] == str(data.client_id)

    ball = body["score"]
    assert ball["overall_score"] == 87
    assert ball["blocks"] == {"script": 25, "communication": 25}
    assert len(ball["red_flags"]) == 1
    assert ball["model"] == "test-model"
    assert ball["rubric_version"] == "v1"
    assert ball["needs_review"] is False


@pytest.mark.asyncio
async def test_bahosiz_qongiroqda_score_null(admin_client, dataset) -> None:
    """Baho hali yo'q — 500 emas, `score: null` qaytishi kerak."""
    data = await dataset(scores=[], unscored_calls=1)

    royxat = await admin_client.get(LIST, params={"agent_id": str(data.agent_id)})
    assert royxat.status_code == 200, royxat.text
    (item,) = royxat.json()["items"]

    response = await admin_client.get(DETAIL.format(item["id"]))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"] is None
    assert body["transcript"] is None


@pytest.mark.asyncio
async def test_mijozsiz_qongiroqda_client_null(admin_client, dataset, db) -> None:
    """Client `SET NULL` bo'lgan qo'ng'iroq ham ochilishi kerak."""
    data = await dataset(scores=[90])
    await db.call(data.calls[0].call_id, client_id=None)

    response = await admin_client.get(DETAIL.format(data.calls[0].call_id))

    assert response.status_code == 200, response.text
    assert response.json()["client"] is None


@pytest.mark.asyncio
async def test_review_reasons_javobda_qaytariladi(admin_client, dataset, db) -> None:
    """Bayroq bilan birga uning SABABI ham keladi — menejer nega bu
    qo'ng'iroq navbatda ekanini javobning o'zidan biladi."""
    sabablar = [{"code": "low_confidence", "message": "AI ishonchi past (0.52 < 0.70)"}]
    data = await dataset(scores=[55])
    await db.score(data.calls[0].call_id, needs_review=True, review_reasons=sabablar)

    response = await admin_client.get(DETAIL.format(data.calls[0].call_id))

    assert response.status_code == 200, response.text
    ball = response.json()["score"]
    assert ball["needs_review"] is True
    assert ball["review_reasons"] == sabablar
