"""Tekshiruv navbati — rahbarning qarori.

Bazada saqlanadigan YAGONA subyektiv yozuv shu. Qoidaning natijasi
(«shubhali») saqlanmaydi, chunki u qo'ng'iroqlar sinxronlanishi bilan
o'zgarishi mumkin (`compliance.py` ning bosh izohiga qarang). Odamning
qarori esa o'zgarmaydi: «kelib oldi», «Telegram orqali kelishdik» —
bu fakt, hisob-kitob emas.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.sales.domain.entities import SaleReviewReason, SaleReviewStatus
from src.modules.sales.infrastructure.models import SaleModel, SaleReviewModel
from src.modules.users.infrastructure.models import UserModel


@dataclass(slots=True)
class ReviewResult:
    sale_id: UUID
    status: str
    reason: str | None
    note: str | None
    reviewed_by: str | None
    reviewed_at: datetime


async def save_review(
    session: AsyncSession,
    sale_id: UUID,
    *,
    status: SaleReviewStatus,
    reason: SaleReviewReason | None,
    note: str | None,
    user_id: UUID | None,
) -> ReviewResult:
    """Qarorni yozadi. Bir savdoga BITTA qaror — takrori ustiga yoziladi.

    ⚠️ FIKR O'ZGARISHI NORMAL HOLAT. Rahbar «oqlandi» deb qo'yib, keyin
    xodim bilan gaplashib «haqiqatan shubhali» deb o'zgartirishi
    mumkin. Shuning uchun jadvalda tarix emas, OXIRGI qaror turadi va
    `sale_id` unikal: ikkinchi qator paydo bo'lsa, ro'yxatda savdo ikki
    marta ko'rinardi.

    Kim va qachon qo'ygani HAR DOIM yoziladi — qaror shaxssiz bo'lsa,
    uni muhokama qilib ham bo'lmaydi.
    """
    exists = (
        await session.execute(select(SaleModel.id).where(SaleModel.id == sale_id))
    ).scalar_one_or_none()
    if exists is None:
        raise NotFoundError("Savdo topilmadi")

    # ⚠️ «Haqiqatan shubhali» qarorida sabab YO'Q: sabablar ro'yxati
    # («kelib oldi», «Telegram»…) aynan OQLASHNI tushuntirish uchun
    # tuzilgan. Tasdiqlangan shubha uchun izoh maydoni bor.
    stored_reason = reason.value if (reason and status is SaleReviewStatus.JUSTIFIED) else None
    cleaned = (note or "").strip() or None

    stmt = (
        pg_insert(SaleReviewModel)
        .values(
            id=uuid4(),
            sale_id=sale_id,
            status=status.value,
            reason=stored_reason,
            note=cleaned,
            reviewed_by=user_id,
            reviewed_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[SaleReviewModel.sale_id],
            set_={
                "status": status.value,
                "reason": stored_reason,
                "note": cleaned,
                "reviewed_by": user_id,
                "reviewed_at": func.now(),
            },
        )
        .returning(SaleReviewModel.reviewed_at)
    )
    reviewed_at = (await session.execute(stmt)).scalar_one()

    name = None
    if user_id is not None:
        name = (
            await session.execute(
                select(UserModel.full_name).where(UserModel.id == user_id)
            )
        ).scalar_one_or_none()
    await session.commit()

    return ReviewResult(
        sale_id=sale_id,
        status=status.value,
        reason=stored_reason,
        note=cleaned,
        reviewed_by=name,
        reviewed_at=reviewed_at,
    )
