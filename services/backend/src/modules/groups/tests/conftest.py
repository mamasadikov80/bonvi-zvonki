"""`groups` testlari uchun yordamchi fixture'lar.

IKKI XIL IZOLYATSIYA — IKKI XIL VOSITA

  1. `rollback_session` — COMMIT QILINMAYDIGAN sessiya.

     `GroupService` ning ko'p metodlari butun jadval ustidan yuradi:
     `broadcast_surveys()` bazadagi HAR BIR guruhga so'rovnoma qo'yadi
     va ularning `last_survey_at` ini yangilaydi. Buni haqiqiy dev
     bazasida commit bilan bajarish — ishlatuvchining guruhlariga
     so'rovnoma navbatga tashlash demak.

     Yechim: servis metodlari faqat `flush()` qiladi (`commit()`
     chaqiruvchida), shuning uchun butun test bitta tranzaksiya ichida
     bajariladi va oxirida ROLLBACK bo'ladi. Bazada bironta ham iz
     qolmaydi, ammo kod haqiqiy PostgreSQL ustida ishlaydi.

     ⚠️ `SessionFactory` da `autoflush=False` — qo'shilgan obyektlar
     so'rovdan oldin O'ZI yozilmaydi. Har `add()` dan keyin `flush()`
     qilish shart.

  2. `seed` — HTTP endpointlari uchun haqiqiy, commit qilingan yozuvlar.

     Endpoint `get_session` orqali o'zi commit qiladi, shuning uchun
     bu yerda tozalash yaratilgan `id` lar va nom prefiksi bo'yicha
     bajariladi. Guruh o'chsa unga tegishli so'rovnoma va javoblar
     `ON DELETE CASCADE` bilan o'zi ketadi.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest_asyncio
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.groups.domain.entities import BotStatus
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.surveys.domain.entities import (
    SurveyChannel,
    SurveyStatus,
    new_survey_token,
)
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel

API = "http://test/api/v1"

#: Shu modul yaratgan yozuvlarni tanib olish uchun prefiks.
MARK = "pytest-groups"


def unique_name(prefix: str = "guruh") -> str:
    return f"{MARK}-{prefix}-{uuid.uuid4().hex[:8]}"


def chat_id() -> int:
    """Telegram supergroup id ga o'xshash, band bo'lmagan manfiy son."""
    return -random.randrange(10**12, 10**13)


def telegram_user_id() -> int:
    """Ro'yxatdan o'tgan xodimning Telegram id si — `agents` da unique."""
    return random.randrange(10**11, 10**12)


# ══════════════════════════════════════════════════════════════
#  Yozilmagan ORM obyektlari — `rollback_session` ichida ishlatiladi
# ══════════════════════════════════════════════════════════════


def build_agent(
    *,
    region: str | None = None,
    telegram_user_id_: int | None = None,
    is_active: bool = True,
    enrolled_at: datetime | None = None,
) -> AgentModel:
    """Savdo xodimi.

    `region` — xodimning YASHASH joyi. Biriktirishda ishlatilmaydi,
    shuning uchun standart qiymat ham test prefiksli: bazadagi haqiqiy
    hududlarning ishlatilish hisobiga qo'shilib ketmasin.
    """
    return AgentModel(
        full_name=unique_name("xodim"),
        region=region or unique_name("yashash"),
        telegram_user_id=telegram_user_id_,
        is_active=is_active,
        enrolled_at=enrolled_at,
    )


def build_group(
    *,
    agent_id: UUID | None = None,
    region: str | None = None,
    is_active: bool = True,
    bound_by: str | None = None,
    bot_status: str = BotStatus.MEMBER.value,
    last_survey_at: datetime | None = None,
    title: str | None = None,
) -> TelegramGroupModel:
    return TelegramGroupModel(
        chat_id=chat_id(),
        title=title or unique_name(),
        agent_id=agent_id,
        region=region,
        is_active=is_active,
        bound_by=bound_by,
        bot_status=bot_status,
        last_survey_at=last_survey_at,
    )


def build_survey(
    *,
    agent_id: UUID,
    group_id: UUID | None = None,
    status: SurveyStatus = SurveyStatus.SENT,
    sent_at: datetime | None = None,
    chat_message_id: int | None = None,
    message_deleted_at: datetime | None = None,
) -> SurveyModel:
    now = datetime.now(UTC)
    return SurveyModel(
        client_id=None,
        agent_id=agent_id,
        group_id=group_id,
        token=new_survey_token(),
        period_start=now - timedelta(days=14),
        period_end=now,
        channel=SurveyChannel.TELEGRAM_GROUP,
        status=status,
        sent_at=sent_at,
        chat_message_id=chat_message_id,
        message_deleted_at=message_deleted_at,
        expires_at=now + timedelta(days=7),
        response_count=0,
    )


def build_response(*, survey_id: UUID, csat: int = 5) -> SurveyResponseModel:
    return SurveyResponseModel(
        survey_id=survey_id,
        # Har javob boshqa odamdan — `uq_response_per_respondent` ushlab
        # qolmasin
        respondent_hash=uuid.uuid4().hex,
        csat=csat,
        responded_at=datetime.now(UTC),
    )


async def survey_count(session: AsyncSession, group_id: UUID) -> int:
    """Aynan SHU guruhning so'rovnomalari — bazadagi qolganlari emas."""
    return (
        await session.execute(
            select(func.count(SurveyModel.id)).where(SurveyModel.group_id == group_id)
        )
    ).scalar_one()


# ══════════════════════════════════════════════════════════════
#  Fixture'lar
# ══════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def rollback_session() -> AsyncIterator[AsyncSession]:
    """Commit qilinmaydigan sessiya — modul boshidagi izohga qarang."""
    async with SessionFactory() as session:
        try:
            yield session
        finally:
            await session.rollback()


class Seed:
    """HTTP testlari uchun haqiqiy yozuvlar. Test oxirida o'chiriladi."""

    def __init__(self) -> None:
        self.agent_ids: list[UUID] = []
        self.group_ids: list[UUID] = []

    async def agent(self, **kwargs) -> AgentModel:
        async with SessionFactory() as session:
            agent = build_agent(**kwargs)
            session.add(agent)
            await session.commit()
        self.agent_ids.append(agent.id)
        return agent

    async def group(self, **kwargs) -> TelegramGroupModel:
        async with SessionFactory() as session:
            group = build_group(**kwargs)
            session.add(group)
            await session.commit()
        self.group_ids.append(group.id)
        return group


@pytest_asyncio.fixture
async def seed() -> AsyncIterator[Seed]:
    bin_ = Seed()
    yield bin_

    async with SessionFactory() as session:
        # Guruh o'chsa so'rovnomalari va javoblari kaskad bilan ketadi
        await session.execute(
            delete(TelegramGroupModel).where(
                or_(
                    TelegramGroupModel.id.in_(bin_.group_ids),
                    TelegramGroupModel.title.like(f"{MARK}%"),
                )
            )
        )
        await session.execute(
            delete(AgentModel).where(
                or_(
                    AgentModel.id.in_(bin_.agent_ids),
                    AgentModel.full_name.like(f"{MARK}%"),
                )
            )
        )
        await session.commit()
