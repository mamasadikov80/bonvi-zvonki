"""Mijozlar endpointlari.

Mijoz — bu telefon RAQAMI va u bilan bo'lgan barcha suhbatlar. Nega
katalogdan emas, qo'ng'iroqlardan yig'ilishi
`clients/application/directory.py` da yozilgan.

Ruxsat qo'ng'iroqlarnikidek: bu bo'lim o'sha ma'lumotni boshqa
kesimda ko'rsatadi, ya'ni kim qo'ng'iroqni ko'ra olsa — mijozni ham.
SALES roli faqat O'ZI gaplashgan mijozlarni ko'radi.

⚠️ BITTA ISTISNO — `/{key}/sales`. Savdo nazorati ma'lumoti
kartochkaga qo'shilsa ham, u YERDA HAM `sales:read` talab qilinadi
(savdo-nazorati shartnomasi, 7.1). Sabab: bu ro'yxat xodim ustidan
olib boriladigan tekshiruv va savdo xodimi o'z mijozining
kartochkasini ochib, savdosi shubhali deb belgilanganini KO'RMASLIGI
kerak. Ruxsat kartochkani ochish huquqidan MEROS OLINMAYDI.
"""

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.deps import (
    CurrentUser,
    DbSession,
    require_any_permission,
    require_permission,
)
from src.core.exceptions import NotFoundError, ValidationError
from src.modules.clients.application.directory import (
    ClientDirectory,
    ClientFilter,
    ClientScope,
    ClientSort,
)
from src.modules.sales.application.compliance import (
    ComplianceService,
    resolve_window_days,
)
from src.modules.users.domain.entities import Role

router = APIRouter(prefix="/clients", tags=["Clients"])

#: Qo'ng'iroq ma'lumotini o'qish sharti — `calls` bo'limi bilan bir xil.
CanReadClients = Depends(require_any_permission("calls:read", "calls:read:own"))

#: Savdo nazorati sharti — `sales` bo'limi bilan bir xil, `:own` yo'q.
CanReadSales = Depends(require_permission("sales:read"))


def _inclusive_end(date_to: datetime | None) -> datetime | None:
    """`date_to` ni KUN OXIRIGA suradi — vaqt ko'rsatilmagan bo'lsa.

    ⚠️ Bu qoida `analytics/presentation/router.py` dagi `_inclusive_end`
    bilan BIR XIL bo'lishi shart. Aks holda bitta davr uchun ikki
    bo'limda ikki xil son chiqadi: filtr sharti `started_at <= date_to`
    va frontend `2026-08-16` yuborganda u yarim tunga aylanib, o'sha
    kunning butun ishi tushib qolardi.
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


def _key_or_error(key: str) -> str:
    """Manzildagi kalit — faqat raqamlar.

    Kalit bevosita `SQL` ga tushmaydi (bog'langan parametr), lekin
    aniq shakl xatoni erta ko'rsatadi: `/clients/undefined` kabi
    so'rov bo'sh sahifa emas, tushunarli javob olsin.
    """
    cleaned = key.strip()
    if not cleaned.isdigit():
        raise ValidationError("Mijoz kaliti — faqat raqamlardan iborat bo'ladi")
    return cleaned


class ClientListItem(BaseModel):
    key: str
    """Raqamning oxirgi 9 tasi — ro'yxat va tafsilot uchun identifikator."""
    name: str | None
    phone: str | None
    calls_total: int
    inbound: int
    outbound: int
    missed: int
    """Kiruvchi va javobsiz — kompaniya javob bermagani."""
    talk_seconds: int
    first_call_at: datetime | None
    """`None` — tanlangan davrda aloqa bo'lmagan (faqat kartochkada)."""
    last_call_at: datetime | None
    agent_count: int
    main_agent_id: UUID | None
    main_agent_name: str | None
    main_agent_color: str | None
    avg_score: float | None
    scored: int
    """Nechta suhbat baholangan — o'rtacha shundan hisoblangan."""


class PaginatedClients(BaseModel):
    items: list[ClientListItem]
    total: int
    page: int
    page_size: int


class ClientAgentItem(BaseModel):
    agent_id: UUID
    full_name: str
    color: str | None
    region: str | None
    calls: int
    last_call_at: datetime


class ClientDetail(BaseModel):
    client: ClientListItem
    agents: list[ClientAgentItem]
    """Mijoz bilan gaplashgan xodimlar — ko'pdan kamga."""


class ClientCallItem(BaseModel):
    id: UUID
    started_at: datetime
    duration_sec: int
    direction: str
    answered: bool | None
    status: str
    call_type: str | None
    agent_id: UUID
    agent_name: str
    agent_color: str | None
    score: int | None
    red_flag_count: int
    needs_review: bool


class PaginatedClientCalls(BaseModel):
    items: list[ClientCallItem]
    total: int
    page: int
    page_size: int


class ClientSaleItem(BaseModel):
    """Vaqt chizig'idagi bitta savdo.

    Maydon nomlari `/sales/compliance` bilan BIR XIL (`id`, `verdict`,
    `broken_rules`…) — ikkita lug'at bo'lmasin: frontendda savdo
    qatorining turi ikkala ekranda ham bitta joydan o'qiladi.
    """

    id: UUID
    occurred_on: date
    """⚠️ Faqat SANA. SAP savdoga vaqt bermaydi — kun ichidagi aniq
    tartib noma'lum (`docs/savdo-nazorati.md`, 2.1)."""
    external_id: str
    branch: str | None = None
    direction: str | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    amount: float | None = None
    currency: str
    amount_usd: float | None = None
    verdict: str
    broken_rules: list[str]
    skip_reason: str | None = None

    # ── DALIL ────────────────────────────────────────────────
    #
    # ⚠️ Nomlar `/sales/compliance` dagi bilan AYNAN bir xil va
    # qiymatlar ham aynan bir xil bo'lishi shart: ikkala yo'l bitta
    # manbadan (`ComplianceService`) oziqlanadi. Ajralib ketsa,
    # kartochkadagi son ro'yxatdagidan farq qilardi — bunday
    # ziddiyatdan keyin ikkala ekranga ham ishonib bo'lmaydi.
    #
    # ⚠️ «Toza» qatorda `last_call_at` BO'SH BO'LOLMAYDI: xulosa aynan
    # o'sha suhbat topilgani uchun `ok`. Bo'sh kelsa — bu hisoblash
    # emas, javobni yig'ish xatosi.
    last_call_at: datetime | None = None
    last_call_agent: str | None = None
    days_before: int | None = None
    previous_sale_on: date | None = None
    calls_between: int
    calls_total: int

    review_status: str | None = None


class ClientSalesOut(BaseModel):
    items: list[ClientSaleItem]
    total: int
    """Davrdagi BARCHA savdolar — `items` kesilgan bo'lsa ham to'g'ri."""
    amount_usd: float
    suspicious: int
    not_checkable: int
    window_days: int
    """R1 oynasi — ekranda «savdo kuni + oldingi N kun» deb yoziladi."""


def _filter(
    user: CurrentUser,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    agent_ids: list[UUID] | None,
    regions: list[str] | None,
    scope: ClientScope,
    search: str | None = None,
) -> ClientFilter:
    """So'rov parametrlaridan filtr — HAR uchala endpointda bir xil."""
    scoped = list(agent_ids) if agent_ids else None
    if user.role == Role.SALES:
        # ⚠️ URL dagi `agent_ids` E'TIBORSIZ qoldiriladi: savdo xodimi
        # hamkasbining mijozini ko'rmasligi kerak. `agent_id` yo'q
        # bo'lsa bo'sh ro'yxat — hech kimniki emas.
        scoped = [user.agent_id] if user.agent_id else []

    return ClientFilter(
        since=date_from,
        until=_inclusive_end(date_to),
        agent_ids=scoped,
        regions=list(regions) if regions else None,
        scope=scope,
        search=search,
    )


@router.get(
    "",
    response_model=PaginatedClients,
    summary="Mijozlar ro'yxati (qo'ng'iroqlardan yig'iladi)",
    dependencies=[CanReadClients],
)
async def list_clients(
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_ids: Annotated[list[UUID] | None, Query(description="Xodimlar")] = None,
    regions: Annotated[list[str] | None, Query(description="Hududlar")] = None,
    scope: Annotated[
        ClientScope,
        Query(description="`clients` — ichkilardan boshqa hammasi (sukut)"),
    ] = ClientScope.CLIENTS,
    search: Annotated[
        str | None, Query(description="Ism yoki raqam bo'yicha qidiruv")
    ] = None,
    sort: Annotated[ClientSort, Query()] = ClientSort.LAST_CALL,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> PaginatedClients:
    """Kim bilan gaplashilgan, qancha va oxirgi marta qachon.

    Qidiruv ism va raqam bo'yicha ishlaydi; raqam istalgan formatda
    kiritilishi mumkin («90 123», «+998901234567») — solishtirish
    faqat raqamlar bo'yicha.
    """
    directory = ClientDirectory(session)
    result = await directory.page(
        _filter(
            user,
            date_from=date_from,
            date_to=date_to,
            agent_ids=agent_ids,
            regions=regions,
            scope=scope,
            search=search,
        ),
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return PaginatedClients(
        items=[ClientListItem(**asdict(row)) for row in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/{key}",
    response_model=ClientDetail,
    summary="Bitta mijoz — yig'ma va u bilan gaplashgan xodimlar",
    dependencies=[CanReadClients],
)
async def get_client(
    key: str,
    session: DbSession,
    user: CurrentUser,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_ids: Annotated[list[UUID] | None, Query()] = None,
    regions: Annotated[list[str] | None, Query()] = None,
    scope: Annotated[ClientScope, Query()] = ClientScope.CLIENTS,
) -> ClientDetail:
    """Tafsilot ro'yxat bilan BIR XIL filtrni oladi.

    Aks holda ro'yxatda «12 qo'ng'iroq» deb turgan mijozning ichida
    boshqa son chiqardi va qaysi biriga ishonish noaniq bo'lardi.
    """
    cleaned = _key_or_error(key)
    directory = ClientDirectory(session)
    f = _filter(
        user,
        date_from=date_from,
        date_to=date_to,
        agent_ids=agent_ids,
        regions=regions,
        scope=scope,
    )

    summary = await directory.summary(cleaned, f)
    if summary is None:
        raise NotFoundError("Bu raqam bo'yicha qo'ng'iroq topilmadi")

    agents = await directory.agents_of(cleaned, f)
    return ClientDetail(
        client=ClientListItem(**asdict(summary)),
        agents=[ClientAgentItem(**asdict(row)) for row in agents],
    )


@router.get(
    "/{key}/calls",
    response_model=PaginatedClientCalls,
    summary="Mijoz bilan bo'lgan barcha suhbatlar",
    dependencies=[CanReadClients],
)
async def client_calls(
    key: str,
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_ids: Annotated[list[UUID] | None, Query()] = None,
    regions: Annotated[list[str] | None, Query()] = None,
    scope: Annotated[ClientScope, Query()] = ClientScope.CLIENTS,
) -> PaginatedClientCalls:
    """Yangisidan eskisiga. Har qatorda KIM gaplashgani ko'rinadi."""
    cleaned = _key_or_error(key)
    result = await ClientDirectory(session).calls(
        cleaned,
        _filter(
            user,
            date_from=date_from,
            date_to=date_to,
            agent_ids=agent_ids,
            regions=regions,
            scope=scope,
        ),
        page=page,
        page_size=page_size,
    )
    return PaginatedClientCalls(
        items=[
            ClientCallItem(
                id=row.call_id,
                started_at=row.started_at,
                duration_sec=row.duration_sec,
                direction=row.direction,
                answered=row.answered,
                status=row.status,
                call_type=row.call_type,
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                agent_color=row.agent_color,
                score=row.score,
                red_flag_count=row.red_flag_count,
                needs_review=row.needs_review,
            )
            for row in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/{key}/sales",
    response_model=ClientSalesOut,
    summary="Mijozning savdolari — xulosa va dalili bilan",
    dependencies=[CanReadSales],
)
async def client_sales(
    key: str,
    session: DbSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ClientSalesOut:
    """Kartochkadagi vaqt chizig'ining ikkinchi yarmi.

    ⚠️ RUXSAT — `sales:read`, kartochkani ochish huquqidan ALOHIDA
    (modul izohiga qarang). Savdo xodimi shu mijozning qo'ng'iroqlarini
    ko'radi, savdo nazoratini esa YO'Q: bu ro'yxat uning ustidan olib
    boriladigan tekshiruv.

    ⚠️ DAVR PARAMETRLARI `datetime` — qo'ng'iroqlarnikidek. Savdoda
    faqat sana bor va u yerda `date` yetarli bo'lardi, lekin kartochka
    ikkala so'rovga BIR XIL parametrni yuboradi
    (`rangeToQuery` → `…T00:00:00.000Z`). Ikki xil format qilinsa,
    frontendda ikkinchi sana lug'ati paydo bo'lardi va bitta ekranda
    ikki xil davr ko'rsatish xavfi tug'ilardi. Bu yerda faqat KUNI
    olinadi: savdoda soat yo'q, ya'ni `date_to` ni kun oxiriga surish
    ham kerak emas (`occurred_on <= date_to` allaqachon shu kunni
    o'z ichiga oladi).

    ⚠️ SAHIFALASH YO'Q, chegara bor. Bitta mijozning savdolari
    o'nliklar bilan o'lchanadi (o'lchandi: eng ko'pi 20 ta), vaqt
    chizig'i esa bo'linmasligi kerak — qo'ng'iroq va savdo bir
    ro'yxatda turadi. Chegara shunchaki himoya: `total` baribir
    to'g'ri sonni aytadi.
    """
    cleaned = _key_or_error(key)
    window_days = await resolve_window_days(session)
    result = await ComplianceService(session).for_client(
        cleaned,
        since=date_from.date() if date_from else None,
        until=date_to.date() if date_to else None,
        limit=limit,
        window_days=window_days,
    )

    return ClientSalesOut(
        items=[
            ClientSaleItem(
                id=row.sale_id,
                occurred_on=row.occurred_on,
                external_id=row.external_id,
                branch=row.branch,
                direction=row.direction,
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                amount=row.amount,
                currency=row.currency,
                amount_usd=row.amount_usd,
                verdict=row.verdict,
                broken_rules=row.broken_rules,
                skip_reason=row.skip_reason,
                last_call_at=row.last_call_at,
                last_call_agent=row.last_call_agent,
                days_before=row.days_before,
                previous_sale_on=row.previous_sale_on,
                calls_between=row.calls_between,
                calls_total=row.calls_total,
                review_status=row.review_status,
            )
            for row in result.items
        ],
        total=result.total,
        amount_usd=result.amount_usd,
        suspicious=result.suspicious,
        not_checkable=result.not_checkable,
        window_days=window_days,
    )
