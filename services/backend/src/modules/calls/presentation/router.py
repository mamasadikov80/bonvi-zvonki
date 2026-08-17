"""Qo'ng'iroqlar endpointlari."""

from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import false, func, nullslast, or_, select
from sqlalchemy.orm import aliased

from src.core.deps import CurrentUser, DbSession, require_permission
from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.moizvonki.application.factory import moizvonki_client
from src.modules.moizvonki.application.ingest import IngestService
from src.modules.calls.domain.entities import CallType
from src.modules.moizvonki.domain.entities import (
    SYNC_MAX_DAYS,
    RecordingNotFoundError,
)
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.scoring.infrastructure.rubric_models import RubricModel
from src.modules.users.domain.entities import Role, User, has_permission

router = APIRouter(prefix="/calls", tags=["Calls"])


def require_any_permission(*permissions: str) -> Callable:
    """Sanab o'tilganlardan BITTASI yetarli bo'lgan tekshiruv.

    Qo'ng'iroqlarga ikki xil huquq bilan kelinadi: ADMIN/MANAGER da
    `calls:read`, SALES da esa faqat `calls:read:own`. Yagona
    `require_permission("calls:read")` savdo xodimini ham to'sib
    qo'yardi, shuning uchun qamrovni ruxsat emas, so'rovning o'zi
    toraytiradi (`Role.SALES` sharti pastda).
    """

    async def checker(user: CurrentUser) -> User:
        if not any(has_permission(user.role, name) for name in permissions):
            raise ForbiddenError("Ruxsat yetarli emas: " + " yoki ".join(permissions))
        return user

    return checker


#: Qo'ng'iroq ma'lumotini o'qish uchun kirish sharti. Yozuv — eng nozik
#: ma'lumot (transkript, mijoz nomi, xodimning xatolari), shuning uchun
#: uchala o'qish endpointi ham shu bitta shartdan o'tadi.
CanReadCalls = Depends(require_any_permission("calls:read", "calls:read:own"))


def _ilike_ekranla(matn: str) -> str:
    """`ILIKE` metabelgilarini oddiy belgiga aylantiradi.

    Foydalanuvchi `%` yoki `_` ni matn deb yozadi («MChJ 100% Sut»),
    shablon deb emas. Ekranlanmasa bitta `%` butun filtrni o'chirib
    yuboradi. Teskari chiziq birinchi almashtiriladi — aks holda o'zi
    qo'ygan ekranlar qayta ekranlanib ketadi.
    """
    for belgi in ("\\", "%", "_"):
        matn = matn.replace(belgi, f"\\{belgi}")
    return matn


class SortField(StrEnum):
    """Jadval sarlavhasidagi saralanadigan ustunlar."""

    DATE = "date"
    AGENT = "agent"
    CLIENT = "client"
    DURATION = "duration"
    SCORE = "score"
    STATUS = "status"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CallTypeFilter(StrEnum):
    """Tur bo'yicha filtr qiymatlari.

    `CallType` ning ustiga ikkita qiymat qo'shiladi:

      · `unknown`   — hali tasniflanmagan (`call_type IS NULL`);
      · `not_sales` — savdodan boshqa HAMMASI, bitta tanlov bilan.

    NEGA KERAK. Tasniflashdan keyin ma'lumotning katta qismi savdo
    bo'lmay chiqdi (o'lchandi: 69 tadan 63 tasi). Filtrsiz menejer
    savdo suhbatini ko'rish uchun o'nlab ichki suhbatni varaqlashi
    kerak — ya'ni yangi imkoniyat ro'yxatni ishlatib bo'lmas qildi.
    """

    SALES = "sales"
    SERVICE = "service"
    INTERNAL = "internal"
    PERSONAL = "personal"
    UNCLEAR = "unclear"
    UNKNOWN = "unknown"
    NOT_SALES = "not_sales"


class CallListItem(BaseModel):
    id: UUID
    started_at: datetime
    duration_sec: int
    status: str
    agent_id: UUID
    agent_name: str
    agent_color: str

    client_name: str | None
    """Katalogdagi mijoz nomi, u bo'lmasa MoyZvonki bergani."""
    client_phone: str | None
    """Nom umuman bo'lmaganda ko'rsatiladi — «—» dan foydaliroq."""

    call_type: str | None
    """`sales | service | internal | personal | unclear`. `null` — hali
    tasniflanmagan. FAQAT `sales` baholanadi, shuning uchun boshqa
    turlarda `score` bo'sh bo'lishi XATO EMAS."""

    score: int | None
    red_flag_count: int
    needs_review: bool


class PaginatedCalls(BaseModel):
    items: list[CallListItem]
    total: int
    page: int
    page_size: int


class CallDetail(BaseModel):
    id: UUID
    started_at: datetime
    duration_sec: int
    status: str
    direction: str
    agent: dict[str, Any]

    client: dict[str, Any] | None
    """Katalogdagi mijoz — faqat raqam `clients` da topilgan bo'lsa."""
    client_name: str | None
    """MoyZvonki bergan nom. Katalogda mijoz bo'lmaganda ham to'la."""
    client_phone: str | None

    call_type: str | None
    call_type_reason: str | None
    """AI nega shu turni tanlagani. Qo'lda tuzatish yo'q, shuning uchun
    qaror hech bo'lmasa tushuntirilgan bo'lishi kerak — menejer sababni
    o'qib, xato bo'lsa «Qayta baholash» bilan qaytadan yuboradi."""
    call_type_confidence: float | None

    transcript: str | None
    score: dict[str, Any] | None


@router.get(
    "",
    response_model=PaginatedCalls,
    summary="Qo'ng'iroqlar ro'yxati",
    dependencies=[CanReadCalls],
)
async def list_calls(
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    agent_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    score_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    score_max: Annotated[int | None, Query(ge=0, le=100)] = None,
    needs_review: bool | None = None,
    call_type: Annotated[
        CallTypeFilter | None,
        Query(description="Qo'ng'iroq turi. `not_sales` — savdodan boshqa hammasi"),
    ] = None,
    search: str | None = None,
    sort: Annotated[SortField, Query(description="Saralash ustuni")] = SortField.DATE,
    order: Annotated[SortOrder, Query(description="Yo'nalish")] = SortOrder.DESC,
):
    agent = aliased(AgentModel)
    client = aliased(ClientModel)
    score = aliased(CallScoreModel)

    stmt = (
        select(CallModel, agent, client, score)
        .join(agent, agent.id == CallModel.agent_id)
        .outerjoin(client, client.id == CallModel.client_id)
        .outerjoin(score, score.call_id == CallModel.id)
    )

    # SALES faqat o'zinikini ko'radi
    if user.role == Role.SALES:
        stmt = stmt.where(CallModel.agent_id == user.agent_id)
    elif agent_id:
        stmt = stmt.where(CallModel.agent_id == agent_id)

    if date_from:
        stmt = stmt.where(CallModel.started_at >= date_from)
    if date_to:
        if date_to.time() == time.min:
            # Frontend bu maydonga SANA yuboradi va u yarim tunga
            # aylanadi — `<=` bilan tanlangan oxirgi kun butunlay tushib
            # qolardi. Vaqti ko'rsatilmagan chegara «shu kun ham kirsin»
            # degani, shuning uchun ertangi yarim tundan OLDIN deb o'qiladi.
            stmt = stmt.where(CallModel.started_at < date_to + timedelta(days=1))
        else:
            # Aniq vaqt berilgan bo'lsa foydalanuvchi nima so'raganini
            # biladi — chegara o'zgartirilmaydi
            stmt = stmt.where(CallModel.started_at <= date_to)
    # ⚠️ Baho — IXTIYORIY bog'lanish. Sharti to'g'ridan-to'g'ri `WHERE` ga
    # tushsa, bahosiz qatorda u NULL beradi va `OUTER JOIN` amalda
    # `INNER JOIN` ga aylanadi: hali baholanmagan qo'ng'iroqlar eng keng
    # oraliqda ham jimgina yo'qoladi. Shuning uchun har bir shart
    # «yoki bahosi umuman yo'q» varianti bilan birga yuradi.
    if score_min is not None:
        stmt = stmt.where(or_(score.overall_score >= score_min, score.id.is_(None)))
    if score_max is not None:
        stmt = stmt.where(or_(score.overall_score <= score_max, score.id.is_(None)))
    if needs_review is not None:
        # Ro'yxatda bahosiz qo'ng'iroq `needs_review: false` bo'lib
        # ko'rsatiladi — filtr ham aynan shunday o'qishi kerak, aks holda
        # javob o'z-o'ziga zid bo'ladi
        stmt = stmt.where(func.coalesce(score.needs_review, false()).is_(needs_review))
    if call_type is not None:
        if call_type is CallTypeFilter.UNKNOWN:
            stmt = stmt.where(CallModel.call_type.is_(None))
        elif call_type is CallTypeFilter.NOT_SALES:
            # ⚠️ «!= sales» deb yozib bo'lmaydi: SQL da `NULL <> 'sales'`
            # NULL beradi va tasniflanmaganlar jimgina yo'qolardi. Ular
            # ham savdo emas — hali bilinmagani ularni savdo qilmaydi.
            stmt = stmt.where(
                or_(
                    CallModel.call_type.is_(None),
                    CallModel.call_type != CallType.SALES.value,
                )
            )
        else:
            stmt = stmt.where(CallModel.call_type == call_type.value)
    if search and search.strip():
        # Qidiruv bir nechta ustunni qamraydi: foydalanuvchi «Samarqand»
        # deb yozganda transkriptdan emas, hududdan topilishini kutadi
        needle = f"%{_ilike_ekranla(search.strip())}%"
        stmt = stmt.where(
            or_(
                CallModel.transcript.ilike(needle, escape="\\"),
                agent.full_name.ilike(needle, escape="\\"),
                agent.region.ilike(needle, escape="\\"),
                client.name.ilike(needle, escape="\\"),
                # Katalogda yo'q mijoz ham topilsin — ro'yxatda uning
                # nomi ko'rinib turadi, qidiruvda topilmasligi g'alati
                CallModel.client_name.ilike(needle, escape="\\"),
                CallModel.client_phone.ilike(needle, escape="\\"),
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    # Saralash ustuni oq ro'yxatdan olinadi — foydalanuvchi kiritgan matn
    # hech qachon to'g'ridan-to'g'ri SQL ga tushmaydi
    # Ro'yxatda ko'rsatiladigan mijoz nomi. Saralash AYNAN SHU ifoda
    # bo'yicha ketishi shart: `client.name` bo'yicha saralansa,
    # katalogda yo'q mijozlar (ekranda nomi bor bo'lsa ham) hammasi
    # NULL bo'lib oxiriga tushib qolardi.
    client_label = func.coalesce(client.name, CallModel.client_name)

    column = {
        SortField.DATE: CallModel.started_at,
        SortField.AGENT: agent.full_name,
        SortField.CLIENT: func.coalesce(client_label, CallModel.client_phone),
        SortField.DURATION: CallModel.duration_sec,
        SortField.SCORE: score.overall_score,
        # «Holat» ustuni qoidabuzarlik sonini ko'rsatadi — shuning uchun
        # saralash ham shu son bo'yicha, `needs_review` esa ikkilamchi mezon
        SortField.STATUS: func.coalesce(
            func.jsonb_array_length(score.red_flags), 0
        ),
    }[sort]

    direction = column.desc() if order is SortOrder.DESC else column.asc()
    # Bahosi yo'q qo'ng'iroqlar va ismsiz clientlar har doim oxirida tursin —
    # yo'nalish qanday bo'lishidan qat'i nazar
    ordering = [nullslast(direction)]
    if sort is SortField.STATUS:
        # Bir xil qoidabuzarlik sonida — tekshiruv kutayotganlari oldinda,
        # lekin yo'nalish teskari bo'lsa ular ham teskari tartibda
        review = score.needs_review
        ordering.append(
            nullslast(review.desc() if order is SortOrder.DESC else review.asc())
        )
    # Ikkilamchi mezon: bir xil qiymatli qatorlar sahifalar orasida
    # sakrab yurmasligi uchun barqaror tartib kerak
    if sort is not SortField.DATE:
        ordering.append(CallModel.started_at.desc())
    ordering.append(CallModel.id)

    rows = (
        await session.execute(
            stmt.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    return PaginatedCalls(
        items=[
            CallListItem(
                id=c.id,
                started_at=c.started_at,
                duration_sec=c.duration_sec,
                status=c.status.value,
                agent_id=a.id,
                agent_name=a.full_name,
                agent_color=a.color,
                # Katalog ustun turadi: u yerdagi nom tahrir qilingan
                # bo'lishi mumkin, MoyZvonki'niki esa nusxa
                client_name=(cl.name if cl else None) or c.client_name,
                client_phone=c.client_phone,
                call_type=c.call_type,
                score=s.overall_score if s else None,
                red_flag_count=len(s.red_flags or []) if s else 0,
                needs_review=s.needs_review if s else False,
            )
            for c, a, cl, s in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ══════════════════════════════════════════════════════════════
#  MoyZvonki sinxronizatsiyasi
#
#  Faqat METADATA va yozuv manzili ko'chiriladi. Audio baytlari bu
#  yerdan o'tmaydi va hech qayerga yozilmaydi.
# ══════════════════════════════════════════════════════════════


class SyncRequest(BaseModel):
    date_from: datetime = Field(description="Qaysi sanadan boshlab (UTC)")
    date_to: datetime | None = Field(default=None, description="Qaysi sanagacha")

    supervised: bool = Field(
        default=True,
        description=(
            "MoyZvonki `supervised=1` — API kalit egasi ko'ra oladigan BARCHA "
            "xodimlarning qo'ng'iroqlari. Deyarli har doim `true` bo'lishi "
            "kerak: `false` da faqat kalit egasining o'z qo'ng'iroqlari keladi. "
            "Qaysi xodimlar SAQLANISHINI `agent_ids` belgilaydi."
        ),
    )

    agent_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "FAQAT shu xodimlarning qo'ng'iroqlari bazaga yoziladi. "
            "Berilmasa — `external_id` si bor barcha xodimlarniki. "
            "⚠️ Filtrlash BIZNING tomonda: MoyZvonki `calls.list` da xodim "
            "bo'yicha parametr yo'q, shuning uchun sahifalar baribir to'liq "
            "o'qiladi, keraksizlari esa yozilmaydi."
        ),
    )

    max_calls: int = Field(default=20_000, ge=1, le=200_000)


class UnmatchedOwner(BaseModel):
    user_id: str | None
    user_account: str | None
    call_count: int
    label: str


class SyncResult(BaseModel):
    """Sinxronizatsiya hisoboti.

    `created` + `updated` = bazaga yozilgan qatorlar. Ikkinchi marta
    ishga tushirilsa `created` 0 bo'lishi kerak — idempotentlik shu.
    """

    date_from: datetime
    date_to: datetime | None
    pages: int
    fetched: int
    created: int
    updated: int
    skipped_no_agent: int
    skipped_not_selected: int = 0
    """Admin tanlamagan xodimga tegishli — xato emas, filtr natijasi."""
    skipped_no_recording: int
    """Audiosi yo'q — bazaga umuman yozilmadi (javobsiz qo'ng'iroq,
    muddati o'tgan yozuv). Bu ham xato emas, asosiy filtr natijasi."""
    truncated: bool
    unmatched: list[UnmatchedOwner]
    message: str


class SyncWindow(BaseModel):
    """Sinxronizatsiyada tanlash mumkin bo'lgan sana oralig'i.

    Chegara — qat'iy `SYNC_MAX_DAYS` kun (sababi konstanta yonida
    yozilgan). UI sana tanlagichini shu bilan cheklaydi, backend esa
    kelgan so'rovni shu bilan qisqartiradi — ya'ni chegara ikki joyda
    bir xil manbadan olinadi.
    """

    earliest: date
    """Tanlash mumkin bo'lgan eng eski kun."""
    days: int
    """Bugundan necha kun orqaga (= `SYNC_MAX_DAYS`)."""


async def _label_flags(
    session: DbSession, score: CallScoreModel
) -> list[dict[str, Any]]:
    """Bayroqlarga rubrikadagi yorliqni qo'shadi.

    ⚠️ Yorliq BAHO QO'YILGAN versiyadan olinadi, faol versiyadan emas.
    Sabab: qoida nomi keyinroq o'zgargan bo'lishi mumkin va o'sha yangi
    nomni eski bahoga yopishtirish tarixni buzardi — menejer «bu bayroq
    o'shanda boshqacha atalgan» deganini tekshira olmasdi.

    Yorliq topilmasa maydon QO'SHILMAYDI (kalit o'chirilgan bo'lishi
    mumkin) — interfeys o'shanda kalitning o'zini ko'rsatadi.
    """
    flags = list(score.red_flags or [])
    if not flags:
        return flags

    row = (
        await session.execute(
            select(RubricModel.red_flags).where(
                RubricModel.version == _version_number(score.rubric_version)
            )
        )
    ).scalar_one_or_none()

    labels = {
        str(item.get("type")): item.get("label")
        for item in (row or [])
        if item.get("label")
    }
    return [
        {**flag, "label": labels[flag["type"]]}
        if flag.get("type") in labels
        else dict(flag)
        for flag in flags
    ]


def _version_number(raw: str | None) -> int:
    """`"v3"` / `"3"` → `3`. Tanib bo'lmasa `-1` (hech nima topilmaydi).

    Ustun `VARCHAR(16)`, ya'ni shakli kafolatlanmagan. `int()` ni
    to'g'ridan-to'g'ri chaqirish g'alati qiymatda `ValueError` berib,
    butun qo'ng'iroq sahifasini 500 ga aylantirardi — yorliq kabi
    ikkilamchi narsa uchun bu qabul qilinmaydi.
    """
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return int(digits) if digits else -1


def _as_utc(moment: datetime) -> datetime:
    """Vaqt mintaqasi ko'rsatilmagan sanani UTC deb qabul qiladi.

    Pydantic mintaqasiz `datetime` ni ham qabul qiladi, uni mintaqali
    chegara bilan solishtirish esa `TypeError` beradi — ya'ni «Z» siz
    sana jo'natgan mijoz sinxronizatsiyani 500 bilan yiqitardi.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _earliest_allowed() -> datetime:
    """Ruxsat etilgan eng eski payt — kun boshidan (UTC).

    Kun boshiga tekislanadi: aks holda «45 kun» soatga bog'liq bo'lib,
    ertalab sinxronlagan admin kechqurun sinxronlaganidan boshqa oraliq
    olardi va nega ba'zi qo'ng'iroqlar tushmaganini tushunmasdi.
    """
    day = datetime.now(UTC).date() - timedelta(days=SYNC_MAX_DAYS)
    return datetime.combine(day, time.min, tzinfo=UTC)


@router.get(
    "/sync/window",
    response_model=SyncWindow,
    summary="Sinxronizatsiya uchun ruxsat etilgan sana oralig'i",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def sync_window() -> SyncWindow:
    """Sana tanlagich uchun chegara. MoyZvonki'ga so'rov YO'Q.

    Ilgari bu chegara MoyZvonki'dan har safar o'lchanardi (yozuvi bor
    eng eski kunni ikkilik qidiruv bilan topib). O'lchov ishlagan,
    lekin tarmoqqa bog'liq edi: MoyZvonki sekinlashsa «aniqlanmadi»
    qaytardi va o'shanda butun sana tanlovi ishonchsiz bo'lib turardi.
    Qat'iy chegara esa har doim bir xil javob beradi.
    """
    earliest = _earliest_allowed()
    return SyncWindow(earliest=earliest.date(), days=SYNC_MAX_DAYS)


@router.post(
    "/sync",
    response_model=SyncResult,
    summary="MoyZvonki'dan qo'ng'iroqlarni tortib olish",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def sync_calls(payload: SyncRequest, session: DbSession) -> SyncResult:
    """Sana oralig'idagi qo'ng'iroqlarni `calls` jadvaliga ko'chiradi.

    Faqat AUDIOSI BOR qo'ng'iroqlar saqlanadi — qolganlari baholanmaydi,
    demak ro'yxatda ham kerak emas.

    Qayta-qayta ishga tushirish xavfsiz: `external_id` (MoyZvonki
    `db_call_id`) bo'yicha UNIQUE upsert qilinadi.
    """
    # Chegara SERVER tomonida qo'yiladi, faqat tanlagichda emas: so'rov
    # to'g'ridan-to'g'ri (skript, eski oyna, keshlangan UI) kelishi
    # mumkin. Chegarasiz so'rov MoyZvonki'ning yuz minglab eski
    # yozuvini sahifalab o'qib, hech nima yozmasdan daqiqalab ishlardi.
    limit = _earliest_allowed()
    asked = _as_utc(payload.date_from)
    since = max(asked, limit)
    clamped = since > asked

    # Oraliqning OXIRI ham chegaradan oldin bo'lsa, ichida bitta ham
    # foydali kun yo'q. Bunda boshini qirqish oraliqni TESKARI qilardi
    # («3-iyuldan 2-martgacha») va javob «0 ta yangi» bo'lib chiqardi —
    # ya'ni admin ma'lumot yo'q deb o'ylardi, aslida so'rov noto'g'ri.
    # MoyZvonki'ga bejiz so'rov ham ketmaydi.
    until = _as_utc(payload.date_to) if payload.date_to else None
    if until is not None and until < limit:
        raise ValidationError(
            f"Tanlangan oraliq to'liq chegaradan tashqarida. "
            f"Sinxronizatsiya oxirgi {SYNC_MAX_DAYS} kun bilan cheklangan "
            f"— {limit:%d.%m.%Y} dan boshlab tanlang."
        )

    async with moizvonki_client(session) as client:
        report = await IngestService(session, client).run(
            since=since,
            until=until,
            supervised=payload.supervised,
            max_calls=payload.max_calls,
            agent_ids=payload.agent_ids,
        )

    if report.skipped_no_agent:
        names = ", ".join(row.label for row in report.unmatched[:5])
        message = (
            f"{report.created} ta yangi, {report.updated} ta yangilandi. "
            f"⚠️ {report.skipped_no_agent} ta qo'ng'iroq xodimga bog'lanmadi "
            f"— «Xodimlar» bo'limida MoyZvonki identifikatorini to'ldiring: "
            f"{names}"
        )
    else:
        message = (
            f"{report.created} ta yangi, {report.updated} ta yangilandi "
            f"({report.fetched} ta ko'rib chiqildi)"
        )

    if clamped:
        # Jim qisqartirish eng yomon variant: admin «1-martdan» deb
        # tanlab, «12 ta yangi» degan javob oladi va mart ma'lumoti
        # yo'q deb o'ylaydi. Aslida oraliq qisqartirilgan.
        message += (
            f". Oraliq {SYNC_MAX_DAYS} kunga qisqartirildi "
            f"({since:%d.%m.%Y} dan) — undan oldingi yozuvlar mavjud emas"
        )

    if report.skipped_no_recording:
        # Bu son hisobot kartochkasida ham bor, lekin xulosa qatorida
        # aytilmasa «nega 400 tadan 90 tasi keldi?» degan savol qoladi
        message += (
            f". {report.skipped_no_recording} tasida audio yo'q edi "
            "(javobsiz yoki muddati o'tgan) — ular olinmadi"
        )

    return SyncResult(
        date_from=report.since,
        date_to=report.until,
        pages=report.pages,
        fetched=report.fetched,
        created=report.created,
        updated=report.updated,
        skipped_no_agent=report.skipped_no_agent,
        skipped_not_selected=report.skipped_not_selected,
        skipped_no_recording=report.skipped_no_recording,
        truncated=report.truncated,
        unmatched=[
            UnmatchedOwner(
                user_id=row.user_id,
                user_account=row.user_account,
                call_count=row.call_count,
                label=row.label,
            )
            for row in report.unmatched
        ],
        message=message,
    )


@router.get(
    "/{call_id}",
    response_model=CallDetail,
    summary="Qo'ng'iroq tafsiloti",
    dependencies=[CanReadCalls],
)
async def get_call(call_id: UUID, session: DbSession, user: CurrentUser):
    call = await session.get(CallModel, call_id)
    if call is None:
        raise NotFoundError("Qo'ng'iroq topilmadi")

    if user.role == Role.SALES and call.agent_id != user.agent_id:
        raise ForbiddenError("Bu qo'ng'iroq sizga tegishli emas")

    agent = await session.get(AgentModel, call.agent_id)
    client = await session.get(ClientModel, call.client_id) if call.client_id else None
    score = (
        await session.execute(
            select(CallScoreModel).where(CallScoreModel.call_id == call_id)
        )
    ).scalar_one_or_none()

    return CallDetail(
        id=call.id,
        started_at=call.started_at,
        duration_sec=call.duration_sec,
        status=call.status.value,
        direction=call.direction.value,
        agent={
            "id": str(agent.id),
            "full_name": agent.full_name,
            "region": agent.region,
            "color": agent.color,
        },
        client=(
            {"id": str(client.id), "name": client.name, "shop_name": client.shop_name}
            if client
            else None
        ),
        client_name=(client.name if client else None) or call.client_name,
        client_phone=call.client_phone,
        call_type=call.call_type,
        call_type_reason=call.call_type_reason,
        call_type_confidence=(
            float(call.call_type_confidence)
            if call.call_type_confidence is not None
            else None
        ),
        transcript=call.transcript,
        score=(
            {
                "overall_score": score.overall_score,
                "blocks": score.blocks,
                # Har bayroqqa RUBRIKADAGI yorlig'i qo'shiladi.
                #
                # NEGA BACKENDDA. Bayroq turi — admin o'zi yaratgan kalit
                # bo'lishi mumkin (`shaxsiy_raqamga_ogdirish`), unga
                # tarjima fayli YO'Q. Frontend o'zi rubrikani so'ray
                # olmaydi: `rubric:read` savdo xodimida yo'q va so'rov
                # har bir qo'ng'iroq sahifasida 403 berardi. Yorliqni
                # backend qo'shsa, u barcha rollarda va qo'shimcha
                # so'rovsiz ko'rinadi.
                "red_flags": await _label_flags(session, score),
                "outcome_signal": score.outcome_signal,
                "sentiment": score.sentiment,
                "coaching_note": score.coaching_note,
                "confidence": score.confidence,
                "needs_review": score.needs_review,
                # Bayroqning SABABI bayroqning o'zi bilan birga yuboriladi —
                # busiz menejer «tekshiruv kerak» yozuvini ko'radi-yu, nega
                # kerakligini bilmaydi
                "review_reasons": score.review_reasons,
                "model": score.model,
                "rubric_version": score.rubric_version,
            }
            if score
            else None
        ),
    )


# ══════════════════════════════════════════════════════════════
#  Audio ko'prigi
#
#  🔒 Buzilmas qoida: call audiolari BIZNING diskda ham, bazada ham
#  saqlanmaydi. Bu endpoint — ko'prik: baytlar MoyZvonki'dan kelib
#  to'g'ridan-to'g'ri brauzerga o'tadi. Na fayl, na vaqtinchalik
#  papka, na `bytes` o'zgaruvchisiga to'liq yig'ish.
#
#  Shuning uchun ham MoyZvonki manzili frontendga BERILMAYDI —
#  unda avtorizatsiya ma'lumoti bo'lishi mumkin.
# ══════════════════════════════════════════════════════════════


@router.get(
    "/{call_id}/audio",
    summary="Qo'ng'iroq yozuvi (MoyZvonki'dan to'g'ridan-to'g'ri oqim)",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "To'liq yozuv"},
        206: {"content": {"audio/mpeg": {}}, "description": "Qism (Range)"},
        403: {"description": "Ruxsat yo'q yoki boshqa xodimning qo'ng'irog'i"},
        404: {"description": "Qo'ng'iroq yoki yozuv topilmadi"},
        416: {"description": "So'ralgan oraliq noto'g'ri"},
        502: {"description": "MoyZvonki javob bermadi yoki kalit noto'g'ri"},
        503: {"description": "MoyZvonki sozlanmagan"},
    },
    dependencies=[CanReadCalls],
)
async def stream_call_audio(
    call_id: UUID,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> StreamingResponse:
    call = await session.get(CallModel, call_id)
    if call is None:
        raise NotFoundError("Qo'ng'iroq topilmadi")

    # Mavjud qoida: SALES faqat o'zining qo'ng'irog'ini eshitadi
    if user.role == Role.SALES and call.agent_id != user.agent_id:
        raise ForbiddenError("Bu qo'ng'iroq sizga tegishli emas")

    if not call.audio_key:
        raise RecordingNotFoundError(
            "Bu qo'ng'iroqning yozuvi yo'q — javobsiz bo'lgan yoki "
            "MoyZvonki'da yozuv saqlash muddati o'tgan"
        )

    # `Range` MAJBURIY qo'llab-quvvatlanadi: busiz brauzer pleerida
    # 8 daqiqalik yozuvning 6-daqiqasiga o'tib bo'lmaydi.
    range_header = request.headers.get("range")

    stack = AsyncExitStack()
    try:
        client = await stack.enter_async_context(moizvonki_client(session))
        stream = await stack.enter_async_context(
            client.open_recording(call.audio_key, range_header=range_header)
        )
    except BaseException:
        await stack.aclose()
        raise

    headers: dict[str, str] = {
        # Seek ishlashi uchun brauzerga oraliq so'rash mumkinligini aytamiz
        "Accept-Ranges": stream.accept_ranges or "bytes",
        # Diskka tushmasin: brauzer ham keshlab qo'ymasin
        "Cache-Control": "private, no-store",
        "X-Audio-Source": "moizvonki-stream",
    }
    if stream.content_range:
        headers["Content-Range"] = stream.content_range
    if stream.content_length is not None:
        headers["Content-Length"] = str(stream.content_length)

    async def body():
        """Baytlarni bo'lak-bo'lak uzatadi — to'liq tana yig'ilmaydi."""
        try:
            async for chunk in stream.chunks:
                yield chunk
        finally:
            await stack.aclose()

    return StreamingResponse(
        body(),
        status_code=stream.status_code,
        media_type=stream.content_type,
        headers=headers,
    )
