"""Filial → xodim xaritasi.

SAP savdo faylida SOTUVCHI ISMI YO'Q — bor-yo'g'i `Подразделение`
(Бухоро, Мастона ёйма, Логистика…). Savdoni xodimga bog'lashning
yagona yo'li shu jadval.

Import nom o'xshashligiga qarab avtomatik biriktiradi (aynan tenglik,
`normalize_branch`), qolganini rahbar qo'lda qo'yadi. O'lchandi
(22.08.2026): 29 filialdan 15 tasi avtomatik, qo'lda biriktirilgani
bilan birga 19 tasi = savdolarning 88.4%.

⚠️ XARITA OCHIQ TURISHI KERAK. Rahbar qaysi filial kimga
biriktirilganini va uni tizim topganmi yoki odam qo'yganmi — ko'rib
turmasa, xodimlar kesimidagi sonlarga ishonmaydi. Shuning uchun
ro'yxatda biriktirilmagan filiallar ham, ulardagi savdolar soni ham
ko'rinadi.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.sales.application.importer import backfill_sale_links
from src.modules.sales.domain.entities import SaleOpType
from src.modules.sales.infrastructure.models import SaleBranchModel, SaleModel


@dataclass(slots=True)
class BranchRow:
    """Bitta filial va uning dalili."""

    branch: str
    agent_id: UUID | None
    agent_name: str | None
    matched_automatically: bool
    """`True` — nom o'xshashligiga qarab tizim topgan; `False` — odam
    qo'ygan yoki hali biriktirilmagan."""
    sales: int
    """Shu filialdagi savdolar soni — biriktirish qanchalik muhimligini
    ko'rsatadi (biriktirilmagan filialdagi 79 savdo xodimsiz qoladi)."""


async def list_branches(session: AsyncSession) -> list[BranchRow]:
    """Butun xarita — savdosi ko'pidan boshlab.

    Tartib ATAYLAB savdolar soni bo'yicha: rahbar birinchi navbatda eng
    ko'p savdo yotgan filialni biriktirishi kerak.
    """
    counts = (
        select(SaleModel.branch.label("branch"), func.count().label("sales"))
        .where(SaleModel.op_type == SaleOpType.SALE.value)
        .where(SaleModel.branch.is_not(None))
        .group_by(SaleModel.branch)
        .subquery("branch_sales")
    )

    rows = (
        await session.execute(
            select(
                SaleBranchModel.branch,
                SaleBranchModel.agent_id,
                SaleBranchModel.matched_automatically,
                AgentModel.full_name.label("agent_name"),
                func.coalesce(counts.c.sales, 0).label("sales"),
            )
            .select_from(SaleBranchModel)
            .outerjoin(AgentModel, AgentModel.id == SaleBranchModel.agent_id)
            .outerjoin(counts, counts.c.branch == SaleBranchModel.branch)
            .order_by(func.coalesce(counts.c.sales, 0).desc(), SaleBranchModel.branch)
        )
    ).all()

    return [
        BranchRow(
            branch=row.branch,
            agent_id=row.agent_id,
            agent_name=row.agent_name,
            matched_automatically=row.matched_automatically,
            sales=row.sales,
        )
        for row in rows
    ]


async def assign_branch(
    session: AsyncSession, branch: str, agent_id: UUID | None
) -> BranchRow:
    """Filialga xodimni QO'LDA biriktiradi (yoki bo'shatadi).

    Uch ish bajariladi va uchalasi ham zarur:

      1. `matched_automatically = False` — bu odamning qarori. Keyingi
         importlar bu qatorga TEGMAYDI (`ON CONFLICT DO NOTHING`), ya'ni
         rahbarning qo'yganini tizim jimgina almashtirib yubormaydi.
      2. Shu filialdagi savdolar YANGI xodimga o'tkaziladi. ⚠️ Faqat
         `backfill_sale_links()` yetarli EMAS: u faqat BO'SH
         `agent_id` ni to'ldiradi, ya'ni xato biriktirishni tuzatganda
         eski savdolar eski xodimda qolib ketardi va hisobot
         yolg'onga aylanardi. Filial → xodim xaritasi yagona manba,
         demak savdolar unga ERGASHADI.
      3. `backfill_sale_links()` baribir chaqiriladi — u telefon
         bog'lanishini ham tiklaydi (katalog registrdan keyin
         yuklangan bo'lishi mumkin).
    """
    row = await session.get(SaleBranchModel, branch)
    if row is None:
        raise NotFoundError(f"«{branch}» filiali topilmadi")

    if agent_id is not None:
        agent = await session.get(AgentModel, agent_id)
        if agent is None:
            raise NotFoundError("Xodim topilmadi")

    row.agent_id = agent_id
    row.matched_automatically = False

    await session.execute(
        update(SaleModel).where(SaleModel.branch == branch).values(agent_id=agent_id)
    )
    await backfill_sale_links(session)
    await session.commit()

    sales = (
        await session.execute(
            select(func.count())
            .select_from(SaleModel)
            .where(SaleModel.branch == branch)
            .where(SaleModel.op_type == SaleOpType.SALE.value)
        )
    ).scalar_one()
    name = None
    if agent_id is not None:
        name = (
            await session.execute(
                select(AgentModel.full_name).where(AgentModel.id == agent_id)
            )
        ).scalar_one_or_none()

    return BranchRow(
        branch=branch,
        agent_id=agent_id,
        agent_name=name,
        matched_automatically=False,
        sales=sales,
    )
