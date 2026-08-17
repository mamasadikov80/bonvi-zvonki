"""Savdo xodimi servisi — CRUD va ishdan bo'shatish oqibatlari.

Eng muhim qoida shu yerda: xodim faolsizlantirilganda unga biriktirilgan
guruhlar avtomatik bo'shatiladi va ularning navbatdagi so'rovnomalari
bekor qilinadi. Aks holda bot bir necha soniyadan keyin guruhga so'rovnoma
tashlab, bahoni kompaniyadan ketgan odamga yozib qo'yardi.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.agents.domain.entities import PHONE_MATCH_DIGITS, normalize_phone
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.groups.application.agent_regions import (
    agent_region_names,
    load_regions_by_agent,
)
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.surveys.domain.entities import SurveyStatus
from src.modules.surveys.infrastructure.models import SurveyModel


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Ichki yordamchilar ────────────────────────────────────

    async def _get(self, agent_id: UUID) -> AgentModel:
        agent = await self._session.get(AgentModel, agent_id)
        if agent is None:
            raise NotFoundError("Xodim topilmadi")
        return agent

    async def _bound_counts(
        self, agent_ids: list[UUID] | None = None
    ) -> dict[UUID, int]:
        """Xodim → biriktirilgan guruhlar soni.

        Bitta `GROUP BY` — ro'yxat endpointida har qator uchun alohida
        `COUNT` qilinmaydi (N+1 bo'lardi).
        """
        stmt = (
            select(TelegramGroupModel.agent_id, func.count(TelegramGroupModel.id))
            .where(TelegramGroupModel.agent_id.isnot(None))
            .group_by(TelegramGroupModel.agent_id)
        )
        if agent_ids is not None:
            if not agent_ids:
                return {}
            stmt = stmt.where(TelegramGroupModel.agent_id.in_(agent_ids))
        rows = (await self._session.execute(stmt)).all()
        return {agent_id: count for agent_id, count in rows}

    @staticmethod
    def _to_dict(
        agent: AgentModel,
        *,
        bound_groups: int = 0,
        freed_groups: int | None = None,
        regions: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": agent.id,
            "full_name": agent.full_name,
            # ⚠️ IKKI XIL HUDUD, ikkalasi ham kerak:
            #   `region`  — xodim YASHAYDIGAN joy (kartochkadagi maydon)
            #   `regions` — u XIZMAT KO'RSATADIGAN hududlar, biriktirilgan
            #               guruhlaridan yig'iladi (`agent_regions.py`)
            # Ilgari faqat birinchisi qaytarilardi va profil sahifasi
            # «Toshkent» deb turardi, guruhlar bo'limi esa o'sha xodimni
            # «Samarqand» da ko'rsatardi. Endi ikkala ekran ham `regions`
            # ni ko'rsatadi — manba bitta.
            "region": agent.region,
            "regions": regions or [],
            "phone": agent.phone,
            "external_id": agent.external_id,
            "hired_at": agent.hired_at,
            "is_active": agent.is_active,
            "color": agent.color,
            "avatar_url": agent.avatar_url,
            "telegram_user_id": agent.telegram_user_id,
            "telegram_username": agent.telegram_username,
            "enrolled_at": agent.enrolled_at,
            "archived_at": agent.archived_at,
            "bound_groups": bound_groups,
            "freed_groups": freed_groups,
        }

    async def serialize(
        self, agent: AgentModel, *, freed_groups: int | None = None
    ) -> dict[str, Any]:
        """Bitta xodim — guruhlar soni va xizmat hududlari bilan."""
        bound = (
            await self._session.execute(
                select(func.count(TelegramGroupModel.id)).where(
                    TelegramGroupModel.agent_id == agent.id
                )
            )
        ).scalar_one()
        regions = sorted(
            (await self._session.execute(agent_region_names(agent.id))).scalars()
        )
        return self._to_dict(
            agent,
            bound_groups=bound,
            freed_groups=freed_groups,
            regions=regions,
        )

    # ── O'qish ────────────────────────────────────────────────

    async def list_agents(
        self,
        include_inactive: bool = False,
        search: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = select(AgentModel).order_by(AgentModel.full_name)
        # Arxivlangan xodim `include_inactive` bilan ham CHIQMAYDI: u
        # «ishdan bo'shagan» emas, «tizimdan olib tashlangan». Uni
        # ko'rish uchun ataylab so'rash kerak.
        if not include_archived:
            stmt = stmt.where(AgentModel.archived_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(AgentModel.is_active.is_(True))
        if search and search.strip():
            # Ism yoki hudud bo'yicha. `ilike` — katta-kichik harfga qaramaydi,
            # `%` ikki tomonda — so'zning o'rtasidan ham topadi
            needle = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AgentModel.full_name.ilike(needle),
                    AgentModel.region.ilike(needle),
                )
            )
        agents = list((await self._session.execute(stmt)).scalars())
        ids = [a.id for a in agents]
        counts = await self._bound_counts(ids)
        # Bitta `GROUP BY` — har xodim uchun alohida so'rov emas
        regions = await load_regions_by_agent(self._session, ids)
        return [
            self._to_dict(
                agent,
                bound_groups=counts.get(agent.id, 0),
                regions=regions.get(agent.id, []),
            )
            for agent in agents
        ]

    async def get_one(self, agent_id: UUID) -> dict[str, Any]:
        return await self.serialize(await self._get(agent_id))

    # ── Telegram ro'yxatdan o'tishi ───────────────────────────

    async def find_by_phone(self, phone: str | None) -> AgentModel | None:
        """Raqam bo'yicha xodimni topadi — oxirgi 9 raqam bo'yicha.

        Solishtirish BAZADA bajariladi: 1000 ta xodim bo'lganda ham
        hammasini Python'ga tortib normallashtirish keraksiz. Postgres
        tomonida ham aynan shu qoida — `regexp_replace` bilan faqat
        raqamlar qoldiriladi, keyin `right(..., 9)`.

        Faqat FAOL xodim topiladi: ishdan ketgan odam botga kontakt
        yuborsa uning guruhlari qayta tirilib ketmasligi kerak.
        """
        key = normalize_phone(phone)
        if key is None:
            return None

        digits = func.regexp_replace(AgentModel.phone, "[^0-9]", "", "g")
        return (
            await self._session.execute(
                select(AgentModel)
                .where(
                    AgentModel.is_active.is_(True),
                    AgentModel.phone.isnot(None),
                    func.length(digits) >= PHONE_MATCH_DIGITS,
                    func.right(digits, cast(literal(PHONE_MATCH_DIGITS), Integer))
                    == key,
                )
                # Bir xil raqamli ikkita xodim bo'lib qolsa — natija
                # tasodifiy emas, doim bir xil bo'lsin
                .order_by(AgentModel.created_at, AgentModel.id)
                .limit(1)
            )
        ).scalars().first()

    async def enroll(
        self,
        phone: str,
        telegram_user_id: int,
        telegram_username: str | None = None,
    ) -> dict[str, Any]:
        """Xodim botga kontaktini yubordi — Telegram ID sini yozib qo'yamiz.

        Bu butun avtomatikaning kalitidir: shundan keyin bot guruhda
        ko'rgan `user_id` ni backend xodimga aylantira oladi va 1000 ta
        guruh o'zi biriktiriladi.

        Bunday raqamli xodim bo'lmasa — 200 va `matched: false`. XATO
        EMAS: bu oddiy holat (mijoz ham botni ochib raqam yuborishi
        mumkin), va bot foydalanuvchiga o'zbekcha tushuntirish beradi.
        """
        agent = await self.find_by_phone(phone)
        if agent is None:
            return {"matched": False}

        # Shu Telegram akkaunti avval BOSHQA xodimga bog'langan bo'lsa —
        # bo'shatamiz. Ustunda UNIQUE bor, tozalamasak `IntegrityError`
        # chiqib, xodim qayta ro'yxatdan o'ta olmasdi.
        await self._session.execute(
            update(AgentModel)
            .where(
                AgentModel.telegram_user_id == telegram_user_id,
                AgentModel.id != agent.id,
            )
            .values(telegram_user_id=None, telegram_username=None, enrolled_at=None)
        )

        agent.telegram_user_id = telegram_user_id
        agent.telegram_username = telegram_username
        agent.enrolled_at = datetime.now(UTC)
        await self._session.flush()

        bound_groups = (
            await self._session.execute(
                select(func.count(TelegramGroupModel.id)).where(
                    TelegramGroupModel.agent_id == agent.id
                )
            )
        ).scalar_one()

        return {
            "matched": True,
            "agent_id": agent.id,
            "full_name": agent.full_name,
            "bound_groups": bound_groups,
        }

    # ── Yozish ────────────────────────────────────────────────

    async def create(self, fields: dict[str, Any]) -> dict[str, Any]:
        agent = AgentModel(**fields)
        self._session.add(agent)
        await self._session.flush()
        return await self.serialize(agent)

    async def update(self, agent_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
        """Xodimni tahrirlaydi; faolsizlantirilsa guruhlarini bo'shatadi."""
        agent = await self._get(agent_id)
        was_active = agent.is_active

        for key, value in fields.items():
            setattr(agent, key, value)

        freed_groups = 0
        if was_active and not agent.is_active:
            freed_groups = await self._release_groups(agent.id)

        # Xodim QAYTA faollashtirilganda guruhlar avtomatik qaytarilmaydi.
        # Bu ataylab: kim qaysi guruhni oladi — adminning qarori, bo'shagan
        # guruhlar shu orada boshqa xodimga berilgan bo'lishi mumkin.
        # Simmetriya "chiroyli" ko'rinadi, lekin u adminning qarorini
        # jimgina bekor qilardi.

        await self._session.flush()
        return await self.serialize(agent, freed_groups=freed_groups)

    async def _release_groups(self, agent_id: UUID) -> int:
        """Xodim ishdan ketdi: guruhlarini bo'shatadi, navbatni bekor qiladi.

        Qaytaradi: bo'shatilgan guruhlar soni.
        """
        group_ids = list(
            (
                await self._session.execute(
                    select(TelegramGroupModel.id).where(
                        TelegramGroupModel.agent_id == agent_id
                    )
                )
            ).scalars()
        )
        if not group_ids:
            return 0

        # 1) Navbatdagi (`pending`) so'rovnomalar bekor qilinadi — bot ularni
        #    60 soniyada olib, guruhga tashlab yuborardi va baho ketgan
        #    xodimga yozilardi. `sent` bo'lganlar va mavjud javoblar
        #    TEGILMAYDI: ular haqiqiy tarix, uni qayta yozib bo'lmaydi.
        await self._session.execute(
            update(SurveyModel)
            .where(
                SurveyModel.group_id.in_(group_ids),
                SurveyModel.status == SurveyStatus.PENDING,
            )
            .values(status=SurveyStatus.EXPIRED)
        )

        # 2) Guruhlar bo'shatiladi. `region` SAQLANADI — hudud odamga emas,
        #    hududga tegishli; uni tozalash admindan qayta kiritishni talab
        #    qilardi. `bound_at` esa tushiriladi: biriktirish endi yo'q.
        await self._session.execute(
            update(TelegramGroupModel)
            .where(TelegramGroupModel.agent_id == agent_id)
            .values(agent_id=None, bound_at=None)
        )
        return len(group_ids)
