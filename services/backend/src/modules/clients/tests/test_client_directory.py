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
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.core.database import SessionFactory
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.sales.application.compliance import LOCAL_TZ
from src.modules.sales.domain.entities import SaleOpType
from src.modules.sales.infrastructure.models import SaleModel, SalePartnerModel

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
async def test_bosh_davr_mijozni_yoqotmaydi(admin_client, dataset) -> None:
    """⚠️ Tanlangan davrda aloqa bo'lmasa ham kartochka OCHILADI.

    Kartochkada davr tanlanadi («qachon kim bilan gaplashgan?») va
    bo'sh oraliq «bunday mijoz yo'q» degani emas. 404 qaytarilsa
    foydalanuvchi davrni toraytirib mijozni butunlay yo'qotgandek
    ko'rardi va bu nosozlikka o'xshardi.
    """
    data = await dataset(scores=[])
    await _add_calls(data.agent_id, [{"phone": "901112233", "name": "Ali"}])

    # Qo'ng'iroqlar bugungi kunda — o'tgan yilgi oraliqda hech nima yo'q
    params = {
        "agent_ids": str(data.agent_id),
        "date_from": "2020-01-01T00:00:00Z",
        "date_to": "2020-01-31T00:00:00Z",
    }

    response = await admin_client.get(f"{API}/clients/901112233", params=params)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["client"]["name"] == "Ali", "nomi butun tarixdan olinadi"
    assert body["client"]["calls_total"] == 0
    assert body["client"]["last_call_at"] is None
    assert body["agents"] == []

    calls = await admin_client.get(f"{API}/clients/901112233/calls", params=params)
    assert calls.json()["total"] == 0


@pytest.mark.asyncio
async def test_kartochkada_davr_ishlaydi(admin_client, dataset) -> None:
    """Davr tanlanganda sonlar ham, xodimlar ro'yxati ham qisqaradi."""
    data = await dataset(scores=[])
    ids = await _add_calls(
        data.agent_id,
        [{"phone": "901112233"} for _ in range(3)],
    )
    assert len(ids) == 3

    # `_add_calls` har qo'ng'iroqni bir soat orqaga suradi: eng eskisi
    # ~3 soat oldin. Oxirgi ikki soat — ikkita qo'ng'iroq.
    since = (datetime.now(UTC) - timedelta(hours=2, minutes=10)).isoformat()
    params = {"agent_ids": str(data.agent_id), "date_from": since}

    body = (await admin_client.get(f"{API}/clients/901112233", params=params)).json()
    assert body["client"]["calls_total"] == 2
    assert body["agents"][0]["calls"] == 2

    calls = (
        await admin_client.get(f"{API}/clients/901112233/calls", params=params)
    ).json()
    assert calls["total"] == 2


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


@pytest.mark.asyncio
async def test_ichki_raqam_kartochkasi_scope_siz_ochiladi(admin_client, dataset) -> None:
    """⚠️ XATO EDI: ichki raqamning kartochkasi hech qachon ochilmasdi.

    Ro'yxat `scope=internal` bilan ishlaydi, kartochkaning manzilida esa
    `scope` bo'lmasligi mumkin (havola saqlab qo'yilgan yoki qo'lda
    yozilgan). Backend sukut bo'yicha `clients` kesimida qidirardi va
    ichki raqam u yerda YO'Q — natijada ro'yxatda ko'rinib turgan qator
    bosilmas bo'lib qolardi.

    Endi kesimda topilmasa `all` bilan qayta qaraladi: yig'ma ham,
    suhbatlar jadvali ham ochiq.
    """
    data = await dataset(scores=[])
    await _add_calls(
        data.agent_id,
        [{"phone": "700100200", "name": "Ombor", "call_type": "internal"}],
    )
    params = {"agent_ids": str(data.agent_id)}

    # Ro'yxat kalitni aynan `internal` kesimida beradi
    listed = (
        await admin_client.get(f"{API}/clients", params={**params, "scope": "internal"})
    ).json()["items"]
    assert [row["key"] for row in listed] == ["700100200"]

    # ⚠️ `scope` YUBORILMAYDI — aynan buzilgan holat
    detail = await admin_client.get(f"{API}/clients/700100200", params=params)
    assert detail.status_code == 200, detail.text
    assert detail.json()["client"]["calls_total"] == 1
    assert detail.json()["agents"], "«kim gaplashgan» ham to'lishi kerak"

    calls = await admin_client.get(f"{API}/clients/700100200/calls", params=params)
    assert calls.status_code == 200, calls.text
    assert calls.json()["total"] == 1, "jadval ham bo'sh qolmasin"

    # Aniq kesim berilganda ham o'sha natija
    exact = await admin_client.get(
        f"{API}/clients/700100200", params={**params, "scope": "internal"}
    )
    assert exact.status_code == 200
    assert exact.json()["client"]["calls_total"] == 1


@pytest.mark.asyncio
async def test_kesim_kengayishi_xodim_chegarasini_buzmaydi(sales_client, dataset) -> None:
    """⚠️ Kesim kengaysa ham BEGONA mijoz ochilmaydi.

    `_locate` faqat `scope` ni almashtiradi; xodim va hudud shartlari
    joyida qoladi. Aks holda savdo xodimi istalgan raqamni manzilga
    yozib, hamkasbining mijozini ochib ko'rardi — bu ruxsat tizimidagi
    teshik bo'lardi.
    """
    client, own = sales_client
    stranger = await dataset(scores=[])
    await _add_calls(own.agent_id, [{"phone": "901112233", "name": "Meniki"}])
    await _add_calls(
        stranger.agent_id,
        [{"phone": "907778899", "name": "Begona", "call_type": "internal"}],
    )

    # O'ziniki — ochiladi
    mine = await client.get(f"{API}/clients/901112233")
    assert mine.status_code == 200, mine.text

    # Begona — kesim kengaytirilsa ham 404
    for params in ({}, {"scope": "all"}, {"scope": "internal"}):
        stranger_detail = await client.get(f"{API}/clients/907778899", params=params)
        assert stranger_detail.status_code == 404, stranger_detail.text

    stranger_calls = await client.get(f"{API}/clients/907778899/calls")
    assert stranger_calls.json()["total"] == 0, "begona suhbatlar ko'rinmasin"


# ══════════════════════════════════════════════════════════════
#  Kartochkadagi savdo tarixi (savdo-nazorati, 3-bosqich)
# ══════════════════════════════════════════════════════════════
#
# ⚠️ NEGA BU YERDA. `/clients/{key}/sales` mijoz kartochkasining bir
# qismi, lekin ruxsati `sales:read` — kartochkani ochish huquqidan
# ALOHIDA. Aynan shu chegara sinaladi: savdo xodimi mijozini ko'radi,
# uning ustidan olib borilayotgan tekshiruvni esa YO'Q.

#: Savdo shu kunda bo'ladi — «bugun» ga bog'lanmaydi.
#
# Sanani `date.today()` dan olish testni ertalab soat 00:05 da
# yiqitardi: qo'ng'iroq mahalliy vaqtda «kecha» bo'lib qolardi va
# R1 oynasi bir kunga siljirdi.
SALE_DAY = date(2026, 5, 14)


@pytest_asyncio.fixture
async def sale_client_key() -> AsyncIterator[Callable[..., Any]]:
    """Noyob telefon kaliti + o'sha kalitga bog'langan savdolar.

    Kalit bazada MAVJUD EMASLIGI tekshirilmaydi — u tasodifiy va
    `7` bilan boshlanadi; haqiqiy mobil raqamlar `9` bilan boshlanadi
    (`test_compliance.py` dagi bilan bir xil hiyla). Testlar haqiqiy
    dev bazasida ishlaydi, shuning uchun begona savdo yig'maga
    qo'shilib qolmasligi kerak.
    """
    codes: list[str] = []

    async def _make(agent_id, days: list[tuple[date, int]]) -> str:
        key = f"7{uuid.uuid4().int % 10**8:08d}"
        code = f"pytest-{uuid.uuid4().hex[:6]}"
        codes.append(code)

        async with SessionFactory() as session:
            session.add(
                SalePartnerModel(
                    code=code,
                    name="pytest-mijoz",
                    group_name="Клиенты",
                    phone=f"+998{key}",
                    phone_key=key,
                    is_active=True,
                )
            )
            for day, amount in days:
                session.add(
                    SaleModel(
                        external_id=f"pytest-{uuid.uuid4().hex[:12]}",
                        op_type=SaleOpType.SALE.value,
                        occurred_on=day,
                        branch="pytest-filial",
                        direction="ВЕЛО",
                        partner_code=code,
                        partner_name="pytest-mijoz",
                        amount=Decimal(amount),
                        currency="USD",
                        amount_usd=Decimal(amount),
                        agent_id=agent_id,
                        phone_key=key,
                        source_file="pytest",
                    )
                )
            await session.commit()
        return key

    yield _make

    async with SessionFactory() as session:
        if codes:
            await session.execute(
                delete(SaleModel).where(SaleModel.partner_code.in_(codes))
            )
            await session.execute(
                delete(SalePartnerModel).where(SalePartnerModel.code.in_(codes))
            )
        await session.commit()


async def _add_call_on(agent_id, phone: str, day: date) -> None:
    """Mahalliy vaqt bilan TUSHDA — kun chegarasidan uzoqda.

    Qo'ng'iroq UTC da saqlanadi, savdo sanasi bilan esa MAHALLIY kun
    solishtiriladi. Soat 00:30 dagi qo'ng'iroq UTC da «kechagi» bo'lib
    qolardi va test qoidani emas, vaqt mintaqasini sinardi.
    """
    async with SessionFactory() as session:
        session.add(
            CallModel(
                external_id=f"pytest-client-{uuid.uuid4().hex}",
                agent_id=agent_id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.COMPLETED,
                started_at=datetime.combine(day, time(12, 0), tzinfo=ZoneInfo(LOCAL_TZ)),
                duration_sec=180,
                answered=True,
                client_phone=f"+998{phone}",
                client_name="pytest-mijoz",
                call_type="sales",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_kartochkada_savdolar_va_yigma(
    admin_client, dataset, sale_client_key
) -> None:
    """`GET /clients/{key}/sales` — vaqt chizig'ining savdo qismi."""
    data = await dataset(scores=[])
    key = await sale_client_key(
        data.agent_id, [(SALE_DAY, 100), (SALE_DAY - timedelta(days=20), 200)]
    )
    # Faqat KEYINGI savdoni oqlaydigan suhbat: eskisi oldidan
    # gaplashilmagan, ya'ni u shubhali bo'lib qoladi.
    await _add_call_on(data.agent_id, key, SALE_DAY)

    response = await admin_client.get(f"{API}/clients/{key}/sales")
    assert response.status_code == 200, response.text
    body = response.json()

    assert {
        "items", "total", "amount_usd", "suspicious", "not_checkable", "window_days"
    } == set(body)
    assert body["total"] == 2
    assert body["amount_usd"] == 300.0
    assert body["suspicious"] == 1
    assert body["not_checkable"] == 0
    assert body["window_days"] >= 0

    # Yangisidan eskisiga
    assert [row["occurred_on"] for row in body["items"]] == [
        SALE_DAY.isoformat(),
        (SALE_DAY - timedelta(days=20)).isoformat(),
    ]
    row = body["items"][0]
    assert {
        "id", "occurred_on", "external_id", "branch", "direction", "agent_id",
        "agent_name", "amount", "currency", "amount_usd", "verdict",
        "broken_rules", "skip_reason", "last_call_at", "last_call_agent",
        "days_before", "previous_sale_on", "calls_between", "calls_total",
        "review_status",
    } == set(row)
    assert row["verdict"] == "ok"
    assert row["broken_rules"] == []
    # ⚠️ «Toza» degani aynan oyna ichida suhbat topilgani — dalil
    # bo'sh bo'lolmaydi.
    assert row["last_call_at"] is not None
    assert row["days_before"] == 0
    assert row["calls_total"] == 1
    assert row["review_status"] is None
    assert body["items"][1]["verdict"] == "suspicious"
    assert "R1" in body["items"][1]["broken_rules"]


@pytest.mark.asyncio
async def test_kartochkadagi_savdo_davri_qongiroqlar_bilan_bir_xil(
    admin_client, dataset, sale_client_key
) -> None:
    """Davr ikkala so'rovda ham BIR XIL parametr bilan yuboriladi.

    Frontend `rangeToQuery` dan `…T00:00:00.000Z` ko'rinishidagi ISO
    qiymat beradi — savdo endpointi ham aynan shuni tushunishi kerak,
    aks holda kartochkada ikki xil davr ko'rinardi.
    """
    data = await dataset(scores=[])
    key = await sale_client_key(
        data.agent_id, [(SALE_DAY, 100), (SALE_DAY - timedelta(days=20), 200)]
    )

    params = {
        "date_from": f"{SALE_DAY.isoformat()}T00:00:00.000Z",
        "date_to": f"{SALE_DAY.isoformat()}T23:59:59.999Z",
    }
    body = (await admin_client.get(f"{API}/clients/{key}/sales", params=params)).json()

    assert body["total"] == 1
    assert body["amount_usd"] == 100.0
    assert body["items"][0]["occurred_on"] == SALE_DAY.isoformat()


@pytest.mark.asyncio
async def test_savdosiz_mijozda_bosh_javob(admin_client, dataset) -> None:
    """Savdosi yo'q mijoz — 200 va nollar, xato EMAS.

    Kartochka savdo bo'lmasa ham ochiladi: 404 qaytarilsa sahifa
    nosozlikka o'xshab ko'rinardi.
    """
    data = await dataset(scores=[])
    await _add_calls(data.agent_id, [{"phone": "901112233"}])

    body = (await admin_client.get(f"{API}/clients/901112233/sales")).json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["amount_usd"] == 0.0


@pytest.mark.asyncio
async def test_savdo_xodimi_kartochkada_savdoni_kormaydi(sales_client) -> None:
    """⚠️ SALES mijozni ko'radi, uning savdo nazoratini KO'RMAYDI.

    Kartochka savdo xodimiga ochiq (o'z mijozi), lekin `sales:read`
    unda yo'q. Ruxsat kartochkani ochish huquqidan meros olinmasligi
    kerak: aks holda xodim o'z savdosi shubhali deb belgilanganini
    ko'rib, tekshiruvdan oldin tayyorgarlik ko'rardi.
    """
    client, own = sales_client
    await _add_calls(own.agent_id, [{"phone": "901112233", "name": "Meniki"}])

    calls = await client.get(f"{API}/clients/901112233/calls")
    assert calls.status_code == 200, "qo'ng'iroqlar ochiq qolishi kerak"

    sales = await client.get(f"{API}/clients/901112233/sales")
    assert sales.status_code == 403, sales.text
