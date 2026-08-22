"""Savdo nazorati qoidalari — R1, R2, R3 va tekshiruv navbati.

Har test O'ZI uchun xodim, mijoz va noyob telefon kaliti yaratadi,
so'ng tekshiruvni AYNAN o'sha xodim bo'yicha filtrlab bajaradi.
Bazadagi boshqa ma'lumot natijaga umuman ta'sir qilmaydi.

⚠️ VAQT MINTAQASI TEKSHIRUVNING BIR QISMI. Savdoda faqat SANA bor,
qo'ng'iroqda esa UTC dagi VAQT. Shuning uchun testdagi qo'ng'iroqlar
`Asia/Tashkent` bo'yicha TUSHDA yaratiladi: chegara qaysi kunga
tushishi mintaqa xatosidan emas, qoidadan kelib chiqsin. Soat 00:30 da
yaratilgan qo'ng'iroq UTC da bir kun oldingi bo'lib qolardi va test
«qoida buzildi» deb yolg'on gapirardi.

Testlar HAQIQIY dev bazasida ishlaydi: hamma yozuvda `pytest-` prefiksi
bor va oxirida o'chiriladi.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus, CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.sales.application.compliance import (
    LOCAL_TZ,
    ComplianceFilter,
    ComplianceService,
    ReviewState,
    SkipReason,
    Verdict,
    resolve_window_days,
)
from src.modules.sales.application.review import save_review
from src.modules.sales.domain.entities import (
    SaleOpType,
    SaleReviewReason,
    SaleReviewStatus,
    WALK_IN_PARTNER_CODE,
)
from src.modules.sales.infrastructure.models import (
    SaleBranchModel,
    SaleModel,
    SalePartnerModel,
    SaleReviewModel,
)

# Haqiqiy eksport sarlavhasi — YAGONA manba `test_sales_import.py` da.
# Nusxa ko'chirilmaydi: sarlavhada lotin `c` (`Хақдор (cўм)`) kabi
# ko'zga tashlanmaydigan tuzoqlar bor va ikki joyda ikki xil bo'lib
# qolsa, import testi yashil turgani holda HTTP testi yiqilardi.
from src.modules.sales.tests.test_sales_import import REGISTER_HEADER

MARK = "pytest-"

#: Barcha testlarda savdo shu kunda bo'ladi — «bugun» ga bog'lanmaydi.
#
# Sanani `date.today()` dan olish testni ertalab soat 00:05 da
# yiqitardi: qo'ng'iroq mahalliy vaqtda «kecha» bo'lib qolardi.
SALE_DAY = date(2026, 5, 14)

TASHKENT = ZoneInfo(LOCAL_TZ)


@dataclass(slots=True)
class World:
    """Bitta test uchun ajratilgan olam."""

    agent_id: uuid.UUID
    agent_name: str
    phone_key: str
    partner_code: str
    sales: dict[str, uuid.UUID] = field(default_factory=dict)


def _local_noon(day: date) -> datetime:
    """Mahalliy vaqt bilan TUSHDA — kun chegarasidan uzoqda."""
    return datetime.combine(day, time(12, 0), tzinfo=TASHKENT)


@pytest_asyncio.fixture
async def world() -> AsyncIterator[Callable[..., Any]]:
    """Xodim + kontragent + qo'ng'iroq/savdo yaratuvchi.

    Telefon kaliti bazada MAVJUD EMASLIGI tekshiriladi: dev bazasida
    22 000 dan ortiq haqiqiy qo'ng'iroq bor va tasodifiy mos kelgan
    raqam testni jimgina buzardi.
    """
    created: list[uuid.UUID] = []
    codes: list[str] = []

    async def _make(*, code: str | None = None, with_phone: bool = True) -> World:
        async with SessionFactory() as session:
            key = ""
            if with_phone:
                while True:
                    key = f"7{uuid.uuid4().int % 10**8:08d}"
                    clash = (
                        await session.execute(
                            select(CallModel.id)
                            .where(CallModel.client_phone.like(f"%{key}"))
                            .limit(1)
                        )
                    ).first()
                    if clash is None:
                        break

            agent = AgentModel(
                full_name=f"{MARK}{uuid.uuid4().hex[:8]}",
                region="Toshkent",
                is_active=True,
            )
            session.add(agent)
            await session.flush()
            created.append(agent.id)

            partner_code = code or f"{MARK}{uuid.uuid4().hex[:6]}"
            if code is None:
                session.add(
                    SalePartnerModel(
                        code=partner_code,
                        name=f"{MARK}mijoz",
                        group_name="Клиенты",
                        phone=f"+998{key}" if with_phone else None,
                        phone_key=key or None,
                        is_active=True,
                    )
                )
                codes.append(partner_code)

            await session.commit()
            return World(
                agent_id=agent.id,
                agent_name=agent.full_name,
                phone_key=key,
                partner_code=partner_code,
            )

    yield _make

    async with SessionFactory() as session:
        await session.execute(
            delete(SaleModel).where(SaleModel.external_id.like(f"{MARK}%"))
        )
        # ⚠️ Filial qatorlari kaskad bilan ketmaydi: `sale_branches` ga
        # hech kim havola qilmaydi. HTTP testlari (import, biriktirish)
        # ularni yaratadi va qoldirib ketsa, ular admin panelida
        # haqiqiy SAP filiallari orasida ko'rinardi.
        await session.execute(
            delete(SaleBranchModel).where(SaleBranchModel.branch.like(f"{MARK}%"))
        )
        if codes:
            await session.execute(
                delete(SalePartnerModel).where(SalePartnerModel.code.in_(codes))
            )
        if created:
            # Xodim o'chsa qo'ng'iroqlari kaskad bilan ketadi.
            await session.execute(delete(AgentModel).where(AgentModel.id.in_(created)))
        await session.commit()


async def add_sale(w: World, day: date, *, name: str = "s") -> uuid.UUID:
    """Bitta savdo. `name` — test ichida qatorni tanib olish uchun."""
    async with SessionFactory() as session:
        sale = SaleModel(
            external_id=f"{MARK}{uuid.uuid4().hex[:12]}",
            op_type=SaleOpType.SALE.value,
            occurred_on=day,
            branch=f"{MARK}filial",
            partner_code=w.partner_code,
            partner_name=f"{MARK}mijoz",
            amount=Decimal("100.000"),
            currency="USD",
            amount_usd=Decimal("100.000"),
            agent_id=w.agent_id,
            phone_key=w.phone_key or None,
            source_file="pytest",
        )
        session.add(sale)
        await session.commit()
        w.sales[name] = sale.id
        return sale.id


async def add_call(
    w: World, day: date, *, call_type: CallType = CallType.SALES
) -> None:
    """Mijoz bilan bitta suhbat — mahalliy vaqt bilan tushda."""
    async with SessionFactory() as session:
        session.add(
            CallModel(
                external_id=f"{MARK}{uuid.uuid4().hex}",
                agent_id=w.agent_id,
                client_phone=f"+998{w.phone_key}",
                client_name=f"{MARK}mijoz",
                direction=CallDirection.OUTBOUND,
                status=CallStatus.COMPLETED,
                started_at=_local_noon(day),
                duration_sec=180,
                answered=True,
                call_type=call_type.value,
            )
        )
        await session.commit()


async def verdicts(w: World, *, window_days: int = 3, **kwargs: Any) -> dict[str, Any]:
    """Shu olamdagi savdolar bo'yicha xulosa — `external_id` siz, nom bilan."""
    async with SessionFactory() as session:
        result = await ComplianceService(session).page(
            ComplianceFilter(agent_ids=[w.agent_id], window_days=window_days, **kwargs),
            page=1,
            page_size=100,
        )
    by_id = {row.id: row for row in result.items}
    return {name: by_id.get(sale_id) for name, sale_id in w.sales.items()}


# ══════════════════════════════════════════════════════════════
#  R1 — savdo oldidan qo'ng'iroq
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_r1_savdo_kunidagi_qongiroq_oqlaydi(world) -> None:
    """Savdo kunining o'zidagi suhbat — eng yaqin holat, `days_before = 0`."""
    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY)

    row = (await verdicts(w))["s"]
    assert row.verdict.verdict == Verdict.OK.value
    assert row.verdict.broken_rules == []
    assert row.verdict.days_before == 0
    assert row.verdict.last_call_agent == w.agent_name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("days", "expected"), [(3, Verdict.OK.value), (4, Verdict.SUSPICIOUS.value)]
)
async def test_r1_oyna_chegarasi(world, days: int, expected: str) -> None:
    """⚠️ CHEGARA QULFLANADI: oyna 3 kun bo'lsa, 3 kun oldingi suhbat
    OQLAYDI, 4 kun oldingisi esa yo'q.

    Shartnomada oyna «savdo kuni + oldingi N kun» deb yozilgan, ya'ni
    jami N+1 kun. Bir kunlik xato butun ro'yxatni siljitib yuborardi va
    uni faqat qo'lda sanab topish mumkin bo'lardi.
    """
    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY - timedelta(days=days))

    row = (await verdicts(w, window_days=3))["s"]
    assert row.verdict.verdict == expected
    assert row.verdict.days_before == days
    assert ("R1" in row.verdict.broken_rules) is (expected == Verdict.SUSPICIOUS.value)


@pytest.mark.asyncio
async def test_r1_savdodan_keyingi_qongiroq_hisobga_olinmaydi(world) -> None:
    """Savdodan KEYINGI suhbat kelishuvni oqlay olmaydi.

    Vaqt orqaga oqmaydi: ertaga bo'ladigan suhbat bugungi savdoni
    tushuntirmaydi. Lekin u BOR — shuning uchun R3 («umuman
    gaplashilmagan») qo'yilmaydi va `calls_total` uni sanaydi.
    """
    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY + timedelta(days=1))

    row = (await verdicts(w))["s"]
    assert "R1" in row.verdict.broken_rules
    assert "R3" not in row.verdict.broken_rules
    assert row.verdict.last_call_at is None
    assert row.verdict.days_before is None
    assert row.verdict.calls_total == 1


@pytest.mark.asyncio
async def test_ichki_suhbat_r1_ni_oqlamaydi(world) -> None:
    """Hamkasb bilan gaplashuv mijoz bilan kelishuv EMAS.

    ⚠️ Busiz nazorat aldangan bo'lardi: ichki raqamga qilingan
    qo'ng'iroq har qanday savdoni «toza» qilib qo'yardi.
    """
    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY, call_type=CallType.INTERNAL)

    row = (await verdicts(w))["s"]
    assert row.verdict.verdict == Verdict.SUSPICIOUS.value
    assert "R1" in row.verdict.broken_rules
    assert row.verdict.calls_total == 0


# ══════════════════════════════════════════════════════════════
#  R2 — ikki savdo orasida qo'ng'iroq
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_r2_ikki_savdo_orasida_suhbat_bor(world) -> None:
    """`qo'ng'iroq → savdo → qo'ng'iroq → savdo` — to'g'ri ketma-ketlik."""
    w = await world()
    await add_sale(w, SALE_DAY - timedelta(days=10), name="birinchi")
    await add_call(w, SALE_DAY - timedelta(days=10))
    await add_sale(w, SALE_DAY, name="ikkinchi")
    await add_call(w, SALE_DAY - timedelta(days=1))

    rows = await verdicts(w)
    ikkinchi = rows["ikkinchi"].verdict
    assert ikkinchi.previous_sale_on == SALE_DAY - timedelta(days=10)
    assert ikkinchi.calls_between == 1
    assert "R2" not in ikkinchi.broken_rules
    assert rows["ikkinchi"].verdict.verdict == Verdict.OK.value


@pytest.mark.asyncio
async def test_r2_oraliqda_suhbat_yoq(world) -> None:
    """Oldingi savdodan keyin bitta ham suhbat bo'lmagan.

    ⚠️ CHEGARA ATAYLAB SHUNDAY: oldingi savdo KUNIDAGI suhbat oraliqqa
    KIRMAYDI — u o'sha savdoni oqlagan bo'lishi mumkin va bitta suhbat
    ikki savdoni oqlab yuborardi. Shu sababli bu yerda R1 buzilmaydi
    (suhbat oyna ichida), R2 esa buziladi.
    """
    w = await world()
    await add_sale(w, SALE_DAY - timedelta(days=1), name="birinchi")
    await add_call(w, SALE_DAY - timedelta(days=1))
    await add_sale(w, SALE_DAY, name="ikkinchi")

    ikkinchi = (await verdicts(w))["ikkinchi"].verdict
    assert ikkinchi.previous_sale_on == SALE_DAY - timedelta(days=1)
    assert ikkinchi.calls_between == 0
    assert ikkinchi.broken_rules == ["R2"]
    assert ikkinchi.days_before == 1


@pytest.mark.asyncio
async def test_r2_birinchi_savdoga_qollanmaydi(world) -> None:
    """Birinchi savdoda solishtiradigan narsa yo'q — R2 jim turadi.

    Savdo umuman suhbatsiz bo'lsa ham R2 emas, R1 va R3 qo'yiladi:
    aks holda har yangi mijozning birinchi savdosi ikki qoida bilan
    belgilanib, ro'yxat sun'iy og'irlashardi.
    """
    w = await world()
    await add_sale(w, SALE_DAY)

    row = (await verdicts(w))["s"].verdict
    assert row.previous_sale_on is None
    assert "R2" not in row.broken_rules
    assert row.broken_rules == ["R1", "R3"]


# ══════════════════════════════════════════════════════════════
#  R3 — umuman gaplashilmagan
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_r3_umuman_qongiroqsiz_mijoz(world) -> None:
    """Eng qattiq signal: telefon bor, savdo bor, suhbat YO'Q."""
    w = await world()
    await add_sale(w, SALE_DAY)

    row = (await verdicts(w))["s"].verdict
    assert row.verdict == Verdict.SUSPICIOUS.value
    assert "R3" in row.broken_rules
    assert row.calls_total == 0
    assert row.last_call_at is None


# ══════════════════════════════════════════════════════════════
#  Uchinchi toifa — tekshirib bo'lmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_umumiy_kod_shubhali_emas(world) -> None:
    """«Разовый клиент» — bitta kod ostida ko'p odam.

    Qo'ng'iroq yo'qligi bu yerda hech nimani anglatmaydi, shuning uchun
    savdo shubhali ham, toza ham emas: uchinchi toifa.
    """
    w = await world(code=WALK_IN_PARTNER_CODE)
    await add_sale(w, SALE_DAY)

    row = (await verdicts(w))["s"].verdict
    assert row.verdict == Verdict.NOT_CHECKABLE.value
    assert row.skip_reason == SkipReason.GENERIC_CODE.value
    assert row.broken_rules == []


@pytest.mark.asyncio
async def test_telefonsiz_mijoz_shubhali_emas(world) -> None:
    """Telefonsiz mijozni tekshirishning imkoni yo'q.

    ⚠️ Uni «shubhali» deb belgilash aynan biz oldini olmoqchi bo'lgan
    YOLG'ON SIGNAL bo'lardi: aybdor xodim emas, SAP dagi to'ldirilmagan
    katak.
    """
    w = await world(with_phone=False)
    await add_sale(w, SALE_DAY)

    row = (await verdicts(w))["s"].verdict
    assert row.verdict == Verdict.NOT_CHECKABLE.value
    assert row.skip_reason == SkipReason.NO_PHONE.value
    assert row.broken_rules == []


# ══════════════════════════════════════════════════════════════
#  Sozlama
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_oyna_sozlamadan_oqiladi(world, settings_guard) -> None:
    """`sales.window_days` haqiqatan o'qiladi, kodda qotirilmagan.

    Oyna 7 kunga kengaytirilsa, 5 kun oldingi suhbat savdoni oqlaydi.
    """
    await settings_guard("sales.window_days", 7)
    async with SessionFactory() as session:
        assert await resolve_window_days(session) == 7

    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY - timedelta(days=5))

    assert (await verdicts(w, window_days=3))["s"].verdict.verdict == (
        Verdict.SUSPICIOUS.value
    )
    assert (await verdicts(w, window_days=7))["s"].verdict.verdict == Verdict.OK.value


# ══════════════════════════════════════════════════════════════
#  Tekshiruv navbati
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qaror_qoyilgach_navbatdan_chiqadi(world) -> None:
    """Sukut filtri — «ko'rilmaganlar».

    Rahbar ko'rib bo'lgan savdo ertasi kuni yana ro'yxat boshida
    turmasligi kerak: aks holda navbat hech qachon tugamaydi.
    """
    w = await world()
    sale_id = await add_sale(w, SALE_DAY)

    navbat = await verdicts(w, review=ReviewState.NEW.value)
    assert navbat["s"] is not None

    async with SessionFactory() as session:
        await save_review(
            session,
            sale_id,
            status=SaleReviewStatus.JUSTIFIED,
            reason=SaleReviewReason.TELEGRAM,
            note="pytest",
            user_id=None,
        )

    try:
        assert (await verdicts(w, review=ReviewState.NEW.value))["s"] is None
        # Yo'qolmaydi — arxivda turadi va qarori ko'rinadi
        arxiv = (await verdicts(w, review=ReviewState.JUSTIFIED.value))["s"]
        assert arxiv is not None
        assert arxiv.review.status == SaleReviewStatus.JUSTIFIED.value
        assert arxiv.review.reason == SaleReviewReason.TELEGRAM.value
    finally:
        async with SessionFactory() as session:
            await session.execute(
                delete(SaleReviewModel).where(SaleReviewModel.sale_id == sale_id)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_hisobot_toifalarni_sanaydi(world) -> None:
    """Uchala toifa ham ekranda turadi — biri ikkinchisini yashirmaydi."""
    w = await world()
    await add_sale(w, SALE_DAY, name="toza")
    await add_call(w, SALE_DAY)
    await add_sale(w, SALE_DAY - timedelta(days=30), name="shubhali")

    async with SessionFactory() as session:
        report = await ComplianceService(session).summary(
            ComplianceFilter(agent_ids=[w.agent_id], window_days=3)
        )

    assert report.total == 2
    assert report.ok == 1
    assert report.suspicious == 1
    assert report.not_checkable == 0
    assert report.new == 1
    assert len(report.agents) == 1
    assert report.agents[0].agent_name == w.agent_name
    assert report.agents[0].sales == 2


@pytest.mark.asyncio
async def test_mijoz_kartochkasi_savdolarni_beradi(world) -> None:
    """`for_client` — 3-bosqichdagi vaqt chizig'i uchun."""
    w = await world()
    await add_sale(w, SALE_DAY)
    await add_call(w, SALE_DAY)

    async with SessionFactory() as session:
        rows = await ComplianceService(session).for_client(w.phone_key, limit=10)

    assert len(rows) == 1
    assert rows[0].occurred_on == SALE_DAY
    assert rows[0].verdict == Verdict.OK.value
    assert rows[0].review_status is None


# ══════════════════════════════════════════════════════════════
#  Ruxsatlar
# ══════════════════════════════════════════════════════════════

API = "http://test/api/v1"

def _register_xlsx(*, external_id: str, code: str, branch: str) -> bytes:
    """Bitta savdo qatoridan iborat eng kichik registr fayli."""
    from io import BytesIO

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(REGISTER_HEADER)
    sheet.append(
        [
            1,
            "Продажа",
            external_id,
            branch,
            "ВЕЛО",
            "1",
            "14.05.2026",
            code,
            f"{MARK}mijoz",
            "Клиенты",
            "561,000",
            "561,000",
            "",
            "",
            "USD",
            "",
        ]
    )
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_savdo_xodimi_nazoratni_kormaydi(sales_client) -> None:
    """⚠️ Bu ro'yxat XODIM USTIDAN olib boriladigan tekshiruv.

    Xodim o'z savdosi shubhali deb belgilanganini ko'rsa, tekshiruvdan
    oldin tayyorgarlik ko'rish imkoni tug'iladi va ro'yxatning ma'nosi
    qolmaydi. Shuning uchun `sales:*` ruxsatlarining `:own` ko'rinishi
    ham YO'Q.
    """
    client, _ = sales_client

    assert (await client.get(f"{API}/sales/compliance")).status_code == 403
    assert (await client.get(f"{API}/sales/compliance/summary")).status_code == 403
    assert (await client.get(f"{API}/sales/branches")).status_code == 403
    assert (
        await client.put(f"{API}/sales/branches/xxx", json={"agent_id": None})
    ).status_code == 403
    assert (
        await client.post(f"{API}/sales/import", files={"file": ("a.xlsx", b"x")})
    ).status_code == 403
    response = await client.post(
        f"{API}/sales/{uuid.uuid4()}/review", json={"status": "justified"}
    )
    assert response.status_code == 403


# ══════════════════════════════════════════════════════════════
#  HTTP chegarasi — HAR ENDPOINT uchun bitta test
# ══════════════════════════════════════════════════════════════
#
# ⚠️ XIZMAT QATLAMINI SINASH YETARLI EMAS. Yuqoridagi testlarning
# hammasi yashil turganda ham uchta endpoint 500 qaytargan: javob
# `slots=True` dataclass'dan yig'ilardi va `vars()` unda ishlamaydi
# (`__dict__` yo'q). Bunday xato FAQAT HTTP chegarasida — Pydantic
# javobni yig'ayotganda — chiqadi. Shuning uchun oltala yo'l ham
# «200 qaytardimi va javobda kerakli maydonlar bormi» deb alohida
# tekshiriladi.


@pytest.mark.asyncio
async def test_endpoint_import(admin_client, world) -> None:
    """`POST /sales/import` — haqiqiy `.xlsx`, hisobot bilan."""
    w = await world()
    external_id = f"{MARK}{uuid.uuid4().hex[:10]}"
    payload = _register_xlsx(
        external_id=external_id, code=w.partner_code, branch=f"{MARK}filial"
    )

    response = await admin_client.post(
        f"{API}/sales/import", files={"file": ("savdo kunlik.xlsx", payload)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "register"
    assert body["read"] == 1
    assert body["created"] == 1
    # Kontragent katalogda bor — telefon savdoga ko'chirilgan bo'lishi kerak
    assert body["unknown_partner"] == 0

    # Idempotentlik ham shu yerda: ikkinchi yuklash yangi qator yaratmaydi
    again = await admin_client.post(
        f"{API}/sales/import", files={"file": ("savdo kunlik.xlsx", payload)}
    )
    assert again.status_code == 200
    assert again.json()["created"] == 0


@pytest.mark.asyncio
async def test_endpoint_notogri_fayl(admin_client) -> None:
    """`.xlsx` dan boshqasi qabul qilinmaydi — xato aniq kod bilan."""
    response = await admin_client.post(
        f"{API}/sales/import",
        files={"file": ("hisobot.csv", b"a;b;c", "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sales_bad_file"


@pytest.mark.asyncio
async def test_endpoint_royxat(admin_client, world) -> None:
    """`GET /sales/compliance` — javob shakli frontend bilan kelishilgan."""
    w = await world()
    await add_sale(w, SALE_DAY)

    response = await admin_client.get(
        f"{API}/sales/compliance?page_size=50&agent_ids={w.agent_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"items", "total", "page", "page_size", "window_days"} <= set(body)
    assert body["window_days"] >= 0

    row = next(item for item in body["items"] if item["external_id"].startswith(MARK))
    # Shartnomaning 7.1-bo'limidagi qator — nomlar aynan shu
    assert {
        "id", "occurred_on", "external_id", "partner_code", "partner_name",
        "phone", "phone_key", "branch", "direction", "agent_id", "agent_name",
        "amount", "currency", "amount_usd", "verdict", "broken_rules",
        "skip_reason", "last_call_at", "last_call_agent", "days_before",
        "previous_sale_on", "calls_between", "calls_total", "review",
    } == set(row)
    assert row["verdict"] == Verdict.SUSPICIOUS.value
    assert row["review"] is None


@pytest.mark.asyncio
async def test_endpoint_hisobot(admin_client, world) -> None:
    """`GET /sales/compliance/summary` — toifalar va xodimlar kesimi."""
    w = await world()
    await add_sale(w, SALE_DAY)

    response = await admin_client.get(
        f"{API}/sales/compliance/summary?agent_ids={w.agent_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {
        "total", "ok", "suspicious", "not_checkable",
        "new", "justified", "confirmed", "window_days", "agents",
    } == set(body)
    assert body["total"] == 1
    assert body["suspicious"] == 1
    assert body["agents"][0]["agent_name"] == w.agent_name


@pytest.mark.asyncio
async def test_endpoint_filiallar(admin_client, world) -> None:
    """`GET /sales/branches` — xarita va har filialdagi savdolar soni."""
    w = await world()
    await add_sale(w, SALE_DAY)
    async with SessionFactory() as session:
        session.add(
            SaleBranchModel(branch=f"{MARK}filial", matched_automatically=False)
        )
        await session.commit()

    response = await admin_client.get(f"{API}/sales/branches")
    assert response.status_code == 200, response.text
    rows = response.json()
    row = next(item for item in rows if item["branch"] == f"{MARK}filial")
    assert set(row) == {
        "branch", "agent_id", "agent_name", "matched_automatically", "sales"
    }
    assert row["sales"] == 1
    assert row["agent_id"] is None


@pytest.mark.asyncio
async def test_endpoint_filialga_biriktirish(admin_client, world) -> None:
    """`PUT /sales/branches/{branch}` — savdolar ham darhol ko'chadi.

    ⚠️ Biriktirish savdolarni KO'CHIRISHI shart. `backfill_sale_links()`
    faqat bo'sh `agent_id` ni to'ldiradi, ya'ni xato biriktirishni
    tuzatganda eski savdolar eski xodimda qolib ketardi.
    """
    w = await world()
    await add_sale(w, SALE_DAY)
    branch = f"{MARK}filial"
    async with SessionFactory() as session:
        session.add(SaleBranchModel(branch=branch, matched_automatically=False))
        await session.commit()

    response = await admin_client.put(
        f"{API}/sales/branches/{branch}", json={"agent_id": str(w.agent_id)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_id"] == str(w.agent_id)
    assert body["agent_name"] == w.agent_name
    # Qo'lda qo'yilgan — keyingi importlar tegmasin
    assert body["matched_automatically"] is False
    assert body["sales"] == 1

    async with SessionFactory() as session:
        agent_id = (
            await session.execute(
                select(SaleModel.agent_id).where(SaleModel.branch == branch)
            )
        ).scalar_one()
    assert agent_id == w.agent_id

    # Yo'q filial — 404, 500 emas
    missing = await admin_client.put(
        f"{API}/sales/branches/{MARK}yoq", json={"agent_id": None}
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_endpoint_qaror(admin_client, world) -> None:
    """`POST /sales/{id}/review` — qaror qo'yiladi va navbatdan chiqadi."""
    w = await world()
    sale_id = await add_sale(w, SALE_DAY)

    response = await admin_client.post(
        f"{API}/sales/{sale_id}/review",
        json={"status": "justified", "reason": "telegram", "note": "pytest"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "justified"
    assert body["reason"] == "telegram"
    assert body["reviewed_by"]
    assert body["reviewed_at"]

    listed = f"{API}/sales/compliance?agent_ids={w.agent_id}&page_size=50"
    assert (await admin_client.get(f"{listed}&review=new")).json()["total"] == 0
    arxiv = (await admin_client.get(f"{listed}&review=justified")).json()
    assert arxiv["total"] == 1
    assert arxiv["items"][0]["review"]["reason"] == "telegram"

    # Yo'q savdo — 404, 500 emas
    missing = await admin_client.post(
        f"{API}/sales/{uuid.uuid4()}/review", json={"status": "confirmed"}
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_endpoint_review_all(admin_client, world) -> None:
    """`review=all` — qarori bor-yo'qligidan qat'i nazar hammasi.

    Sukut qiymat `new` bo'lib qoladi: ro'yxat ochilganda ko'rilmaganlar
    chiqishi to'g'ri. `all` esa rahbarning ANIQ tanlovi — oqlanganlar
    statistikasi shu ro'yxatdan o'qiladi.
    """
    w = await world()
    korilgan = await add_sale(w, SALE_DAY, name="korilgan")
    await add_sale(w, SALE_DAY - timedelta(days=1), name="korilmagan")

    await admin_client.post(
        f"{API}/sales/{korilgan}/review", json={"status": "confirmed"}
    )

    listed = f"{API}/sales/compliance?agent_ids={w.agent_id}&page_size=50"
    assert (await admin_client.get(f"{listed}&review=new")).json()["total"] == 1

    response = await admin_client.get(f"{listed}&review=all")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    holatlar = {
        (item["review"] or {}).get("status") for item in body["items"]
    }
    assert holatlar == {None, "confirmed"}
