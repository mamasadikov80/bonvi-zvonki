"""Mijozlar ro'yxati — QO'NG'IROQLARDAN yig'iladi.

⚠️ NEGA `clients` JADVALIDAN EMAS. Katalog bo'sh: unda 0 qator bor va
`calls.client_id` ning hech birida qiymat yo'q. Katalog boshqa vazifa
uchun tuzilgan — Telegram orqali so'rovnoma yuborish; unda hudud
majburiy va har notanish raqamni u yerga yozish katalogni
ifloslantirardi (`CallModel.client_name` izohiga qarang).

MoyZvonki esa HAR qo'ng'iroqda suhbatdoshning raqamini va (ko'pincha)
nomini beradi. Ya'ni mijoz haqidagi yagona ishonchli ma'lumot —
qo'ng'iroqlarning o'zi. Shuning uchun bu yerdagi «mijoz» — bitta
telefon raqami va u bilan bo'lgan barcha suhbatlar.

KALIT — RAQAMNING OXIRGI 9 TASI. Bir odam turli ko'rinishda kelishi
mumkin: «+998 90 123-45-67», «998901234567», «901234567». O'zbekistonda
oxirgi 9 raqam yagona, shuning uchun guruhlash aynan shu bo'yicha —
tizimda hamma joyda shunday (`moizvonki/application/ingest.py`,
`analytics/application/activity.py`). Qisqa ATS raqamlari (masalan
`700`) o'zicha kalit bo'ladi: ular 9 tadan qisqa va kesilmaydi.

ICHKI SUHBATLAR SUKUT BO'YICHA KIRMAYDI. Hamkasblar bilan gaplashuv
mijoz emas; `scope` bilan ular alohida ko'riladi. Filtr `call_type`
ustuniga tayanadi va u RAQAM bo'yicha aniqlanadi
(`calls/domain/routing.py`), ya'ni ishonchli.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Select, and_, distinct, func, nullslast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.scoring.infrastructure.models import CallScoreModel

#: Raqamning solishtiriladigan qismi — O'zbekistonda oxirgi 9 raqam
#: yagona. Tizimdagi boshqa joylar bilan bir xil bo'lishi SHART: kalit
#: farq qilsa, bir xil mijoz ikki bo'limda ikki xil ko'rinardi.
PHONE_TAIL = 9

#: Faqat raqamlar — formatlash va bo'shliqlar tashlab yuboriladi.
_DIGITS = func.regexp_replace(CallModel.client_phone, r"\D", "", "g")

#: Guruhlash kaliti.
_KEY = func.right(_DIGITS, PHONE_TAIL)


class ClientScope(StrEnum):
    """Kimlar ro'yxatga kiradi.

    `CLIENTS` — sukut bo'yicha: ichki suhbatlardan boshqa hammasi.
    «Savdo» deb qat'iy filtrlamaymiz: tasniflanmagan qatorlar
    (`call_type IS NULL`) ham bo'lishi mumkin va ular mijoz emas
    degani emas — hali aniqlanmagan. Ularni jimgina yashirish
    ro'yxatni to'liq emas qilardi.
    """

    CLIENTS = "clients"
    INTERNAL = "internal"
    ALL = "all"


class ClientSort(StrEnum):
    LAST_CALL = "last_call"
    CALLS = "calls"
    MISSED = "missed"
    TALK = "talk"
    SCORE = "score"
    NAME = "name"


@dataclass(slots=True)
class ClientFilter:
    """Ro'yxat va tafsilot uchun BIR XIL filtr.

    ⚠️ Ikkalasi bir xil oynani ko'rishi shart: tafsilotdagi «jami 12
    qo'ng'iroq» ro'yxatdagi son bilan mos kelmasa, foydalanuvchi
    qaysi biriga ishonishni bilmaydi.
    """

    since: datetime | None = None
    until: datetime | None = None
    agent_ids: list[UUID] | None = None
    regions: list[str] | None = None
    scope: ClientScope = ClientScope.CLIENTS
    search: str | None = None


@dataclass(slots=True)
class ClientRow:
    """Ro'yxatdagi bitta mijoz."""

    key: str
    name: str | None
    phone: str | None
    calls_total: int
    inbound: int
    outbound: int
    missed: int
    """Kiruvchi va javobsiz — «propushenniy». Faollik bo'limidagi
    ta'rif bilan bir xil."""
    talk_seconds: int
    first_call_at: datetime | None
    """`None` — tanlangan davrda bu mijoz bilan aloqa bo'lmagan.

    Ro'yxatda bunday qator YO'Q (guruh kamida bitta qo'ng'iroqdan
    tuziladi), lekin kartochkada bor: u yerda davr tanlanadi va bo'sh
    davr «mijoz topilmadi» degani EMAS."""
    last_call_at: datetime | None
    agent_count: int
    main_agent_id: UUID | None
    main_agent_name: str | None
    main_agent_color: str | None
    avg_score: float | None
    scored: int


@dataclass(slots=True)
class ClientPage:
    items: list[ClientRow]
    total: int
    page: int
    page_size: int


@dataclass(slots=True)
class ClientAgent:
    """Mijoz bilan gaplashgan xodim."""

    agent_id: UUID
    full_name: str
    color: str | None
    region: str | None
    calls: int
    last_call_at: datetime


@dataclass(slots=True)
class ClientCall:
    call_id: UUID
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


@dataclass(slots=True)
class ClientCallPage:
    items: list[ClientCall] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


def _ilike_escape(text: str) -> str:
    """`ILIKE` metabelgilarini oddiy belgiga aylantiradi.

    Foydalanuvchi `%` ni matn deb yozadi, shablon deb emas.
    Ekranlanmasa bitta `%` butun qidiruvni o'chirib yuborardi.
    """
    for sign in ("\\", "%", "_"):
        text = text.replace(sign, f"\\{sign}")
    return text


class ClientDirectory:
    """Qo'ng'iroqlardan yig'iladigan mijozlar ro'yxati."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Umumiy shartlar ───────────────────────────────────────

    def _scoped(self, stmt: Select, f: ClientFilter) -> Select:
        """Filtrlarni QO'NG'IROQ qatorlariga qo'yadi.

        ⚠️ Qidiruv bu yerda YO'Q va ataylab: u qatorlarni emas,
        MIJOZLARNI tanlaydi (pastdagi `_matching_keys`). Agar qidiruv
        shu yerga tushsa, «Ali» deb qidirganda faqat nomi yozilgan
        qo'ng'iroqlar sanalardi va mijozning jami soni kamayib
        ko'rinardi — qidiruv raqamni O'ZGARTIRMASLIGI kerak.
        """
        stmt = stmt.where(
            CallModel.client_phone.is_not(None),
            # Raqamsiz qator ham bor (masalan bo'sh satr) — u mijoz emas
            _DIGITS != "",
        )
        if f.since is not None:
            stmt = stmt.where(CallModel.started_at >= f.since)
        if f.until is not None:
            stmt = stmt.where(CallModel.started_at <= f.until)
        if f.agent_ids:
            stmt = stmt.where(CallModel.agent_id.in_(f.agent_ids))
        if f.regions:
            stmt = stmt.where(AgentModel.region.in_(f.regions))

        if f.scope is ClientScope.INTERNAL:
            stmt = stmt.where(CallModel.call_type == CallType.INTERNAL.value)
        elif f.scope is ClientScope.CLIENTS:
            # ⚠️ «!= internal» deb yozib bo'lmaydi: SQL da
            # `NULL <> 'internal'` NULL beradi va tasniflanmagan
            # qatorlar jimgina yo'qolardi.
            stmt = stmt.where(
                or_(
                    CallModel.call_type.is_(None),
                    CallModel.call_type != CallType.INTERNAL.value,
                )
            )
        return stmt

    def _matching_keys(self, f: ClientFilter) -> Select | None:
        """Qidiruvga mos MIJOZLAR kaliti.

        Nom bo'yicha ham, raqam bo'yicha ham. Bitta qo'ng'irog'ida
        nomi yozilgan bo'lsa yetarli: mijoz topilishi kerak, keyin
        uning HAMMA suhbati ko'rsatiladi.
        """
        text = (f.search or "").strip()
        if not text:
            return None

        conditions = [CallModel.client_name.ilike(f"%{_ilike_escape(text)}%", escape="\\")]
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            # Raqam istalgan formatda kiritilishi mumkin — solishtirish
            # faqat raqamlar bo'yicha: «90 123» ham topsin
            conditions.append(_DIGITS.like(f"%{digits}%"))

        stmt = select(_KEY).select_from(CallModel).join(
            AgentModel, AgentModel.id == CallModel.agent_id
        )
        return self._scoped(stmt, f).where(or_(*conditions)).distinct()

    def _aggregate(self, f: ClientFilter) -> Select:
        """Mijoz bo'yicha yig'ma — ro'yxatning o'zagi."""
        stmt = (
            select(
                _KEY.label("key"),
                # `mode()` — eng ko'p uchragan qiymat, NULL larni
                # sanamaydi. «Oxirgi nom» emas: MoyZvonki ba'zan nomni
                # umuman bermaydi va oxirgi qo'ng'iroq bo'yicha olsak
                # mijoz nomsiz bo'lib qolardi.
                func.mode().within_group(CallModel.client_name).label("name"),
                func.mode().within_group(CallModel.client_phone).label("phone"),
                # Asosiy xodim — eng ko'p gaplashgani. Ro'yxatda bitta
                # ism ko'rinadi, qolganlari «+N» bo'lib turadi.
                func.mode().within_group(CallModel.agent_id).label("main_agent_id"),
                func.count().label("calls_total"),
                func.count()
                .filter(CallModel.direction == CallDirection.INBOUND)
                .label("inbound"),
                func.count()
                .filter(CallModel.direction == CallDirection.OUTBOUND)
                .label("outbound"),
                func.count()
                .filter(
                    and_(
                        CallModel.direction == CallDirection.INBOUND,
                        CallModel.answered.is_(False),
                    )
                )
                .label("missed"),
                func.coalesce(func.sum(CallModel.duration_sec), 0).label("talk_seconds"),
                func.min(CallModel.started_at).label("first_call_at"),
                func.max(CallModel.started_at).label("last_call_at"),
                func.count(distinct(CallModel.agent_id)).label("agent_count"),
                func.avg(CallScoreModel.overall_score).label("avg_score"),
                func.count(CallScoreModel.overall_score).label("scored"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            # Baho IXTIYORIY: `INNER JOIN` bo'lsa baholanmagan
            # qo'ng'iroqlar sanoqdan tushib qolardi. `call_scores.call_id`
            # UNIQUE, ya'ni bog'lanish qatorlarni ko'paytirmaydi.
            .outerjoin(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .group_by(_KEY)
        )
        stmt = self._scoped(stmt, f)

        keys = self._matching_keys(f)
        if keys is not None:
            stmt = stmt.where(_KEY.in_(keys))
        return stmt

    # ── Ro'yxat ───────────────────────────────────────────────

    async def page(
        self,
        f: ClientFilter,
        *,
        page: int = 1,
        page_size: int = 20,
        sort: ClientSort = ClientSort.LAST_CALL,
        order: str = "desc",
    ) -> ClientPage:
        aggregate = self._aggregate(f).subquery()

        total = (
            await self._session.execute(
                select(func.count()).select_from(aggregate)
            )
        ).scalar_one()

        column = {
            ClientSort.LAST_CALL: aggregate.c.last_call_at,
            ClientSort.CALLS: aggregate.c.calls_total,
            ClientSort.MISSED: aggregate.c.missed,
            ClientSort.TALK: aggregate.c.talk_seconds,
            ClientSort.SCORE: aggregate.c.avg_score,
            # Nomsiz mijozlar oxirida tursin — `nullslast` pastda
            ClientSort.NAME: aggregate.c.name,
        }[sort]
        direction = column.desc() if order == "desc" else column.asc()

        rows = (
            await self._session.execute(
                select(aggregate)
                # Ikkilamchi mezon: bir xil qiymatli qatorlar sahifalar
                # orasida sakrab yurmasligi uchun barqaror tartib kerak
                .order_by(nullslast(direction), aggregate.c.key)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

        # Xodim nomi va rangi — faqat SHU sahifadagilar uchun. Yig'ma
        # so'rovga qo'shib bo'lmaydi: `mode()` natijasi guruhlashdan
        # KEYIN ma'lum bo'ladi.
        agents = await self._agents({row.main_agent_id for row in rows})

        return ClientPage(
            items=[
                ClientRow(
                    key=row.key,
                    name=row.name,
                    phone=row.phone,
                    calls_total=row.calls_total,
                    inbound=row.inbound,
                    outbound=row.outbound,
                    missed=row.missed,
                    talk_seconds=int(row.talk_seconds or 0),
                    first_call_at=row.first_call_at,
                    last_call_at=row.last_call_at,
                    agent_count=row.agent_count,
                    main_agent_id=row.main_agent_id,
                    main_agent_name=agents.get(row.main_agent_id, (None, None))[0],
                    main_agent_color=agents.get(row.main_agent_id, (None, None))[1],
                    avg_score=float(row.avg_score) if row.avg_score is not None else None,
                    scored=row.scored,
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def _agents(
        self, ids: set[UUID | None]
    ) -> dict[UUID, tuple[str, str | None]]:
        real = [i for i in ids if i is not None]
        if not real:
            return {}
        rows = (
            await self._session.execute(
                select(AgentModel.id, AgentModel.full_name, AgentModel.color).where(
                    AgentModel.id.in_(real)
                )
            )
        ).all()
        return {row.id: (row.full_name, row.color) for row in rows}

    # ── Bitta mijoz ───────────────────────────────────────────

    async def summary(self, key: str, f: ClientFilter) -> ClientRow | None:
        """Bitta mijozning yig'masi. `None` — bunday raqam yo'q.

        Qidiruv shartisiz: tafsilot sahifasiga kirilgandan keyin
        qidiruv matni ahamiyatsiz, mijoz esa allaqachon tanlangan.
        """
        one = ClientFilter(
            since=f.since,
            until=f.until,
            agent_ids=f.agent_ids,
            regions=f.regions,
            scope=f.scope,
        )
        aggregate = self._aggregate(one).where(_KEY == key).subquery()
        row = (await self._session.execute(select(aggregate))).first()

        if row is None:
            # ⚠️ TANLANGAN DAVRDA aloqa bo'lmagan bo'lishi mumkin — bu
            # «bunday mijoz yo'q» degani EMAS. Sanani olib tashlab
            # qayta qaraymiz: raqam umuman bo'lsa, kartochka ochiladi
            # va nollar ko'rsatiladi. Aks holda davrni toraytirgan
            # foydalanuvchi «mijoz topilmadi» degan xatoni ko'rardi.
            #
            # Xodim, hudud va `scope` shartlari SAQLANADI: savdo xodimi
            # o'zi gaplashmagan mijozning kartochkasini ocholmasligi
            # kerak.
            outside = self._aggregate(
                replace(one, since=None, until=None)
            ).where(_KEY == key).subquery()
            known = (await self._session.execute(select(outside))).first()
            if known is None:
                return None
            return ClientRow(
                key=known.key,
                name=known.name,
                phone=known.phone,
                calls_total=0,
                inbound=0,
                outbound=0,
                missed=0,
                talk_seconds=0,
                first_call_at=None,
                last_call_at=None,
                agent_count=0,
                main_agent_id=None,
                main_agent_name=None,
                main_agent_color=None,
                avg_score=None,
                scored=0,
            )

        agents = await self._agents({row.main_agent_id})
        return ClientRow(
            key=row.key,
            name=row.name,
            phone=row.phone,
            calls_total=row.calls_total,
            inbound=row.inbound,
            outbound=row.outbound,
            missed=row.missed,
            talk_seconds=int(row.talk_seconds or 0),
            first_call_at=row.first_call_at,
            last_call_at=row.last_call_at,
            agent_count=row.agent_count,
            main_agent_id=row.main_agent_id,
            main_agent_name=agents.get(row.main_agent_id, (None, None))[0],
            main_agent_color=agents.get(row.main_agent_id, (None, None))[1],
            avg_score=float(row.avg_score) if row.avg_score is not None else None,
            scored=row.scored,
        )

    async def agents_of(self, key: str, f: ClientFilter) -> list[ClientAgent]:
        """Mijoz bilan KIM gaplashgan — ko'pdan kamga.

        Bitta mijoz bir necha xodim bilan gaplashgan bo'lishi mumkin
        (almashinuv, ta'til, boshqa hududga o'tish) va rahbarning
        birinchi savoli aynan shu bo'ladi.
        """
        stmt = (
            select(
                CallModel.agent_id,
                AgentModel.full_name,
                AgentModel.color,
                AgentModel.region,
                func.count().label("calls"),
                func.max(CallModel.started_at).label("last_call_at"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .where(_KEY == key)
            .group_by(
                CallModel.agent_id,
                AgentModel.full_name,
                AgentModel.color,
                AgentModel.region,
            )
            .order_by(func.count().desc(), func.max(CallModel.started_at).desc())
        )
        rows = (await self._session.execute(self._scoped(stmt, f))).all()
        return [
            ClientAgent(
                agent_id=row.agent_id,
                full_name=row.full_name,
                color=row.color,
                region=row.region,
                calls=row.calls,
                last_call_at=row.last_call_at,
            )
            for row in rows
        ]

    async def calls(
        self, key: str, f: ClientFilter, *, page: int = 1, page_size: int = 50
    ) -> ClientCallPage:
        """Mijoz bilan bo'lgan barcha suhbatlar — yangisidan eskisiga."""
        stmt = (
            select(CallModel, AgentModel, CallScoreModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .outerjoin(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .where(_KEY == key)
        )
        stmt = self._scoped(stmt, f)

        total = (
            await self._session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                stmt.order_by(CallModel.started_at.desc(), CallModel.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

        return ClientCallPage(
            items=[
                ClientCall(
                    call_id=call.id,
                    started_at=call.started_at,
                    duration_sec=call.duration_sec,
                    direction=call.direction.value,
                    answered=call.answered,
                    status=call.status.value,
                    call_type=call.call_type,
                    agent_id=agent.id,
                    agent_name=agent.full_name,
                    agent_color=agent.color,
                    score=score.overall_score if score else None,
                    red_flag_count=len(score.red_flags or []) if score else 0,
                    needs_review=score.needs_review if score else False,
                )
                for call, agent, score in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
