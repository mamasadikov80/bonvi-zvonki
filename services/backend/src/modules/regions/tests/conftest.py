"""`regions` testlari uchun yordamchi fixture'lar.

NEGA O'Z YOZUVLARIMIZ

  Dev bazasida haqiqiy hududlar bor («Toshkent», «Samarqand» …) va
  ular xodim, mijoz, guruh jadvallarida matn bo'lib takrorlanadi.
  Kaskad nom o'zgartirishni o'sha nomlar ustida sinash — ishlatuvchining
  ma'lumotini qayta yozish demak.

  Shuning uchun har test O'ZINING hududini yaratadi: nomi tasodifiy
  qo'shimchali (`pytest-regions-hudud-1a2b3c4d`), ya'ni kaskad
  `UPDATE ... WHERE region = <o'sha nom>` boshqa hech qaysi qatorga
  tegmasligi kafolatlangan.

TOZALASH IKKI BOSQICHLI

  1) yaratilgan `id` lar bo'yicha,
  2) nom prefiksi bo'yicha — zaxira. Test o'rtada yiqilib, yozuv
     ro'yxatga tushmay qolsa ham qoldiq bazada qolib ketmaydi.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest_asyncio
from sqlalchemy import delete, or_

from src.core.database import SessionFactory
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.infrastructure.models import RegionModel

API = "http://test/api/v1"

#: Shu modul yaratgan yozuvlarni tanib olish uchun prefiks.
MARK = "pytest-regions"

USAGE_ZERO = {"agents": 0, "clients": 0, "groups": 0}


def unique_name(prefix: str = "hudud") -> str:
    """Hech kim bilan to'qnashmaydigan nom."""
    return f"{MARK}-{prefix}-{uuid.uuid4().hex[:8]}"


def _chat_id() -> int:
    """Telegram supergroup id ga o'xshash, band bo'lmagan manfiy son."""
    return -random.randrange(10**12, 10**13)


class Seed:
    """Test uchun hudud va guruh yaratadi, yaratganini eslab qoladi."""

    def __init__(self) -> None:
        self.region_ids: list[UUID] = []
        self.group_ids: list[UUID] = []

    async def region(
        self,
        name: str | None = None,
        *,
        sort_order: int = 0,
        is_active: bool = True,
        note: str | None = None,
    ) -> RegionModel:
        async with SessionFactory() as session:
            region = RegionModel(
                name=name or unique_name(),
                sort_order=sort_order,
                is_active=is_active,
                note=note,
            )
            session.add(region)
            await session.commit()
        self.region_ids.append(region.id)
        return region

    def track_region(self, region_id: UUID | str) -> None:
        """Endpoint orqali yaratilgan hududni tozalash ro'yxatiga qo'shadi."""
        self.region_ids.append(UUID(str(region_id)))

    async def group(
        self,
        *,
        agent_id: UUID | None = None,
        region: str | None = None,
        is_active: bool = True,
        title: str | None = None,
    ) -> TelegramGroupModel:
        async with SessionFactory() as session:
            group = TelegramGroupModel(
                chat_id=_chat_id(),
                title=title or unique_name("guruh"),
                agent_id=agent_id,
                region=region,
                is_active=is_active,
            )
            session.add(group)
            await session.commit()
        self.group_ids.append(group.id)
        return group


@pytest_asyncio.fixture
async def seed() -> AsyncIterator[Seed]:
    bin_ = Seed()
    yield bin_

    async with SessionFactory() as session:
        # Guruh oldin: hududga bog'liqligi matn bo'lsa ham, tartib
        # o'qishga qulay bo'lsin.
        await session.execute(
            delete(TelegramGroupModel).where(
                or_(
                    TelegramGroupModel.id.in_(bin_.group_ids),
                    TelegramGroupModel.title.like(f"{MARK}%"),
                )
            )
        )
        await session.execute(
            delete(RegionModel).where(
                or_(
                    RegionModel.id.in_(bin_.region_ids),
                    RegionModel.name.like(f"{MARK}%"),
                )
            )
        )
        await session.commit()
