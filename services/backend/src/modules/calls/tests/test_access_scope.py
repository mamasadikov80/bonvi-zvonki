"""Qo'ng'iroqlar ro'yxati KIMGA ochiq?

Qo'ng'iroq yozuvi — eng nozik ma'lumot: unda transkript, mijoz nomi va
xodimning ishdagi xatolari bor. Shuning uchun ro'yxatning himoyasi
uchta savolga javob berishi kerak:

  · Tokensiz odam nima ko'radi?          → hech narsa (401)
  · Savdo xodimi nima ko'radi?           → faqat O'ZINIKINI
  · Ruxsati yo'q rol nima ko'radi?       → hech narsa (403)

Uchinchi savol shu modulning asosiy sababi: token borligi hali ruxsat
degani emas. Ro'yxat ham, tafsilot ham `calls:read` YOKI `calls:read:own`
ruxsatini talab qiladi — VIEWER da ikkalasi ham yo'q.
"""

import uuid

import pytest

LIST = "/api/v1/calls"
DETAIL = "/api/v1/calls/{}"


# ══════════════════════════════════════════════════════════════
#  Tokensiz
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tokensiz_royxat_401(anon_client) -> None:
    response = await anon_client.get(LIST)

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_tokensiz_tafsilot_401(anon_client) -> None:
    """404 ham emas, 401: tokensiz odam qaysi id mavjudligini bilmasin."""
    response = await anon_client.get(DETAIL.format(uuid.uuid4()))

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_yaroqsiz_token_401(anon_client) -> None:
    response = await anon_client.get(
        LIST, headers={"Authorization": "Bearer yolgon.token.qiymati"}
    )

    assert response.status_code == 401, response.text


# ══════════════════════════════════════════════════════════════
#  SALES — faqat o'zinikini
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_savdo_xodimi_faqat_ozinikini_koradi(sales_client, dataset) -> None:
    """«Jami» soni ham toraytiriladi — begona qo'ng'iroqlar sanalmaydi."""
    client, data = sales_client
    await dataset(scores=[95, 95, 95])  # boshqa xodimning qo'ng'iroqlari

    response = await client.get(LIST, params={"page_size": 200})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == data.call_count == 2
    assert {item["agent_id"] for item in body["items"]} == {str(data.agent_id)}


@pytest.mark.asyncio
async def test_savdo_xodimi_boshqa_agent_id_ni_majburlay_olmaydi(
    sales_client, dataset
) -> None:
    """URL da begona `agent_id` — filtr emas, urinish. Natija o'zgarmasin."""
    client, data = sales_client
    begona = await dataset(scores=[95, 95, 95])

    response = await client.get(
        LIST, params={"agent_id": str(begona.agent_id), "page_size": 200}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert {item["agent_id"] for item in body["items"]} == {str(data.agent_id)}
    begona_idlar = {str(call.call_id) for call in begona.calls}
    assert not begona_idlar & {item["id"] for item in body["items"]}


@pytest.mark.asyncio
async def test_savdo_xodimi_oz_qongirogini_ochadi(sales_client) -> None:
    """Nazorat testi: o'z qo'ng'irog'i normal ochilishi kerak."""
    client, data = sales_client

    response = await client.get(DETAIL.format(data.calls[0].call_id))

    assert response.status_code == 200, response.text
    assert response.json()["agent"]["id"] == str(data.agent_id)


@pytest.mark.asyncio
async def test_savdo_xodimi_ozga_qongiroq_tafsilotini_ololmaydi(
    sales_client, dataset
) -> None:
    client, _ = sales_client
    begona = await dataset(scores=[95])

    response = await client.get(DETAIL.format(begona.calls[0].call_id))

    assert response.status_code == 403, response.text


# ══════════════════════════════════════════════════════════════
#  VIEWER — ruxsati yo'q rol
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_menejer_royxatni_ochadi(manager_client, dataset) -> None:
    """Nazorat testi: `calls:read` ruxsati BOR rol uchun endpoint ishlaydi.

    Bu quyidagi testlarning ma'nosini aniqlashtiradi: VIEWER 403 olsa,
    endpoint singani uchun emas — ruxsati yetmagani uchun.
    """
    data = await dataset(scores=[90])

    response = await manager_client.get(LIST, params={"agent_id": str(data.agent_id)})

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_viewer_qongiroqlar_royxatiga_kira_olmaydi(
    viewer_client, dataset
) -> None:
    """Monitor hisobi analitikani ko'radi, xom qo'ng'iroqlarni emas."""
    data = await dataset(scores=[90, 70])

    response = await viewer_client.get(LIST, params={"agent_id": str(data.agent_id)})

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_viewer_qongiroq_transkriptini_oqiy_olmaydi(
    viewer_client, dataset, db
) -> None:
    """Tafsilot 404 emas, 403 beradi: id to'g'ri bo'lsa ham matn ochilmaydi."""
    data = await dataset(scores=[90])
    await db.call(data.calls[0].call_id, transcript="Maxfiy suhbat matni")

    response = await viewer_client.get(DETAIL.format(data.calls[0].call_id))

    assert response.status_code == 403, response.text
