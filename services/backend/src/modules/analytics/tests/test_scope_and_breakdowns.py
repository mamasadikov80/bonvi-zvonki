"""Rol doirasi va razrezlar.

ROL DOIRASI eng muhim tekshiruv: savdo xodimi hech qanday yo'l bilan
boshqa xodimning raqamini ko'rmasligi kerak. Buni URL parametrini
majburlab ham sinab ko'ramiz — chunki chegara frontendda emas,
serverda turishi shart.
"""

import pytest

OVERVIEW = "/api/v1/analytics/overview"
LEADERBOARD = "/api/v1/analytics/agents"
BLOCKS = "/api/v1/analytics/blocks"
RED_FLAGS = "/api/v1/analytics/red-flags"
DISTRIBUTION = "/api/v1/analytics/distribution"
FILTERS = "/api/v1/analytics/filters"


# ══════════════════════════════════════════════════════════════
#  Rol doirasi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_savdo_xodimi_faqat_ozini_koradi(sales_client) -> None:
    client, data = sales_client

    body = (await client.get(OVERVIEW, params={"days": 30})).json()

    # Fixture 2 ta qo'ng'iroq beradi: 80 va 60 → o'rtacha 70
    assert body["calls"]["value"] == data.call_count == 2
    assert body["ai_score"]["value"] == pytest.approx(data.avg_score)


@pytest.mark.asyncio
async def test_savdo_xodimi_ozga_xodimni_majburlay_olmaydi(
    sales_client, dataset
) -> None:
    """URL da boshqa `agent_ids` berish natijani O'ZGARTIRMASLIGI kerak."""
    client, data = sales_client
    ozga = await dataset(scores=[10, 10, 10])

    ozini = (await client.get(OVERVIEW, params={"days": 30})).json()
    majburlab = (
        await client.get(
            OVERVIEW, params={"days": 30, "agent_ids": str(ozga.agent_id)}
        )
    ).json()

    assert majburlab["calls"]["value"] == ozini["calls"]["value"]
    assert majburlab["ai_score"]["value"] == pytest.approx(ozini["ai_score"]["value"])
    # O'zga xodimning bali (10) hech qayerda ko'rinmaydi
    assert majburlab["ai_score"]["value"] != pytest.approx(10.0)


@pytest.mark.asyncio
async def test_savdo_xodimi_reytingda_faqat_ozini_koradi(sales_client) -> None:
    client, data = sales_client

    rows = (await client.get(LEADERBOARD, params={"days": 30})).json()

    assert {r["agent_id"] for r in rows} == {str(data.agent_id)}


@pytest.mark.asyncio
async def test_savdo_xodimi_filtr_royxatida_faqat_ozi(sales_client) -> None:
    """Filtr ro'yxati ham torayishi kerak — aks holda boshqa
    xodimlarning ISMLARI oshkor bo'ladi."""
    client, data = sales_client

    body = (await client.get(FILTERS)).json()

    assert [a["id"] for a in body["agents"]] == [str(data.agent_id)]


@pytest.mark.asyncio
async def test_tokensiz_kirish_rad_etiladi(anon_client) -> None:
    for url in (OVERVIEW, LEADERBOARD, BLOCKS, RED_FLAGS, DISTRIBUTION, FILTERS):
        response = await anon_client.get(url, params={"days": 30})
        assert response.status_code == 401, f"{url} → {response.status_code}"


# ══════════════════════════════════════════════════════════════
#  Razrezlar
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ball_taqsimoti_yigindisi_qongiroqlar_soniga_teng(
    admin_client, dataset
) -> None:
    """Histogramma ustunlari yig'indisi jami qo'ng'iroqqa teng — bitta
    qo'ng'iroq ikkita ustunga tushib qolmasligi kerak."""
    data = await dataset(scores=[95, 88, 72, 61, 40])

    params = {"days": 30, "agent_ids": str(data.agent_id)}
    rows = (await admin_client.get(DISTRIBUTION, params=params)).json()
    overview = (await admin_client.get(OVERVIEW, params=params)).json()

    assert sum(r["count"] for r in rows) == overview["calls"]["value"] == 5


@pytest.mark.asyncio
async def test_qoidabuzarlik_razrezi_har_belgini_alohida_sanaydi(
    admin_client, dataset
) -> None:
    """Razrez — HODISALAR soni, KPI kartasi esa QO'NG'IROQLAR soni.

    ⚠️ Ikkalasi ataylab boshqa narsani o'lchaydi va bir-biriga teng
    EMAS. Bu test o'sha farqni qotiradi: kimdir bittasini o'zgartirsa,
    ikkinchisi bilan farqi ko'rinib qolsin.
    """
    data = await dataset(scores=[90, 80], red_flags=[2, 1])

    params = {"days": 30, "agent_ids": str(data.agent_id)}
    razrez = (await admin_client.get(RED_FLAGS, params=params)).json()
    overview = (await admin_client.get(OVERVIEW, params=params)).json()

    assert sum(r["count"] for r in razrez) == data.total_red_flags == 3
    assert overview["red_flags"]["value"] == data.calls_with_red_flags == 2


@pytest.mark.asyncio
async def test_bloklar_razrezi_foizni_100_dan_oshirmaydi(
    admin_client, dataset
) -> None:
    """Blok foizi 0–100 oralig'ida bo'lishi kerak.

    ⚠️ Auditda tasdiqlangan: `scoring/domain/entities.py` dagi qotirilgan
    `BLOCK_MAX` faol rubrikaga zid (`sales_skill`: kodda 15, rubrikada 25),
    shuning uchun haqiqiy ma'lumotda 105.8% chiqishi mumkin. Bu test
    fixture ma'lumotida ishlaydi va regressiyani ushlaydi.
    """
    data = await dataset(scores=[90])

    rows = (
        await admin_client.get(
            BLOCKS, params={"days": 30, "agent_ids": str(data.agent_id)}
        )
    ).json()

    for row in rows:
        assert 0 <= row["percent"] <= 100, row
        assert row["score"] <= row["max"], row


# ══════════════════════════════════════════════════════════════
#  Tur bo'yicha razrez
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_turlar_razrezi_rol_doirasiga_boysunadi(sales_client, dataset) -> None:
    """⚠️ XAVFSIZLIK: yangi razrez rol chegarasini buzmasligi kerak.

    Bu so'rov `_apply` dan foydalanmaydi (u bahoga tayanadigan shartlar
    qo'shadi va savdo bo'lmagan qo'ng'iroqlarni yo'q qilardi), ya'ni
    filtrlar QO'LDA ko'chirilgan. Aynan shunday joyda rol chegarasini
    ko'chirishni unutish oson — o'shanda savdo xodimi butun kompaniya
    ma'lumotini ko'rib qolardi."""
    client, data = sales_client
    await dataset(scores=[10, 10, 10])  # o'zga xodimning qo'ng'iroqlari

    body = (await client.get(OVERVIEW, params={"days": 30})).json()
    assert sum(body["call_types"].values()) == data.call_count
    assert body["calls_total"] == data.call_count


@pytest.mark.asyncio
async def test_turlar_razrezi_hamma_kalitni_qaytaradi(admin_client) -> None:
    """Kalitlar HAR DOIM to'la — nol bo'lsa ham.

    UI ro'yxatni o'zi to'ldirsa backend bilan ajralib ketardi: yangi tur
    qo'shilganda u razrezda ko'rinmay qolardi va sonlar jamiga
    yetmasdi."""
    body = (await admin_client.get(OVERVIEW, params={"days": 365})).json()
    assert set(body["call_types"]) == {"sales", "internal", "unknown"}
    assert body["calls_total"] == sum(body["call_types"].values())


@pytest.mark.asyncio
async def test_baholangan_soni_jamidan_oshmaydi(admin_client) -> None:
    """`calls` — baholanganlar, `calls_total` — hammasi."""
    body = (await admin_client.get(OVERVIEW, params={"days": 365})).json()
    # Baholangan qo'ng'iroq har doim savdo turida bo'ladi, ya'ni
    # baholanganlar soni savdo qo'ng'iroqlaridan OSHIB KETOLMAYDI
    assert body["calls"]["value"] <= body["call_types"]["sales"]
    assert body["calls"]["value"] <= body["calls_total"]
