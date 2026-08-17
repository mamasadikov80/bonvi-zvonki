"""Guruh servisi — ro'yxatga olish, biriktirish va so'rovnoma yaratish.

Ikki xil chaqiruvchi bor:
  • admin panel (JWT) — ro'yxat, tahrirlash, so'rovnoma yaratish
  • bot (`X-Internal-Token`) — guruhni ro'yxatga olish, navbatni olish

Ikkalasi ham shu servisdan o'tadi, shuning uchun qoidalar bitta joyda:
"biriktirilmagan guruhga so'rovnoma yuborilmaydi" degan shart router'da
ikki marta yozilmaydi.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.groups.application.agent_regions import (
    agent_region_names,
    load_regions_by_agent,
)
from src.modules.groups.domain.entities import (
    GONE_STATUSES,
    BindSource,
    BotStatus,
    suggest_region,
)
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.infrastructure.models import RegionModel
from src.modules.surveys.application.services import (
    resolve_message_ttl_hours,
    resolve_period_days,
    resolve_suppression_days,
    resolve_survey_enabled,
)
from src.modules.surveys.domain.entities import (
    SURVEY_TOKEN_TTL_DAYS,
    SurveyChannel,
    SurveyStatus,
    new_survey_token,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel


class GroupService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._regions: list[str] | None = None

    # ── Ichki yordamchilar ────────────────────────────────────

    async def _region_names(self) -> list[str]:
        """Bazadagi hudud nomlari — hudud taxmini uchun.

        Bir so'rov ichida bir marta o'qiladi: ro'yxat sahifasida
        `_serialize` har guruh uchun chaqiriladi, har safar bazaga
        borish esa keraksiz.
        """
        if self._regions is None:
            rows = await self._session.execute(select(RegionModel.name))
            self._regions = list(rows.scalars())
        return self._regions

    async def _get(self, group_id: UUID) -> TelegramGroupModel:
        group = await self._session.get(TelegramGroupModel, group_id)
        if group is None:
            raise NotFoundError("Guruh topilmadi")
        return group

    async def _regions_by_agent(
        self, agent_ids: list[UUID] | None = None
    ) -> dict[UUID, list[str]]:
        """Xodim → u xizmat ko'rsatadigan hududlar.

        Qoida `application/agent_regions.py` da — YAGONA joyda. Ilgari
        u shu yerda alohida yozilgan edi va xodim profilidagi hudud
        bilan mos kelmasdi.
        """
        return await load_regions_by_agent(self._session, agent_ids)

    async def _stats_for(
        self, group_ids: list[UUID]
    ) -> tuple[dict[UUID, int], dict[UUID, int]]:
        """Sahifadagi guruhlar uchun so'rovnoma va javob sonlari.

        Faqat KO'RSATILAYOTGAN 50 ta guruh bo'yicha hisoblanadi. Ilgari
        bu ikkita `GROUP BY` butun `surveys` jadvali ustidan ketardi va
        1000 ta guruhda javob og'irlashardi.
        """
        if not group_ids:
            return {}, {}

        surveys = {
            group_id: count
            for group_id, count in (
                await self._session.execute(
                    select(SurveyModel.group_id, func.count(SurveyModel.id))
                    .where(SurveyModel.group_id.in_(group_ids))
                    .group_by(SurveyModel.group_id)
                )
            ).all()
        }
        responses = {
            group_id: count
            for group_id, count in (
                await self._session.execute(
                    select(SurveyModel.group_id, func.count(SurveyResponseModel.id))
                    .join(
                        SurveyResponseModel,
                        SurveyResponseModel.survey_id == SurveyModel.id,
                    )
                    .where(SurveyModel.group_id.in_(group_ids))
                    .group_by(SurveyModel.group_id)
                )
            ).all()
        }
        return surveys, responses

    # ── Ro'yxat (admin panel) ─────────────────────────────────

    async def list_groups(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        agent_id: UUID | None = None,
        region: str | None = None,
        has_region: bool | None = None,
        has_agent: bool | None = None,
        search: str | None = None,
        include_inactive: bool = False,
    ) -> dict[str, Any]:
        """Sahifalangan guruhlar ro'yxati.

        ⚠️ **Sahifalash majburiy.** Guruhlar soni ~1000 (har mijozga
        alohida guruh), hammasini bitta javobda qaytarish — bir necha
        megabaytlik JSON va sekin sahifa. Shuning uchun bu metod
        `{"items", "total", "page", "page_size"}` qaytaradi.

        So'rovlar soni sahifa hajmiga bog'liq EMAS: sanash, sahifa,
        statistika (2 ta), xodim hududlari, hudud nomlari — jami 6 ta.
        """
        def scoped(stmt: Select) -> Select:
            if not include_inactive:
                stmt = stmt.where(TelegramGroupModel.is_active.is_(True))
            if agent_id is not None:
                stmt = stmt.where(TelegramGroupModel.agent_id == agent_id)
            if region:
                stmt = stmt.where(TelegramGroupModel.region == region)
            if has_region is True:
                stmt = stmt.where(TelegramGroupModel.region.isnot(None))
            elif has_region is False:
                stmt = stmt.where(TelegramGroupModel.region.is_(None))
            # `agent_id` UUID bo'lgani uchun u orqali "xodimi yo'q" ni
            # so'rab bo'lmaydi — daraxtdagi «Xodimi aniqlanmagan»
            # to'plami uchun alohida bayroq kerak
            if has_agent is True:
                stmt = stmt.where(TelegramGroupModel.agent_id.isnot(None))
            elif has_agent is False:
                stmt = stmt.where(TelegramGroupModel.agent_id.is_(None))
            if search and search.strip():
                needle = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(
                        TelegramGroupModel.title.ilike(needle),
                        AgentModel.full_name.ilike(needle),
                    )
                )
            return stmt

        # Sanash ham `AgentModel` ga LEFT JOIN qiladi — `search` xodim
        # ismi bo'yicha ham qidiradi, aks holda `total` sahifadagi
        # qatorlar soniga mos kelmasdi.
        total = (
            await self._session.execute(
                scoped(
                    select(func.count(TelegramGroupModel.id)).outerjoin(
                        AgentModel, AgentModel.id == TelegramGroupModel.agent_id
                    )
                )
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                scoped(
                    select(TelegramGroupModel, AgentModel).outerjoin(
                        AgentModel, AgentModel.id == TelegramGroupModel.agent_id
                    )
                )
                # `id` — barqaror ikkinchi mezon: bir xil nomli guruhlar
                # sahifalar orasida sakrab yurmasin
                .order_by(TelegramGroupModel.title, TelegramGroupModel.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()

        groups = [group for group, _ in rows]
        survey_counts, response_counts = await self._stats_for([g.id for g in groups])
        regions_by_agent = await self._regions_by_agent(
            [g.agent_id for g in groups if g.agent_id is not None]
        )
        known = await self._region_names()

        return {
            "items": [
                self._to_dict(
                    group,
                    agent,
                    survey_count=survey_counts.get(group.id, 0),
                    response_count=response_counts.get(group.id, 0),
                    regions=regions_by_agent.get(group.agent_id, []) if agent else [],
                    known=known,
                )
                for group, agent in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── Daraxt: xodim → hudud → guruhlar ──────────────────────

    async def tree(self) -> dict[str, Any]:
        """Panel uchun daraxt: xodim → hudud → guruhlar soni.

        ⚠️ **N+1 YO'Q va bo'lmasligi kerak.** Xodimlar bo'yicha aylanib
        har biriga so'rov yuborish — 15 xodimda 30 ta so'rov, 100 xodimda
        200 ta. Bu yerda hammasi TO'RTTA yig'ma so'rov bilan olinadi va
        bu son xodimlar/guruhlar soniga umuman bog'liq emas:

          1) faol xodimlar ro'yxati
          2) guruhlar soni — `GROUP BY agent_id, region`
          3) javoblar soni — `GROUP BY agent_id, region`
          4) xodimi aniqlanmagan guruhlar soni

        `region: null` tuguni — «hali ishga tushmagan» guruhlar: xodim
        aniqlangan, lekin hudud yo'q. Ular so'rovnoma OLMAYDI (buni
        `_structural_block` ta'minlaydi), admin daraxtda ko'rib ularga
        hudud tayinlaydi yoki keraksiz deb qoldirib ketadi.
        """
        agents = (
            await self._session.execute(
                select(AgentModel)
                .where(AgentModel.is_active.is_(True))
                .order_by(AgentModel.full_name)
            )
        ).scalars().all()

        group_rows = (
            await self._session.execute(
                select(
                    TelegramGroupModel.agent_id,
                    TelegramGroupModel.region,
                    func.count(TelegramGroupModel.id),
                )
                .where(
                    TelegramGroupModel.agent_id.isnot(None),
                    TelegramGroupModel.is_active.is_(True),
                )
                .group_by(TelegramGroupModel.agent_id, TelegramGroupModel.region)
            )
        ).all()

        response_rows = (
            await self._session.execute(
                select(
                    TelegramGroupModel.agent_id,
                    TelegramGroupModel.region,
                    func.count(SurveyResponseModel.id),
                )
                .join(SurveyModel, SurveyModel.group_id == TelegramGroupModel.id)
                .join(
                    SurveyResponseModel,
                    SurveyResponseModel.survey_id == SurveyModel.id,
                )
                .where(
                    TelegramGroupModel.agent_id.isnot(None),
                    TelegramGroupModel.is_active.is_(True),
                )
                .group_by(TelegramGroupModel.agent_id, TelegramGroupModel.region)
            )
        ).all()

        unassigned = (
            await self._session.execute(
                select(func.count(TelegramGroupModel.id)).where(
                    TelegramGroupModel.agent_id.is_(None),
                    TelegramGroupModel.is_active.is_(True),
                )
            )
        ).scalar_one()

        groups_by_agent: dict[UUID, dict[str | None, int]] = {}
        for agent_id, region, count in group_rows:
            groups_by_agent.setdefault(agent_id, {})[region] = count
        responses_by_agent: dict[UUID, dict[str | None, int]] = {}
        for agent_id, region, count in response_rows:
            responses_by_agent.setdefault(agent_id, {})[region] = count

        items = []
        for agent in agents:
            buckets = groups_by_agent.get(agent.id, {})
            responses = responses_by_agent.get(agent.id, {})
            # Nomli hududlar alifbo bo'yicha, hududsiz tugun ESA ENG OXIRIDA:
            # u «bajarilishi kerak» ro'yxati, ro'yxat boshida turib
            # haqiqiy hududlarni pastga surib yuborishi kerak emas
            named = sorted(r for r in buckets if r is not None)
            ordered: list[str | None] = [*named]
            if None in buckets:
                ordered.append(None)

            items.append(
                {
                    "agent_id": agent.id,
                    "full_name": agent.full_name,
                    "color": agent.color,
                    "avatar_url": agent.avatar_url,
                    "enrolled": agent.telegram_user_id is not None,
                    "regions": [
                        {
                            "region": region,
                            "group_count": buckets[region],
                            "response_count": responses.get(region, 0),
                        }
                        for region in ordered
                    ],
                    "group_count": sum(buckets.values()),
                }
            )

        return {"agents": items, "unassigned": {"group_count": unassigned}}

    def _to_dict(
        self,
        group: TelegramGroupModel,
        agent: AgentModel | None,
        *,
        survey_count: int = 0,
        response_count: int = 0,
        regions: list[str] | None = None,
        known: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": group.id,
            "chat_id": group.chat_id,
            "title": group.title,
            "agent_id": group.agent_id,
            "agent_name": agent.full_name if agent else None,
            "agent_color": agent.color if agent else None,
            "region": group.region,
            # Hudud biriktirilgan bo'lsa taxmin qilinmaydi — admin qarori ustun
            "suggested_region": (
                None if group.region else suggest_region(group.title, known)
            ),
            "regions": regions or [],
            "member_count": group.member_count,
            "is_active": group.is_active,
            "bound_by": group.bound_by,
            "bot_status": group.bot_status,
            "bound_at": group.bound_at,
            "last_survey_at": group.last_survey_at,
            "survey_count": survey_count,
            "response_count": response_count,
        }

    async def get_one(self, group_id: UUID) -> dict[str, Any]:
        """Bitta guruh — ro'yxatdagi qator bilan BIR XIL shaklda.

        Statistika ham hisoblanadi: `PATCH` javobini frontend ro'yxatdagi
        qatorning o'rniga qo'yadi, nol chiqib qolsa raqamlar "yo'qolgandek"
        ko'rinardi.
        """
        group = await self._get(group_id)
        agent = (
            await self._session.get(AgentModel, group.agent_id)
            if group.agent_id
            else None
        )
        regions_by_agent = await self._regions_by_agent()

        survey_count = (
            await self._session.execute(
                select(func.count(SurveyModel.id)).where(
                    SurveyModel.group_id == group.id
                )
            )
        ).scalar_one()
        response_count = (
            await self._session.execute(
                select(func.count(SurveyResponseModel.id))
                .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
                .where(SurveyModel.group_id == group.id)
            )
        ).scalar_one()

        return self._to_dict(
            group,
            agent,
            survey_count=survey_count,
            response_count=response_count,
            regions=regions_by_agent.get(group.agent_id, []) if agent else [],
            known=await self._region_names(),
        )

    # ── Tahrirlash ────────────────────────────────────────────

    # Odam qo'lda o'zgartirganda `bound_by="manual"` qo'yiladigan maydonlar
    _BINDING_FIELDS = ("agent_id", "region")

    def _apply(self, group: TelegramGroupModel, fields: dict[str, Any]) -> None:
        """Maydonlarni yozadi va `bound_at` / `bound_by` ni yangilaydi.

        ⚠️ `fields` ichida kalit BOR-YO'QLIGI muhim, qiymati emas.
        `{"region": None}` — «hududni bo'shat» degan ANIQ buyruq
        (admin guruhni keraksiz deb belgilamoqda), `{}` esa — «hududga
        tegilmasin». Router bu farqni `exclude_unset=True` bilan
        saqlaydi; yo'qotilsa admin hech qachon hududni bo'shata olmasdi.
        """
        for key, value in fields.items():
            setattr(group, key, value)

        # Biriktirishga oid maydon qo'lda o'zgartirildi → bu ODAM qarori.
        # Avtomatika bundan keyin bu guruhga tegmaydi.
        if any(key in fields for key in self._BINDING_FIELDS):
            group.bound_by = BindSource.MANUAL.value

        # Hudud — ishchi guruh belgisi. Xodim ham, hudud ham to'lgandagina
        # guruh so'rovnomaga tayyor.
        bound = group.agent_id is not None and bool(group.region)
        if bound and group.bound_at is None:
            group.bound_at = datetime.now(UTC)
        elif not bound:
            group.bound_at = None

    @staticmethod
    def _clean_region(value: Any) -> str | None:
        """`""` va `"  "` → `None`. Bo'sh matn hudud emas, uni saqlab
        qo'ysak guruh «hududli» ko'rinib, lekin ishlamay qolardi."""
        if value is None:
            return None
        region = str(value).strip()
        return region or None

    async def update(
        self,
        group_id: UUID,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Xodim / hudud / faollikni o'zgartiradi (admin qo'lda).

        `region: null` — guruhni «keraksiz» deb belgilash. Bunday guruh
        xodimga biriktirilgan holida turaveradi, lekin so'rovnoma
        olmaydi: `_structural_block()` uni rad etadi.
        """
        group = await self._get(group_id)

        if fields.get("agent_id") is not None:
            agent = await self._session.get(AgentModel, fields["agent_id"])
            if agent is None:
                raise NotFoundError("Savdo xodimi topilmadi")

        if "region" in fields:
            fields["region"] = self._clean_region(fields["region"])

        self._apply(group, fields)
        await self._session.flush()
        return await self.get_one(group.id)

    async def bulk_update(
        self, group_ids: list[UUID], fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Bir nechta guruhni birdaniga o'zgartiradi.

        Kerak, chunki guruhlar ~1000 ta: «bu 40 tasi keraksiz» degan
        qarorni bittalab 40 marta bosib bajarish — ishlab bo'lmaydigan
        interfeys. Ko'p ishlatiladigan holat aynan
        `{"region": null}` — bir yo'la keraksiz deb belgilash.

        `update()` bilan bir xil qoidalardan o'tadi (`bound_by="manual"`,
        `bound_at`), shuning uchun ORM obyektlari aylanadi —
        `UPDATE ... WHERE id IN` emas. 200 tagacha cheklangan.
        """
        if not group_ids:
            return {"updated": 0}
        if "agent_id" in fields and fields["agent_id"] is not None:
            if await self._session.get(AgentModel, fields["agent_id"]) is None:
                raise NotFoundError("Savdo xodimi topilmadi")
        if "region" in fields:
            fields["region"] = self._clean_region(fields["region"])

        groups = list(
            (
                await self._session.execute(
                    select(TelegramGroupModel).where(
                        TelegramGroupModel.id.in_(group_ids)
                    )
                )
            ).scalars()
        )
        if not groups:
            raise NotFoundError("Guruh topilmadi")

        for group in groups:
            self._apply(group, dict(fields))
        await self._session.flush()
        return {"updated": len(groups)}

    async def delete(self, group_id: UUID) -> None:
        """Guruhni o'chiradi — faqat bot chiqib ketgan bo'lsa.

        Faol guruhni o'chirish xavfli: bot hali ichida, keyingi `register`
        uni qayta yaratadi va biriktirish yo'qoladi. Shuning uchun avval
        botni guruhdan chiqarish kerak.
        """
        group = await self._get(group_id)
        if group.bot_status not in GONE_STATUSES:
            raise ConflictError(
                "Faqat bot chiqib ketgan guruhni o'chirish mumkin — "
                "avval botni guruhdan chiqaring",
                code="group_still_active",
            )
        await self._session.delete(group)
        await self._session.flush()

    # ── Bot: ro'yxatga olish ──────────────────────────────────

    async def register(
        self,
        chat_id: int,
        title: str,
        member_count: int | None = None,
        bot_status: str = BotStatus.MEMBER.value,
    ) -> dict[str, Any]:
        """Bot guruhga qo'shilganda/holat o'zgarganda chaqiradi (upsert).

        Biriktirish (`agent_id`, `region`) HECH QACHON tegilmaydi — bot
        adminning qarorini bilmaydi va uni bekor qila olmasligi kerak.
        """
        group = (
            await self._session.execute(
                select(TelegramGroupModel).where(TelegramGroupModel.chat_id == chat_id)
            )
        ).scalar_one_or_none()

        if group is None:
            group = TelegramGroupModel(
                chat_id=chat_id,
                title=title.strip() or str(chat_id),
                member_count=member_count,
                bot_status=bot_status,
                is_active=bot_status not in GONE_STATUSES,
            )
            self._session.add(group)
            try:
                await self._session.flush()
            except IntegrityError:
                # Ikkita yangilanish bir vaqtda kelsa — mavjudini olamiz
                await self._session.rollback()
                group = (
                    await self._session.execute(
                        select(TelegramGroupModel).where(
                            TelegramGroupModel.chat_id == chat_id
                        )
                    )
                ).scalar_one()
        else:
            group.title = title.strip() or group.title
            if member_count is not None:
                group.member_count = member_count
            group.bot_status = bot_status
            # Bot qaytib kirsa guruh yana faollashadi
            group.is_active = bot_status not in GONE_STATUSES
            await self._session.flush()

        return {
            "id": group.id,
            "chat_id": group.chat_id,
            "title": group.title,
            "agent_id": group.agent_id,
            "region": group.region,
            "suggested_region": (
                None
                if group.region
                else suggest_region(group.title, await self._region_names())
            ),
            "is_active": group.is_active,
            "bound": group.agent_id is not None and bool(group.region),
        }

    # ── Bot: avtomatik biriktirish ────────────────────────────

    async def _agent_regions(self, agent_id: UUID, exclude: UUID) -> list[str]:
        """Xodimning hududlari — YAGONA qoida bo'yicha (`agent_regions.py`).

        `exclude` — hozir qayta ishlanayotgan guruh: o'zining bo'sh
        hududini hisobga olmaymiz.
        """
        stmt = agent_region_names(agent_id).where(TelegramGroupModel.id != exclude)
        return sorted((await self._session.execute(stmt)).scalars())

    async def autobind(
        self,
        chat_id: int,
        title: str,
        member_count: int | None = None,
        bot_status: str = BotStatus.MEMBER.value,
        candidate_user_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Guruhni ro'yxatga oladi VA xodimini o'zi topadi.

        Bot guruhda sotuvchini uch yo'l bilan qidiradi (botni kim
        qo'shgani, adminlar, yozganlar) va topilgan Telegram id larini
        shu yerga yuboradi. Backend ularni ro'yxatdan o'tgan xodimlar
        bilan solishtiradi.

        Uchta qat'iy qoida:

        1. **`bound_by == "manual"` — TEGILMAYDI.** Admin qo'lda
           biriktirgan (yoki qo'lda hududini bo'shatgan) guruhni
           avtomatika qayta yozsa, admin tuzatgan narsa botning
           keyingi aylanishida yana buziladi. Bu eng jahli chiqaradigan
           xatolar sinfi, shuning uchun tekshiruv birinchi o'rinda.
        2. **Hudud** faqat xodimda AYNAN BITTA hudud bo'lsa qo'yiladi.
           Bir nechta bo'lsa `None` qoladi — noto'g'ri hudud qo'yilsa
           baho boshqa hududning hisobotiga tushib ketardi, bo'sh hudud
           esa shunchaki adminni daraxtda kutib turadi.
        3. Guruh turi a'zolar sonidan TAXMIN QILINMAYDI. Ishchi guruhni
           hudud belgilaydi (`domain/entities.py` dagi izohga qarang).
        """
        # `register` — mavjud upsert mantig'i (nom, a'zolar soni, bot
        # holati). Biriktirishga u tegmaydi, shuning uchun xavfsiz.
        await self.register(
            chat_id=chat_id,
            title=title,
            member_count=member_count,
            bot_status=bot_status,
        )
        group = (
            await self._session.execute(
                select(TelegramGroupModel).where(TelegramGroupModel.chat_id == chat_id)
            )
        ).scalar_one()

        async def result(reason: str, agent: AgentModel | None) -> dict[str, Any]:
            return {
                "id": group.id,
                "chat_id": group.chat_id,
                "title": group.title,
                "agent_id": group.agent_id,
                "agent_name": agent.full_name if agent else None,
                "region": group.region,
                "member_count": group.member_count,
                "bound": group.agent_id is not None,
                "bound_by": group.bound_by,
                "reason": reason,
            }

        async def current_agent() -> AgentModel | None:
            if group.agent_id is None:
                return None
            return await self._session.get(AgentModel, group.agent_id)

        # ── 1. Odam qarori ustun ──────────────────────────────
        if group.bound_by == BindSource.MANUAL.value:
            return await result("manual", await current_agent())

        # ── 2. Nomzodlar orasidan ro'yxatdan o'tgan xodim ──────
        candidates = [uid for uid in (candidate_user_ids or []) if uid]
        agent: AgentModel | None = None
        if candidates:
            agent = (
                await self._session.execute(
                    select(AgentModel)
                    .where(
                        AgentModel.telegram_user_id.in_(candidates),
                        AgentModel.is_active.is_(True),
                    )
                    .order_by(AgentModel.enrolled_at)
                    .limit(1)
                )
            ).scalars().first()

        if agent is None:
            # Hech kim topilmadi. Avval biriktirilgan xodim bo'lsa
            # UZILMAYDI: bugun guruhda faqat mijoz yozgan bo'lishi
            # mumkin, bu sotuvchi almashdi degani emas.
            existing = await current_agent()
            if existing is not None:
                return await result("matched", existing)
            return await result("no_agent", None)

        # ── 3. Biriktirish ────────────────────────────────────
        group.agent_id = agent.id
        group.bound_by = BindSource.AUTO.value

        # Hudud allaqachon bo'lsa tegilmaydi — u qayerdandir kelgan
        # (avvalgi biriktirish yoki admin), uni qayta o'ylash shart emas.
        if group.region is None:
            regions = await self._agent_regions(agent.id, exclude=group.id)
            if len(regions) == 1:
                group.region = regions[0]

        bound = group.agent_id is not None and bool(group.region)
        if bound and group.bound_at is None:
            group.bound_at = datetime.now(UTC)
        elif not bound:
            group.bound_at = None

        await self._session.flush()
        return await result("matched", agent)

    # ── Bot: navbatdagi so'rovnomalar ─────────────────────────

    async def pending_surveys(self) -> list[dict[str, Any]]:
        """Yaratilgan, lekin hali guruhga yuborilmagan so'rovnomalar."""
        rows = (
            await self._session.execute(
                select(SurveyModel, TelegramGroupModel, AgentModel)
                .join(
                    TelegramGroupModel,
                    TelegramGroupModel.id == SurveyModel.group_id,
                )
                .join(AgentModel, AgentModel.id == SurveyModel.agent_id)
                .where(SurveyModel.status == SurveyStatus.PENDING)
                .order_by(SurveyModel.created_at)
            )
        ).all()

        return [
            {
                "survey_id": survey.id,
                "token": survey.token,
                "chat_id": group.chat_id,
                "agent_name": agent.full_name,
                "period_start": survey.period_start,
                "period_end": survey.period_end,
            }
            for survey, group, agent in rows
        ]

    async def live_surveys(self) -> list[dict[str, Any]]:
        """Guruhga yuborilgan va hali muddati o'tmagan so'rovnomalar.

        Mini App rejimida baholar to'g'ridan-to'g'ri backendga tushadi —
        bot ular haqida hech narsa bilmaydi. Natijada guruhdagi «N kishi
        baho berdi» hisoblagichi «hali hech kim baho bermadi» bo'lib
        qotib qolardi va bu ishtirokni pasaytirardi.

        Bot shu ro'yxatni davriy o'qib, soni o'zgargan xabarlarni
        yangilaydi. Telegram bilan ishlash mantig'i botda qoladi —
        backend Telegram API ga chiqmaydi.
        """
        now = datetime.now(UTC)
        rows = (
            await self._session.execute(
                select(SurveyModel, TelegramGroupModel)
                .join(
                    TelegramGroupModel,
                    TelegramGroupModel.id == SurveyModel.group_id,
                )
                .where(
                    SurveyModel.chat_message_id.isnot(None),
                    # O'chirilgan xabarni tahrirlab bo'lmaydi — uni
                    # ro'yxatga qo'shish har aylanishda bitta bekor
                    # Telegram so'rovi va bitta xato logi degani.
                    SurveyModel.message_deleted_at.is_(None),
                    SurveyModel.expires_at > now,
                    SurveyModel.status != SurveyStatus.PENDING,
                )
                .order_by(SurveyModel.created_at.desc())
            )
        ).all()

        return [
            {
                "token": survey.token,
                "chat_id": group.chat_id,
                "chat_message_id": survey.chat_message_id,
                "response_count": survey.response_count or 0,
            }
            for survey, group in rows
        ]

    # ── Muddati o'tgan xabarlarni olib tashlash ───────────────

    async def expired_survey_messages(self) -> list[dict[str, Any]]:
        """Guruhdan O'CHIRILISHI kerak bo'lgan so'rovnoma xabarlari.

        ⚠️ BU RO'YXAT — O'CHIRISHNING YAGONA MANBAI. Bot guruhdagi
        xabarlarni umuman ko'rmaydi va sanab chiqmaydi: u faqat shu
        yerdan kelgan `(chat_id, message_id)` juftligini o'chiradi.
        Har bir juftlikni bot O'ZI yuborgan va `POST /surveys/{token}/sent`
        orqali aynan shu yerga yozib qo'ygan.

        Shuning uchun bitta bot ikkita dastur bilan ishlatilsa ham
        boshqa dasturning xabari bu ro'yxatga TUSHA OLMAYDI — u
        `surveys` jadvalida umuman yo'q.

        Shartlar:
          · xabar yuborilgan (`chat_message_id` to'la)
          · hali o'chirilmagan (`message_deleted_at` bo'sh)
          · yuborilganidan TTL soat o'tgan

        TTL `0` bo'lsa (sozlamada «hech qachon») ro'yxat bo'sh qaytadi.
        """
        ttl_hours = await resolve_message_ttl_hours(self._session)
        if ttl_hours <= 0:
            return []

        deadline = datetime.now(UTC) - timedelta(hours=ttl_hours)
        rows = (
            await self._session.execute(
                select(SurveyModel, TelegramGroupModel)
                .join(
                    TelegramGroupModel,
                    TelegramGroupModel.id == SurveyModel.group_id,
                )
                .where(
                    SurveyModel.chat_message_id.isnot(None),
                    SurveyModel.message_deleted_at.is_(None),
                    # `sent_at` bo'sh qolgan eski yozuvlar uchun zaxira:
                    # yaratilgan vaqtga tayanamiz, aks holda ular
                    # navbatda abadiy qolib ketardi.
                    func.coalesce(SurveyModel.sent_at, SurveyModel.created_at)
                    <= deadline,
                )
                .order_by(SurveyModel.sent_at)
            )
        ).all()

        return [
            {
                "token": survey.token,
                "chat_id": group.chat_id,
                "chat_message_id": survey.chat_message_id,
            }
            for survey, group in rows
        ]

    async def mark_message_deleted(self, token: str) -> dict[str, str]:
        """«Bu xabar bilan ish tugadi» belgisi.

        Bot muvaffaqiyatli o'chirgandan KEYIN chaqiradi. O'chirib
        bo'lmagan holatda ham chaqiradi (masalan Telegram'ning 48
        soatlik chegarasi o'tgan): aks holda o'sha xabar har
        aylanishda qaytib kelib, navbatni cheksiz to'ldirardi.

        Idempotent: ikkinchi chaqiruv hech narsani o'zgartirmaydi.
        Bot xabarni o'chirdi-yu, javob tarmoqda yo'qoldi degan holat
        oddiy — keyingi aylanishda qayta chaqiriladi.
        """
        survey = (
            await self._session.execute(
                select(SurveyModel).where(SurveyModel.token == token)
            )
        ).scalar_one_or_none()

        if survey is None:
            raise NotFoundError("So'rovnoma topilmadi")

        if survey.message_deleted_at is None:
            survey.message_deleted_at = datetime.now(UTC)
            await self._session.flush()

        return {"status": "ok"}

    # ── So'rovnoma qoidalari ──────────────────────────────────
    #
    # Qoidalar ikki turga bo'lingan, chunki ular BIR XIL emas:
    #
    #   • tuzilmaviy — xodim/hudud biriktirilmagan, guruh faol emas.
    #     Bularni HECH QACHON chetlab bo'lmaydi: xodimsiz guruhda bahoni
    #     kimga yozishni bilmaymiz, bot chiqib ketgan guruhga esa xabar
    #     umuman yetib bormaydi.
    #   • vaqtga oid — suppression oynasi. Bu admin qarori bilan
    #     chetlab o'tiladi (`force=True`), chunki "hozir hammaga yubor"
    #     tugmasi aynan shuning uchun bor.

    @staticmethod
    def _structural_block(group: TelegramGroupModel) -> tuple[str, str] | None:
        """Tuzilmaviy to'siq: `(kod, o'zbekcha xabar)` yoki `None`."""
        if group.agent_id is None:
            return ("group_not_bound", "Guruhga savdo xodimi biriktirilmagan")
        if not group.region:
            return ("group_not_bound", "Guruhga hudud biriktirilmagan")
        if not group.is_active or group.bot_status in GONE_STATUSES:
            return ("group_inactive", "Guruh faol emas yoki bot guruhdan chiqarilgan")
        return None

    @staticmethod
    def _suppression_block(
        last: datetime | None, now: datetime, window: int
    ) -> tuple[str, str] | None:
        """Vaqtga oid to'siq: oxirgi so'rovnomadan N kun o'tmagan bo'lsa.

        `window` sozlamalardan keladi (`survey.suppression_days`), kodda
        yozilgan konstantadan emas.
        """
        if last is None:
            return None
        passed = (now - last).days
        if passed >= window:
            return None
        return (
            "survey_suppressed",
            f"Oxirgi so'rovnoma {passed} kun oldin yaratilgan — "
            f"keyingisiga {window - passed} kun qoldi",
        )

    def _queue_survey(
        self, group: TelegramGroupModel, now: datetime, period_days: int
    ) -> SurveyModel:
        """Yangi `pending` so'rovnomani sessiyaga qo'shadi (flush QILMAYDI).

        Flush chaqiruvchida — ommaviy yuborishda hamma guruh bitta
        tranzaksiyada yoziladi.
        """
        survey = SurveyModel(
            client_id=None,  # guruh so'rovnomasida client yo'q
            agent_id=group.agent_id,
            group_id=group.id,
            # ⚠️ Hudud NUSXASI shu yerda muhrlanadi va keyin hech qachon
            # o'zgarmaydi. Guruh boshqa hududga ko'chirilsa yoki hudud
            # arxivlanib guruhdan uzilsa, SHU so'rovnoma o'z hududida
            # qoladi — o'tgan oylarning hisoboti qayta yozilmaydi.
            region=group.region,
            token=new_survey_token(),
            period_start=now - timedelta(days=period_days),
            period_end=now,
            channel=SurveyChannel.TELEGRAM_GROUP,
            status=SurveyStatus.PENDING,
            expires_at=now + timedelta(days=SURVEY_TOKEN_TTL_DAYS),
            response_count=0,
        )
        self._session.add(survey)
        group.last_survey_at = now
        return survey

    async def _pending_survey(self, group_id: UUID) -> SurveyModel | None:
        """Guruhning hali yuborilmagan so'rovnomasi (eng eskisi)."""
        return (
            await self._session.execute(
                select(SurveyModel)
                .where(
                    SurveyModel.group_id == group_id,
                    SurveyModel.status == SurveyStatus.PENDING,
                )
                .order_by(SurveyModel.created_at)
                .limit(1)
            )
        ).scalars().first()

    # ── So'rovnoma yaratish ───────────────────────────────────

    async def create_survey(
        self, group_id: UUID, force: bool = False
    ) -> dict[str, Any]:
        """Guruh uchun yangi so'rovnoma yaratadi va navbatga qo'yadi.

        Bot uni `GET /groups/pending-surveys` orqali oladi — shuning uchun
        bu yerda Telegramga hech narsa yuborilmaydi, faqat yozuv.

        `force=True` — suppression oynasi butunlay e'tiborsiz qoldiriladi.
        Tuzilmaviy qoidalar esa baribir ishlaydi.
        """
        group = await self._get(group_id)
        now = datetime.now(UTC)

        await self._require_surveys_enabled()

        block = self._structural_block(group)
        if block is not None:
            code, message = block
            raise ConflictError(message, code=code)

        # Navbatda turgan so'rovnoma bo'lsa ikkinchisi yaratilmaydi:
        # aks holda guruhga ikkita bir xil xabar tushardi.
        existing = await self._pending_survey(group.id)
        if existing is not None:
            return {
                "survey_id": existing.id,
                "token": existing.token,
                "status": existing.status.value,
                "reused": True,
            }

        if not force:
            # Suppression: keshlangan `last_survey_at` ham, haqiqiy oxirgi
            # so'rovnoma ham tekshiriladi — kesh eskirgan bo'lsa ham
            # qoida ishlaydi.
            last_created = (
                await self._session.execute(
                    select(func.max(SurveyModel.created_at)).where(
                        SurveyModel.group_id == group.id
                    )
                )
            ).scalar_one_or_none()
            last = max(
                (d for d in (group.last_survey_at, last_created) if d is not None),
                default=None,
            )
            block = self._suppression_block(
                last, now, await resolve_suppression_days(self._session)
            )
            if block is not None:
                code, message = block
                raise ConflictError(message, code=code)

        survey = self._queue_survey(
            group, now, await resolve_period_days(self._session)
        )
        await self._session.flush()

        return {
            "survey_id": survey.id,
            "token": survey.token,
            "status": survey.status.value,
            "reused": False,
        }

    # ── Ommaviy yuborish ──────────────────────────────────────

    async def _require_surveys_enabled(self) -> None:
        """`survey.enabled` o'chirilgan bo'lsa yaratishni to'xtatadi.

        ⚠️ Ilgari bu sozlama HECH QAYERDA o'qilmasdi: admin «so'rovnoma
        yuborish o'chirilgan» deb turib tugmani bossa, so'rovnoma
        baribir haqiqiy mijoz guruhiga ketardi. Sozlamaning nomi
        va izohi esa buning aksini va'da qilardi.

        Tekshiruv yaratishning IKKALA yo'lida ham turadi — bittasida
        bo'lsa ikkinchisi teshik bo'lib qolardi.
        """
        if not await resolve_survey_enabled(self._session):
            raise ConflictError(
                "So'rovnoma yuborish o'chirilgan. "
                "Sozlamalar → Client so'rovnomasi → «So'rovnoma yuborish yoqilgan»",
                code="survey_disabled",
            )

    async def broadcast_surveys(
        self, force: bool = True, window_days: int | None = None
    ) -> dict[str, Any]:
        """Barcha yaroqli guruhlarga bittadan so'rovnoma qo'yadi.

        Har bir so'rovnoma o'sha guruhning O'Z xodimiga yoziladi — umumiy
        so'rovnoma yo'q, chunki baho har doim aniq bir xodimga tegishli.

        `force=True` (sukut bo'yicha) — vaqtga oid hech qanday qoida
        to'sqinlik qilmaydi. Tugmaning butun mazmuni shu: admin "hozir
        hammaga yubor" deganda 10 kunlik oyna sabab jimgina hech narsa
        yubormaslik — buzuq xatti-harakat.

        `window_days` — `force=False` da ishlatiladigan oyna. Berilmasa
        `survey.suppression_days` olinadi. Avtomatik kadans buni
        `survey.period_days` bilan chaqiradi: «har 5 kunda bir marta»
        degan va'da 3 kunlik suppression oynasi bilan bajarilmaydi.

        Guruh allaqachon navbatda tursa (`pending`, hali yuborilmagan)
        ikkinchisi yaratilmaydi — `reused` bo'lib sanaladi. Aks holda
        tugma ikki marta bosilsa guruhga ikkita bir xil xabar tushardi.

        BITTA TRANZAKSIYA: yozuvlar sessiyaga yig'iladi va oxirida bir
        marta flush qilinadi. So'rov yarmida xato chiqsa `get_session`
        hammasini qaytaradi — yarmi navbatga tushib qolgan holat bo'lmaydi.
        """
        now = datetime.now(UTC)

        await self._require_surveys_enabled()

        # Faolsiz guruhlar ham olinadi: ular `skipped` da sabab bilan
        # ko'rinsin — "nega bu guruhga tushmadi" degan savol qolmasin.
        groups = list(
            (
                await self._session.execute(
                    select(TelegramGroupModel).order_by(TelegramGroupModel.title)
                )
            ).scalars()
        )

        # Navbatdagi so'rovnomalar — bitta so'rov bilan, har guruh uchun
        # alohida bormaymiz (N+1 bo'lardi).
        pending_by_group: dict[UUID, SurveyModel] = {}
        for survey in (
            await self._session.execute(
                select(SurveyModel)
                .where(
                    SurveyModel.group_id.isnot(None),
                    SurveyModel.status == SurveyStatus.PENDING,
                )
                .order_by(SurveyModel.created_at)
            )
        ).scalars():
            pending_by_group.setdefault(survey.group_id, survey)

        # Oxirgi so'rovnoma vaqti — faqat `force=False` da kerak
        last_by_group: dict[UUID, datetime] = {}
        if not force:
            rows = (
                await self._session.execute(
                    select(
                        SurveyModel.group_id,
                        func.max(SurveyModel.created_at),
                    )
                    .where(SurveyModel.group_id.isnot(None))
                    .group_by(SurveyModel.group_id)
                )
            ).all()
            last_by_group = {group_id: created for group_id, created in rows}

        created = 0
        reused = 0
        skipped: list[dict[str, Any]] = []

        # Sozlamalar sikldan oldin bir marta o'qiladi — 50 ta guruhda
        # har biri uchun bazaga borish keraksiz
        period_days = await resolve_period_days(self._session)
        if force:
            suppression_days = None
        elif window_days is not None:
            suppression_days = window_days
        else:
            suppression_days = await resolve_suppression_days(self._session)

        for group in groups:
            block = self._structural_block(group)
            if block is None and group.id in pending_by_group:
                reused += 1
                continue
            if block is None and not force:
                last = max(
                    (
                        d
                        for d in (group.last_survey_at, last_by_group.get(group.id))
                        if d is not None
                    ),
                    default=None,
                )
                block = self._suppression_block(last, now, suppression_days)

            if block is not None:
                code, message = block
                skipped.append(
                    {
                        "group_id": group.id,
                        "title": group.title,
                        "reason": code,
                        "message": message,
                    }
                )
                continue

            self._queue_survey(group, now, period_days)
            created += 1

        await self._session.flush()

        return {
            "created": created,
            "reused": reused,
            "skipped": skipped,
            "total_groups": len(groups),
        }
