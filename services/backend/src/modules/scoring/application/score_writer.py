"""Bahoni bazaga yozish — idempotent.

`call_scores.call_id` UNIQUE: bitta qo'ng'iroqda bitta baho. Qayta
ishga tushirilgan vazifa ikkinchi qator YARATMAYDI — mavjudini
qaytaradi (yoki `force` bo'lsa ustiga yozadi).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.scoring.application.review_rules import ReviewDecision
from src.modules.scoring.application.validator import ScoreDraft
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.surveys.infrastructure.models import (
    SurveyModel,
    SurveyResponseModel,
)


async def existing_score(session: AsyncSession, call_id: UUID) -> CallScoreModel | None:
    return (
        await session.execute(
            select(CallScoreModel).where(CallScoreModel.call_id == call_id)
        )
    ).scalar_one_or_none()


async def delete_score(session: AsyncSession, call_id: UUID) -> bool:
    """Bahoni o'chiradi. `True` — qator bor edi va o'chirildi.

    ⚠️ NEGA BUNDAY FUNKSIYA BOR. Qo'ng'iroq turi aniqlangach ma'lum
    bo'lishi mumkin: bu savdo suhbati emas, demak savdo rubrikasi bilan
    baholanmasligi kerak. Lekin u ILGARI baholangan bo'lishi mumkin —
    turlar ajratilishidan oldin, yoki avval boshqa tur bilan.

    O'sha eski ballni qoldirish tizimni o'z-o'ziga ZID holatga soladi:
    ekranda «savdo emas, baholanmaydi» deb turadi, analitikada esa ball
    hisobga olinib, xodimning o'rtachasini pasaytiraveradi. Baho —
    hisoblanadigan ma'lumot va uni qayta olish mumkin; yolg'on
    ko'rsatkichni esa hech kim sezmaydi.
    """
    row = await existing_score(session, call_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def save_score(
    session: AsyncSession,
    *,
    call_id: UUID,
    draft: ScoreDraft,
    review: ReviewDecision,
    model: str,
    rubric_version: str,
    cost_usd: float | None = None,
) -> CallScoreModel:
    """Bahoni yozadi. Mavjud qator bo'lsa ustiga yoziladi (qayta baholash)."""
    row = await existing_score(session, call_id)
    if row is None:
        row = CallScoreModel(call_id=call_id)
        session.add(row)

    row.model = model[:64]
    row.rubric_version = rubric_version[:16]
    row.overall_score = draft.overall
    row.blocks = _blocks_payload(draft)
    row.block_details = _block_details_payload(draft)
    row.red_flags = draft.red_flags
    row.outcome_signal = draft.outcome_signal
    row.sentiment = draft.sentiment
    row.coaching_note = draft.coaching_note
    row.confidence = draft.confidence
    row.needs_review = review.needs_review
    row.review_reasons = review.reasons
    row.scored_at = datetime.now(UTC)
    row.cost_usd = cost_usd

    await session.flush()
    return row


def _blocks_payload(draft: ScoreDraft) -> dict[str, int]:
    """`call_scores.blocks` — TEKIS `{blok_kaliti: ball}`.

    Iste'molchilar aynan shu shaklni kutadi va boshqasini ko'tara olmaydi:
    analitikadagi razrez har qiymatni `float(value)` qiladi (obyekt kelsa
    `TypeError` → 500), qo'ng'iroq tafsiloti sahifasi esa qiymatni to'g'ridan
    to'g'ri chizadi (obyekt kelsa React sahifani umuman ochmaydi).

    Shuning uchun bu yerga NA ichma-ich obyekt, NA `_meta` kabi qo'shimcha
    kalit tushmaydi — `_meta` razrezda beshinchi «blok» bo'lib chiqardi.
    Dalillar va hisob-kitob izohi alohida ustunda: `block_details`.
    """
    return dict(draft.block_scores)


def _block_details_payload(draft: ScoreDraft) -> dict[str, Any]:
    """`call_scores.block_details` — dalillar va hisob-kitob izohi.

    `meta` ni saqlaymiz, chunki keyinchalik «nega 78?» degan savolga
    javob berish uchun jarima va yig'indi qayta hisoblanmasin.
    """
    return {
        "blocks": draft.blocks,
        "meta": {
            "blocks_total": draft.blocks_total,
            "penalty_total": draft.penalty_total,
            "zeroed_by_red_flag": draft.zeroed,
            "language_detected": draft.language_detected,
            "transcript_quality": draft.transcript_quality,
        },
    }


async def agent_client_rating(
    session: AsyncSession, agent_id: UUID, *, days: int = 90
) -> tuple[float | None, int]:
    """Xodimning so'nggi mijoz bahosi (1..5) va javoblar soni.

    `needs_review` ning to'rtinchi qoidasi shu ikki songa tayanadi:
    AI bahosi mijoz bahosidan keskin farq qilsa — biri xato.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    row = (
        await session.execute(
            select(
                func.avg(SurveyResponseModel.csat),
                func.count(SurveyResponseModel.id),
            )
            .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
            .where(
                SurveyModel.agent_id == agent_id,
                SurveyResponseModel.responded_at >= since,
            )
        )
    ).one()

    average, count = row
    return (float(average) if average is not None else None), int(count or 0)
