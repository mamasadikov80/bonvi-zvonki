"""Analitika endpointlari — dashboard shu yerdan ma'lumot oladi."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.deps import CurrentUser, DbSession
from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.analytics.application.activity import (
    CALLBACK_WINDOW_HOURS,
    LOCAL_TZ,
    ActivityService,
)
from src.modules.analytics.application.services import AnalyticsFilter, AnalyticsService
from src.modules.users.domain.entities import Role

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _inclusive_end(date_to: datetime | None) -> datetime | None:
    """`date_to` ni KUN OXIRIGA suradi — agar unda vaqt ko'rsatilmagan bo'lsa.

    ⚠️ NEGA KERAK. Filtr sharti `started_at <= date_to`. Foydalanuvchi
    «16-avgustgacha» deb tanlaganda frontend `2026-08-16` yuboradi va u
    `2026-08-16T00:00:00` ga aylanadi — natijada o'sha kunning BUTUN
    qo'ng'iroqlari tushib qolardi. Ekranda «bugungacha» so'ralib,
    bugungi ish ko'rinmasdi.

    Aniq vaqt berilgan bo'lsa (soat/daqiqa/soniya noldan farqli) hech
    narsa o'zgartirilmaydi: chaqiruvchi nima so'ragan bo'lsa o'sha.

    ⚠️ Bu qoida `surveys/presentation/router.py` dagi `_period()` bilan
    BIR XIL bo'lishi shart — aks holda ikkala sahifa bitta davr uchun
    ikki xil son ko'rsatadi.
    """
    if date_to is None:
        return None
    if (date_to.hour, date_to.minute, date_to.second, date_to.microsecond) != (
        0,
        0,
        0,
        0,
    ):
        return date_to
    return date_to + timedelta(days=1) - timedelta(microseconds=1)


def _activity_window(
    days: int, date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """Faollik oynasi — IKKI endpointda bir xil hisoblanadi.

    ⚠️ Takrorlanmasligi SHART. Asosiy hisobot va tafsilot ro'yxati
    boshqa-boshqa oyna olsa, tafsilot jamiga to'g'ri kelmasdi va
    tekshirish vositasi o'zi ishonchni buzardi.

    `(None, None)` qaytsa — chaqiruvchi `days` bilan ishlaydi.
    """
    since = _as_utc(date_from)
    until = _as_utc(_inclusive_end(date_to))

    if since is not None and until is None:
        until = datetime.now(UTC)
    if since is not None and until is not None and since >= until:
        raise ValidationError(
            "Boshlanish sanasi tugash sanasidan keyin bo'lolmaydi. "
            "Teskari oraliq jimgina BOSHQA davr ma'lumotini qaytarardi."
        )
    if since is None or until is None:
        # `days` bo'yicha: mahalliy butun kunlarga tekislanadi —
        # `ActivityService` bilan bir xil qoida
        hozir = datetime.now(UTC)
        mahalliy = hozir.astimezone(ZoneInfo(LOCAL_TZ))
        kun_boshi = mahalliy.replace(hour=0, minute=0, second=0, microsecond=0)
        since = (kun_boshi - timedelta(days=days - 1)).astimezone(UTC)
        until = hozir
    return since, until


def _as_utc(moment: datetime | None) -> datetime | None:
    """Mintaqasiz sanani UTC deb qabul qiladi.

    ⚠️ Pydantic `?date_from=2026-08-10` ni MINTAQASIZ `datetime` qilib
    o'qiydi. Uni mintaqali `datetime.now(UTC)` bilan solishtirish
    `TypeError` beradi va endpoint 500 qaytaradi — ya'ni hujjatda
    ko'rsatilgan parametrning oddiy shakli tizimni yiqitardi.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def build_filter(
    date_from: Annotated[datetime | None, Query(description="Boshlanish sanasi")] = None,
    date_to: Annotated[datetime | None, Query(description="Tugash sanasi")] = None,
    agent_ids: Annotated[list[UUID] | None, Query(description="Xodimlar")] = None,
    regions: Annotated[list[str] | None, Query(description="Hududlar")] = None,
    score_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    score_max: Annotated[int | None, Query(ge=0, le=100)] = None,
    has_red_flags: Annotated[bool | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=365, description="Oxirgi N kun")] = 30,
) -> AnalyticsFilter:
    """Query parametrlarini filtrga aylantiradi.

    `date_from` berilmasa — oxirgi `days` kun olinadi.
    """
    now = datetime.now(UTC)
    return AnalyticsFilter(
        date_from=date_from or (now - timedelta(days=days)),
        date_to=_inclusive_end(date_to) or now,
        agent_ids=list(agent_ids) if agent_ids else None,
        regions=list(regions) if regions else None,
        score_min=score_min,
        score_max=score_max,
        has_red_flags=has_red_flags,
    )


Filters = Annotated[AnalyticsFilter, Depends(build_filter)]


@router.get("/overview", summary="KPI kartalar")
async def overview(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).overview(f)


@router.get("/timeseries", summary="Vaqt bo'yicha trend")
async def timeseries(
    session: DbSession,
    user: CurrentUser,
    f: Filters,
    bucket: Literal["day", "week", "month"] = "day",
):
    return await AnalyticsService(session, user).timeseries(f, bucket)


@router.get("/agents", summary="Xodimlar reytingi")
async def agents(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).agent_leaderboard(f)


@router.get("/blocks", summary="Rubrika bloklari bo'yicha razrez")
async def blocks(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).block_breakdown(f)


@router.get("/red-flags", summary="Qoidabuzarliklar razrezi")
async def red_flags(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).red_flag_breakdown(f)


@router.get("/distribution", summary="Ball taqsimoti")
async def distribution(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).score_distribution(f)


@router.get("/regions", summary="Hududlar bo'yicha")
async def regions(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).by_region(f)


@router.get("/filters", summary="Filtr variantlari")
async def filter_options(session: DbSession, user: CurrentUser):
    return await AnalyticsService(session, user).filter_options()


# ══════════════════════════════════════════════════════════════
#  Qo'ng'iroq FAOLLIGI — hajm va javobgarlik (sifatdan mustaqil)
# ══════════════════════════════════════════════════════════════


class AgentActivityRow(BaseModel):
    agent_id: UUID
    agent_name: str
    region: str | None

    outbound_total: int
    """Xodim mijozlarga qilgan qo'ng'iroqlar."""
    outbound_answered: int
    outbound_no_answer: int
    """Mijoz ko'tarmadi. ⚠️ Bu «propushenniy» EMAS."""

    inbound_total: int
    """Mijozlar xodimga qilgan qo'ng'iroqlar."""
    inbound_known: int
    """Javob holati bilingan kiruvchilar — FOIZLAR shundan hisoblanadi."""
    inbound_answered: int
    missed: int
    """KIRUVCHI + javobsiz = «propushenniy». Kompaniya javobgarligi."""

    missed_called_back: int
    """Javobsiz HODISALARdan keyin aloqa bo'lganlari."""
    missed_addressable: int
    """Raqami bor javobsiz hodisalar — `missed_open` shundan."""
    missed_open: int
    """Javobsiz qolib, keyin ham aloqa bo'lmagan hodisalar (hajm)."""

    # ── Mijoz darajasi — ASOSIY ko'rsatkich ───────────────────
    #
    # Mijoz bog'lanolmasa qayta-qayta uriniadi (o'lchandi: o'rtacha 1.8
    # marta). Hodisalarni sanash bir odamning muammosini bir necha
    # marta hisoblardi. Yomonroq holat: mijoz 4 marta qo'ng'iroq qilib
    # 4-chisida javob olgan bo'lsa, hodisa hisobi «3 javobsiz, 75%»
    # deb ko'rsatadi — holbuki mijoz BOG'LANGAN.
    missed_clients: int
    """Bog'lanolmagan MIJOZLAR soni."""
    clients_reached: int
    clients_unreached: int
    """⚠️ HISOBOTNING ASOSIY RAQAMI — yo'qolgan savdo imkoniyati."""

    missed_rate: float | None
    callback_rate: float | None
    """Bog'lanolmagan mijozlarning qancha foiziga qaytilgan (MIJOZ
    darajasida, hodisa darajasida emas)."""

    total: int
    talk_seconds: int
    unknown_in: int
    unknown_out: int
    """Yo'nalish bo'yicha noma'lumlar. Ular bo'lmasa `outbound_total` va
    `answered + no_answer` orasidagi farqni ekranda tushuntirib
    bo'lmasdi — son o'z-o'ziga zid ko'rinardi."""

    unknown: int
    """`answered` noma'lum qatorlar. Hisobda SANALMAYDI — eski, ustun
    paydo bo'lishidan oldingi qatorlar. Qayta sinxronizatsiya to'ldiradi."""


class ActivityDayRow(BaseModel):
    """Bir kunlik hajm — grafik uchun.

    Faqat hajm: mijoz darajasidagi hisob bu yerda YO'Q va ataylab — u
    kun chegarasida buziladi (mijoz kechqurun qo'ng'iroq qilib, ertalab
    javob olishi mumkin) va grafikdagi raqam kartadagi bilan mos
    kelmasdi."""

    day: date
    inbound: int
    inbound_answered: int
    missed: int
    outbound: int
    outbound_no_answer: int


class ActivityHourRow(BaseModel):
    """Soatlik kesim — qaysi soatda mijozlar bog'lanolmaydi.

    ⚠️ Soat MAHALLIY vaqtda (Asia/Tashkent). UTC da bu razrez xulosani
    yo'q qilardi: «tushlikda javobsizlar ko'p» naqshi 12:00 da
    ko'rinadi, UTC da esa 07:00 ga siljib ma'nosini yo'qotadi."""

    hour: int
    inbound: int
    inbound_answered: int
    missed: int
    outbound: int
    outbound_no_answer: int
    missed_rate: float | None


class ActivityResponse(BaseModel):
    days: int
    date_from: datetime
    date_to: datetime
    callback_window_hours: int
    """Qaytib aloqaga chiqish shu muddat ichida hisobga olinadi."""
    callback_median_minutes: float | None
    days_series: list[ActivityDayRow]
    hours_series: list[ActivityHourRow]
    agents: list[AgentActivityRow]
    total: AgentActivityRow


def _activity_row(row) -> AgentActivityRow:
    return AgentActivityRow(
        agent_id=row.agent_id,
        agent_name=row.agent_name,
        region=row.region,
        outbound_total=row.outbound_total,
        outbound_answered=row.outbound_answered,
        outbound_no_answer=row.outbound_no_answer,
        inbound_total=row.inbound_total,
        inbound_known=row.inbound_known,
        inbound_answered=row.inbound_answered,
        missed=row.missed,
        missed_called_back=row.missed_called_back,
        missed_addressable=row.missed_addressable,
        missed_open=row.missed_open,
        missed_clients=row.missed_clients,
        clients_reached=row.clients_reached,
        clients_unreached=row.clients_unreached,
        missed_rate=row.missed_rate,
        callback_rate=row.callback_rate,
        total=row.total,
        talk_seconds=row.talk_seconds,
        unknown=row.unknown,
        unknown_in=row.unknown_in,
        unknown_out=row.unknown_out,
    )


@router.get(
    "/activity",
    response_model=ActivityResponse,
    summary="Qo'ng'iroq faolligi (hajm, javobsizlar, qaytib chiqish)",
)
async def activity(
    session: DbSession,
    user: CurrentUser,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Oxirgi N kun (1 / 7 / 15 / 30)"),
    ] = 7,
    date_from: Annotated[
        datetime | None,
        Query(description="Aniq boshlanish sanasi — `days` ni bekor qiladi"),
    ] = None,
    date_to: Annotated[datetime | None, Query(description="Tugash sanasi")] = None,
    agent_ids: Annotated[list[UUID] | None, Query(description="Xodimlar")] = None,
    regions: Annotated[list[str] | None, Query(description="Hududlar")] = None,
) -> ActivityResponse:
    """Kim kimga qancha qo'ng'iroq qildi va javobsizlarga qaytildimi.

    ⚠️ «Javobsiz» degan yagona son YO'Q. Kiruvchi javobsiz
    («propushenniy» — kompaniya javob bermadi) va chiquvchi javobsiz
    (mijoz ko'tarmadi) butunlay boshqa narsa: o'lchandi, 7 kunda 983 va
    1047. Ularni qo'shish raqamni ikki barobar oshirib, ma'nosini yo'q
    qiladi va xodimni nohaq ayblaydi.

    SALES roli faqat O'ZINING ma'lumotini ko'radi.
    """
    scoped = list(agent_ids) if agent_ids else None
    if user.role == Role.SALES:
        # ⚠️ URL dagi `agent_ids` E'TIBORSIZ qoldiriladi — savdo xodimi
        # hamkasbining faolligini ko'rmasligi kerak
        scoped = [user.agent_id] if user.agent_id else []

    # Aniq oraliq berilgan bo'lsa u USTUN turadi va O'ZGARTIRILMASDAN
    # uzatiladi. `days` esa tez tanlash uchun (1 / 7 / 15 / 30).
    #
    # ⚠️ ORALIQ KUN SONIGA AYLANTIRILMAYDI. Ilgari shunday qilinardi va
    # `timedelta.days` pastga yaxlitlaganligi uchun boshlanish sanasi
    # 24 soatgacha oldinga siljirdi — o'lchandi: «10–16 avgust»
    # so'rovida 853 qo'ng'iroq va 137 javobsiz JIMGINA tushib qolgan
    # edi, javobda esa hech qanday belgi yo'q edi.
    #
    # `_inclusive_end` — tugash sanasi kun OXIRIGA suriladi. Busiz
    # «17-avgustgacha» tanlovi yarim tunga aylanib, o'sha kunning butun
    # ishi tushib qolardi.
    since, until = _activity_window(days, date_from, date_to)

    report = await ActivityService(session).report(
        since=since,
        until=until,
        agent_ids=scoped,
        regions=list(regions) if regions else None,
    )
    return ActivityResponse(
        days=report.days,
        date_from=report.date_from,
        date_to=report.date_to,
        callback_window_hours=CALLBACK_WINDOW_HOURS,
        callback_median_minutes=report.callback_median_minutes,
        days_series=[
            ActivityDayRow(
                day=row.day,
                inbound=row.inbound,
                inbound_answered=row.inbound_answered,
                missed=row.missed,
                outbound=row.outbound,
                outbound_no_answer=row.outbound_no_answer,
            )
            for row in report.days_series
        ],
        hours_series=[
            ActivityHourRow(
                hour=row.hour,
                inbound=row.inbound,
                inbound_answered=row.inbound_answered,
                missed=row.missed,
                outbound=row.outbound,
                outbound_no_answer=row.outbound_no_answer,
                missed_rate=row.missed_rate,
            )
            for row in report.hours_series
        ],
        agents=[_activity_row(row) for row in report.agents],
        total=_activity_row(report.total),
    )


class MissedClientRow(BaseModel):
    """Bog'lanolmagan bitta mijoz — TEKSHIRISH uchun tafsilot.

    Hisobotdagi «100%» yoki «3 mijoz bog'lanmagan» degan son ishonchsiz
    ko'rinishi mumkin: xodimda 15 javobsiz qo'ng'iroq bo'lib, qaytish
    darajasi 100% bo'lishi g'alati tuyuladi. Aslida to'g'ri — 15 hodisa
    9 xil mijozdan kelgan va hammasi bilan gaplashilgan. Lekin buni
    ISBOTLAB ko'rsatmasa raqamga ishonch bo'lmaydi, ayniqsa rahbar
    oldida."""

    phone: str
    client_name: str | None
    attempts: int
    """Necha marta javobsiz qo'ng'iroq qilgan."""
    first_missed_at: datetime
    last_missed_at: datetime
    contacted_at: datetime | None
    """`null` — HALI bog'lanilmagan."""
    contacted_by: str | None
    """Kim bilan aloqa bo'lgan. Boshqa xodim bo'lishi mumkin."""
    contact_inbound: bool | None
    """`true` — mijoz o'zi qayta qo'ng'iroq qilib javob olgan;
    `false` — xodim qaytib qo'ng'iroq qilgan."""
    minutes_to_contact: float | None


class MissedClientsResponse(BaseModel):
    agent_id: UUID
    agent_name: str
    date_from: datetime
    date_to: datetime
    callback_window_hours: int
    clients: list[MissedClientRow]
    unreached: int


@router.get(
    "/activity/missed-clients",
    response_model=MissedClientsResponse,
    summary="Bitta xodimga bog'lanolmagan mijozlar (tekshirish uchun)",
)
async def missed_clients(
    session: DbSession,
    user: CurrentUser,
    agent_id: Annotated[UUID, Query(description="Xodim")],
    days: Annotated[int, Query(ge=1, le=365)] = 7,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> MissedClientsResponse:
    """Jadvaldagi sonni ISBOTLAB ko'rsatadi.

    ⚠️ Oyna va mantiq asosiy hisobot bilan AYNAN bir xil hisoblanadi —
    aks holda tafsilot jamiga to'g'ri kelmasdi va tekshirish vositasi
    o'zi ishonchni buzardi («jadvalda 9, ro'yxatda 8» eng yomon holat).

    SALES roli faqat O'ZINING ma'lumotini ko'radi.
    """
    if user.role == Role.SALES and user.agent_id != agent_id:
        raise ForbiddenError("Savdo xodimi faqat o'z ma'lumotini ko'radi")

    since, until = _activity_window(days, date_from, date_to)

    agent = await session.get(AgentModel, agent_id)
    if agent is None:
        raise NotFoundError(f"Xodim topilmadi: {agent_id}")

    rows = await ActivityService(session).missed_clients(
        agent_id=agent_id, since=since, until=until
    )
    return MissedClientsResponse(
        agent_id=agent_id,
        agent_name=agent.full_name,
        date_from=since,
        date_to=until,
        callback_window_hours=CALLBACK_WINDOW_HOURS,
        clients=[
            MissedClientRow(
                phone=row.phone,
                client_name=row.client_name,
                attempts=row.attempts,
                first_missed_at=row.first_missed_at,
                last_missed_at=row.last_missed_at,
                contacted_at=row.contacted_at,
                contacted_by=row.contacted_by,
                contact_inbound=row.contact_inbound,
                minutes_to_contact=row.minutes_to_contact,
            )
            for row in rows
        ],
        unreached=sum(1 for row in rows if row.contacted_at is None),
    )
