"""Hududlar jadvalini mavjud ma'lumot asosida to'ldirish.

Nega bu `seed.py` da emas: `seed.py` demo ma'lumot uchun va `--reset` bilan
tozalanadi. Hududlar esa tizim ishlashi uchun zarur — jadval bo'sh bo'lsa,
mavjud har bir xodimning hududi ro'yxatdan tashqarida qolib, xodim
formasidagi dropdown qiymatni yo'qotadi. Shuning uchun bu `bootstrap.py`
dan, jadvallar yaratilgandan so'ng darhol chaqiriladi.

Idempotent: `ON CONFLICT (name) DO NOTHING` + mavjud nomlarni oldindan
chetlab o'tish. Necha marta ishga tushirilsa ham nusxa yaratmaydi va
adminning qo'lda kiritgan tartibiga tegmaydi.
"""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.domain.entities import (
    SORT_ORDER_STEP,
    normalize_region_name,
)
from src.modules.regions.infrastructure.models import RegionModel

# Hudud matni saqlanadigan uchala ustun — kaskad yangilash ham,
# ishlatilish hisobi ham shu ro'yxatga tayanadi.
_REGION_COLUMNS = (
    AgentModel.region,
    ClientModel.region,
    TelegramGroupModel.region,
)


async def populate_initial_regions(conn: AsyncConnection) -> list[str]:
    """Mavjud `region` qiymatlaridan yetishmayotgan hududlarni qo'shadi.

    Qaytaradi: shu chaqiruvda qo'shilgan nomlar (bo'sh bo'lsa — hammasi
    allaqachon bor edi).

    Tartib ishlatilish soni bo'yicha: eng ko'p xodim/mijoz biriktirilgan
    hudud yuqorida turadi. Bu qat'iy viloyatlar ro'yxatisiz ham «yirik savdo
    hududlari yuqorida» qoidasini beradi — keyin admin xohlaganicha
    o'zgartiradi.
    """
    existing: set[str] = set(
        (await conn.execute(select(RegionModel.name))).scalars().all()
    )

    # Nom → nechta yozuvda uchraydi (uchala jadval bo'ylab yig'indi)
    usage: dict[str, int] = {}
    for column in _REGION_COLUMNS:
        rows = await conn.execute(
            select(column, func.count())
            .where(column.isnot(None), func.btrim(column) != "")
            .group_by(column)
        )
        for raw_name, count in rows:
            name = normalize_region_name(raw_name)
            if name:
                usage[name] = usage.get(name, 0) + count

    missing = [name for name in usage if name not in existing]
    if not missing:
        return []

    # Ko'p ishlatilgani oldin; teng bo'lsa alifbo bo'yicha — natija
    # takrorlanadigan bo'lsin.
    missing.sort(key=lambda name: (-usage[name], name))

    # Mavjud tartibning davomidan boshlaymiz: qayta ishga tushirilganda
    # yangi hudud ro'yxat oxiriga tushadi, boshiga emas.
    last_order = (
        await conn.execute(select(func.coalesce(func.max(RegionModel.sort_order), 0)))
    ).scalar_one()

    await conn.execute(
        insert(RegionModel)
        .values(
            [
                {
                    # `id` ataylab qo'lda: ko'p qatorli Core INSERT da
                    # ORM ning Python-tarafdagi `default` iga tayanmaymiz.
                    "id": uuid4(),
                    "name": name,
                    "is_active": True,
                    "sort_order": last_order + (index + 1) * SORT_ORDER_STEP,
                    "note": None,
                }
                for index, name in enumerate(missing)
            ]
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    return missing
