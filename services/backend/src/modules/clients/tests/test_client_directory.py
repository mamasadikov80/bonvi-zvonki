"""Mijozlar ro'yxati — qo'ng'iroqlardan yig'ilishi.

NEGA BU TESTLAR BOR. Mijoz bizda alohida yozuv EMAS: u qo'ng'iroqdagi
telefon raqami bo'yicha yig'iladi. Ya'ni yig'ish qoidasi buzilsa,
ro'yxatda yo bir odam ikki qator bo'lib ko'rinadi (raqam formati
har xil), yo qo'ng'iroqlari yarmi boshqa qatorga tushib, sonlar
jimgina kamayadi.

⚠️ IZOLYATSIYA. Testlar haqiqiy dev bazasida ishlaydi va u yerda
minglab mijoz bor. Shuning uchun har test O'ZINING xodimini yaratadi
(`dataset`) va so'rovni `agent_ids` bilan aynan o'sha xodimga
toraytiradi — begona qatorlar natijaga umuman ta'sir qilmaydi.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.database import SessionFactory
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel

API = "http://test/api/v1"

#: Bitta odam — MoyZvonki bergan uch xil ko'rinishda. Oxirgi 9 raqam
#: bir xil, ya'ni bitta mijoz bo'lishi kerak.
SAME_PERSON = ["+998 90 111-22-33", "998901112233", "901112233"]


async def _add_calls(agent_id, rows: list[dict]) -> list[uuid.UUID]:
    """Xodimga qo'ng'iroqlar qo'shadi. Xodim o'chganda kaskad bilan ketadi."""
    now = datetime.now(UTC)
    ids: list[uuid.UUID] = []
    async with SessionFactory() as session:
        for index, row in enumerate(rows):
            call = CallModel(
                external_id=f"pytest-client-{uuid.uuid4().hex}",
                agent_id=agent_id,
                direction=row.get("direction", CallDirection.INBOUND),
                status=CallStatus.COMPLETED,
                started_at=now - timedelta(hours=index + 1),
                duration_sec=row.get("duration", 60),
                answered=row.get("answered", True),
                client_phone=row["phone"],
                client_name=row.get("name"),
                call_type=row.get("call_type", "sales"),
            )
            session.add(call)
            await session.flush()
            ids.append(call.id)
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_bir_odam_bitta_qator(admin_client, dataset) -> None:
    """Uch xil formatdagi raqam — bitta mijoz."""
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [{"phone": phone, "name": "Ali Do'kon"} for phone in SAME_PERSON],
    )

    response = await admin_client.get(
        f"{API}/clients", params={"agent_ids": str(data.agent_id)}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 1, "raqam formati mijozni bo'lib yubormasligi kerak"
    row = body["items"][0]
    assert row["key"] == "901112233"
    assert row["calls_total"] == 3
    assert row["name"] == "Ali Do'kon"


@pytest.mark.asyncio
async def test_yonalish_javobsiz_va_suhbat_sanaladi(admin_client, dataset) -> None:
    """Kiruvchi/chiquvchi, javobsiz va suhbat vaqti — alohida."""
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [
            {"phone": "901112233", "duration": 100},
            {"phone": "901112233", "duration": 50, "answered": False},
            {
                "phone": "901112233",
                "duration": 30,
                "direction": CallDirection.OUTBOUND,
                "answered": False,
            },
        ],
    )

    response = await admin_client.get(
        f"{API}/clients", params={"agent_ids": str(data.agent_id)}
    )
    row = response.json()["items"][0]

    assert row["inbound"] == 2
    assert row["outbound"] == 1
    # ⚠️ Javobsiz — faqat KIRUVCHI javobsiz. Chiquvchi javobsiz
    # («mijoz ko'tarmadi») bunga qo'shilsa, kompaniya javob bermagan
    # qo'ng'iroqlar soni ikki barobar oshib ketardi — Faollik bo'limi
    # bilan bir xil ta'rif.
    assert row["missed"] == 1
    assert row["talk_seconds"] == 180


@pytest.mark.asyncio
async def test_ichki_suhbat_sukut_boyicha_kirmaydi(admin_client, dataset) -> None:
    """Hamkasb — mijoz emas. `scope` bilan ular alohida ko'riladi."""
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [
            {"phone": "901112233", "name": "Mijoz"},
            {"phone": "700100200", "name": "Ombor", "call_type": "internal"},
        ],
    )
    params = {"agent_ids": str(data.agent_id)}

    default = (await admin_client.get(f"{API}/clients", params=params)).json()
    assert [row["key"] for row in default["items"]] == ["901112233"]

    internal = (
        await admin_client.get(f"{API}/clients", params={**params, "scope": "internal"})
    ).json()
    assert [row["key"] for row in internal["items"]] == ["700100200"]

    every = (
        await admin_client.get(f"{API}/clients", params={**params, "scope": "all"})
    ).json()
    assert every["total"] == 2


@pytest.mark.asyncio
async def test_qidiruv_sonni_ozgartirmaydi(admin_client, dataset) -> None:
    """⚠️ Qidiruv MIJOZNI tanlaydi, uning qo'ng'iroqlarini emas.

    Nomi faqat bitta qatorda yozilgan bo'lsa ham mijoz topilishi va
    JAMI soni to'liq ko'rinishi kerak. Aks holda qidirgan odam
    «12 ta emas, 1 ta ekan» degan xulosaga kelardi.
    """
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [
            {"phone": "901112233", "name": "Sardor Aka"},
            {"phone": "901112233", "name": None},
            {"phone": "901112233", "name": None},
        ],
    )
    params = {"agent_ids": str(data.agent_id)}

    by_name = (
        await admin_client.get(f"{API}/clients", params={**params, "search": "sardor"})
    ).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["calls_total"] == 3

    # Raqam istalgan formatda: bo'shliq va qavslar e'tiborsiz
    by_phone = (
        await admin_client.get(f"{API}/clients", params={**params, "search": "111 22"})
    ).json()
    assert by_phone["total"] == 1
    assert by_phone["items"][0]["calls_total"] == 3

    empty = (
        await admin_client.get(f"{API}/clients", params={**params, "search": "topilmas"})
    ).json()
    assert empty["total"] == 0


@pytest.mark.asyncio
async def test_tafsilot_royxat_bilan_bir_xil(admin_client, dataset) -> None:
    """Tafsilotdagi son ro'yxatdagi son bilan mos kelishi SHART."""
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [{"phone": "901112233", "name": "Ali"} for _ in range(4)],
    )
    params = {"agent_ids": str(data.agent_id)}

    listed = (await admin_client.get(f"{API}/clients", params=params)).json()["items"][0]
    detail = (
        await admin_client.get(f"{API}/clients/901112233", params=params)
    ).json()

    assert detail["client"]["calls_total"] == listed["calls_total"]
    assert detail["agents"][0]["agent_id"] == str(data.agent_id)
    assert detail["agents"][0]["calls"] == 4

    calls = (
        await admin_client.get(f"{API}/clients/901112233/calls", params=params)
    ).json()
    assert calls["total"] == 4
    assert {row["agent_id"] for row in calls["items"]} == {str(data.agent_id)}
    # Yangisidan eskisiga
    starts = [row["started_at"] for row in calls["items"]]
    assert starts == sorted(starts, reverse=True)


@pytest.mark.asyncio
async def test_bir_nechta_xodim_korinadi(admin_client, dataset) -> None:
    """Bitta mijoz bilan ikki xodim gaplashgan bo'lishi mumkin."""
    first = await dataset(scores=[])
    second = await dataset(scores=[])
    await _add_calls(first.agent_id, [{"phone": "901112233"} for _ in range(3)])
    await _add_calls(second.agent_id, [{"phone": "901112233"}])

    params = {"agent_ids": [str(first.agent_id), str(second.agent_id)]}
    row = (await admin_client.get(f"{API}/clients", params=params)).json()["items"][0]

    assert row["agent_count"] == 2
    # Asosiy xodim — eng ko'p gaplashgani
    assert row["main_agent_id"] == str(first.agent_id)

    detail = (
        await admin_client.get(f"{API}/clients/901112233", params=params)
    ).json()
    assert [a["calls"] for a in detail["agents"]] == [3, 1]


@pytest.mark.asyncio
async def test_sahifalash(admin_client, dataset) -> None:
    """Sahifa hajmi so'ralganicha, jami esa hamma mijozni sanaydi."""
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [{"phone": f"90111{index:04d}"} for index in range(5)],
    )
    params = {"agent_ids": str(data.agent_id), "page_size": 2}

    first = (await admin_client.get(f"{API}/clients", params=params)).json()
    assert first["total"] == 5
    assert len(first["items"]) == 2

    third = (
        await admin_client.get(f"{API}/clients", params={**params, "page": 3})
    ).json()
    assert len(third["items"]) == 1
    # Sahifalar kesishmasligi kerak
    assert third["items"][0]["key"] not in {row["key"] for row in first["items"]}


@pytest.mark.asyncio
async def test_savdo_xodimi_faqat_ozinikini_koradi(sales_client, dataset) -> None:
    """SALES boshqa xodimning mijozini KO'RMAYDI — `agent_ids` bersa ham."""
    client, own = sales_client
    stranger = await dataset(scores=[])
    await _add_calls(own.agent_id, [{"phone": "901112233", "name": "Meniki"}])
    await _add_calls(stranger.agent_id, [{"phone": "907778899", "name": "Begona"}])

    body = (
        await client.get(f"{API}/clients", params={"agent_ids": str(stranger.agent_id)})
    ).json()
    keys = {row["key"] for row in body["items"]}

    assert "907778899" not in keys, "begona mijoz ko'rinmasligi kerak"
    assert "901112233" in keys


@pytest.mark.asyncio
async def test_notogri_kalit_tushunarli_xato(admin_client) -> None:
    """`/clients/undefined` bo'sh sahifa emas, aniq javob bersin."""
    response = await admin_client.get(f"{API}/clients/undefined")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_topilmagan_mijoz_404(admin_client) -> None:
    response = await admin_client.get(f"{API}/clients/000000001")
    assert response.status_code == 404, response.text
