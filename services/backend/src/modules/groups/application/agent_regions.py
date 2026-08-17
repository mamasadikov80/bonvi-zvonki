"""Xodim qaysi hududlarda ishlaydi — YAGONA manba.

MUAMMO. Hudud tizimda ikki xil ma'noda ishlatiladi:

  · `agents.region`          — xodim YASHAYDIGAN joy (kartochkadagi maydon)
  · `telegram_groups.region` — u XIZMAT KO'RSATADIGAN hudud

Ular teng emas: Toshkentda yashab Samarqand mijozlarini yuritish
mumkin. Xodim bir vaqtda bir nechta hududda ishlashi ham mumkin —
`agents.region` esa bitta ustun, ya'ni buni ifodalay olmaydi.

Shuning uchun «xodimning hududlari» degan savolga javob HAR DOIM
biriktirilgan guruhlardan olinadi. Ilgari bu qoida uch joyda
alohida yozilgan edi va ular bir-biridan farq qilardi: profil
sahifasi `agents.region` ni, guruhlar daraxti guruh hududlarini,
hudud filtri esa uchinchi variantni ko'rsatardi. Bitta xodim uch
ekranda uch xil hududda «yashardi».

QOIDA (shu modulda, bir joyda):
  · faqat FAOL guruhlar — o'chirilgan guruh xizmat ko'rsatilmaydi
  · hududi to'ldirilgan guruhlar — `NULL` hudud «hali saralanmagan»
  · takrorlanmaydigan va alifbo bo'yicha tartiblangan ro'yxat
"""

from uuid import UUID

from sqlalchemy import Select, distinct, func, select

from src.modules.groups.infrastructure.models import TelegramGroupModel


def agent_region_names(agent_id: UUID) -> Select:
    """Bitta xodimning hududlari — kichik so'rov (`IN (...)` uchun mos)."""
    return select(distinct(TelegramGroupModel.region)).where(
        TelegramGroupModel.agent_id == agent_id,
        TelegramGroupModel.region.isnot(None),
        TelegramGroupModel.is_active.is_(True),
    )


def regions_by_agent(agent_ids: list[UUID] | None = None) -> Select:
    """Bir nechta xodim uchun: `(agent_id, [hududlar])` qatorlari.

    Bitta `GROUP BY` — ro'yxat sahifasida har qator uchun alohida
    so'rov yuborilmaydi (N+1 bo'lardi).

    `agent_ids=None` — hammasi; bo'sh ro'yxat — hech kim (chaqiruvchi
    buni oldindan tekshirishi kerak, aks holda `IN ()` yoziladi).
    """
    stmt = (
        select(
            TelegramGroupModel.agent_id,
            func.array_agg(distinct(TelegramGroupModel.region)),
        )
        .where(
            TelegramGroupModel.agent_id.isnot(None),
            TelegramGroupModel.region.isnot(None),
            TelegramGroupModel.is_active.is_(True),
        )
        .group_by(TelegramGroupModel.agent_id)
    )
    if agent_ids is not None:
        stmt = stmt.where(TelegramGroupModel.agent_id.in_(agent_ids))
    return stmt


async def load_regions_by_agent(session, agent_ids: list[UUID] | None = None):
    """`regions_by_agent()` ni bajarib, tayyor lug'at qaytaradi."""
    if agent_ids is not None and not agent_ids:
        return {}
    rows = (await session.execute(regions_by_agent(agent_ids))).all()
    return {agent_id: sorted(regions) for agent_id, regions in rows}
