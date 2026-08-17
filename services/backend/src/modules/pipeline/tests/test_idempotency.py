"""Quvur idempotentligi — qayta yurish IKKINCHI bahoni yaratmaydi.

NEGA MUHIM: qayta ishga tushirish — kundalik holat (worker qayta
yuklandi, admin «qayta urinish» ni bosdi, Celery vazifani takrorladi).
Agar har yurish yangi baho qatori yaratsa:

  · statistika buziladi — bitta qo'ng'iroq o'rtachaga ikki marta kiradi,
  · pul ikki marta sarflanadi (ASR + LLM chaqiruvlari),
  · «qaysi baho haqiqiy?» degan javobsiz savol paydo bo'ladi.

Himoya IKKI qatlamda:
  1. Kod — `existing_score()` bor qatorni topadi va USTIGA yozadi.
  2. Baza — `call_scores.call_id` UNIQUE: kod xato qilsa ham ikkinchi
     qator YOZILMAYDI (`IntegrityError`).

Bu fayl ikkala qatlamni ham tekshiradi. Ma'lumot `dataset` bilan
yaratiladi va test oxirida kaskad bilan o'chadi.
"""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.core.database import SessionFactory
from src.modules.pipeline.tests.stubs import build_payload
from src.modules.scoring.application.review_rules import ReviewDecision
from src.modules.scoring.application.score_writer import existing_score, save_score
from src.modules.scoring.application.validator import validate
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC
from src.modules.scoring.infrastructure.models import CallScoreModel

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]


def _draft(seed: int):
    raw = json.dumps(build_payload(BLOCKS, FLAGS, seed=seed), ensure_ascii=False)
    return validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)


async def _score_count(call_id) -> int:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(CallScoreModel)
                .where(CallScoreModel.call_id == call_id)
            )
        ).scalar_one()


# ══════════════════════════════════════════════════════════════
#  Baza qatlami — UNIQUE cheklov
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ikkinchi_baho_qatori_baza_darajasida_rad_etiladi(dataset) -> None:
    """Kod chetlab o'tsa ham baza ikkinchi bahoni QABUL QILMAYDI."""
    data = await dataset(scores=[85])
    call_id = data.calls[0].call_id

    assert await _score_count(call_id) == 1

    async with SessionFactory() as session:
        session.add(
            CallScoreModel(
                call_id=call_id,
                model="test-model-2",
                rubric_version="v1",
                overall_score=42,
                blocks={"script": 10},
                red_flags=[],
                confidence=0.5,
                needs_review=False,
            )
        )
        with pytest.raises(IntegrityError) as exc:
            await session.commit()

        await session.rollback()

    assert "call_id" in str(exc.value), "UNIQUE cheklov aynan `call_id` da bo'lsin"
    # Mavjud baho tegilmagan
    assert await _score_count(call_id) == 1


# ══════════════════════════════════════════════════════════════
#  Kod qatlami — `save_score()` ustiga yozadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qayta_baholash_mavjud_qatorni_ustiga_yozadi(dataset) -> None:
    """Ikkinchi yurish — yangi qator emas, o'sha qatorning yangilanishi."""
    data = await dataset(scores=[85])
    call_id = data.calls[0].call_id

    first = _draft(seed=1)
    second = _draft(seed=2)

    async with SessionFactory() as session:
        row = await save_score(
            session,
            call_id=call_id,
            draft=first,
            review=ReviewDecision(needs_review=False),
            model="stub-haiku",
            rubric_version="v1",
        )
        first_row_id = row.id
        await session.commit()

    async with SessionFactory() as session:
        row = await save_score(
            session,
            call_id=call_id,
            draft=second,
            review=ReviewDecision(needs_review=True, reasons=[
                {"code": "low_confidence", "message": "AI ishonchi past"}
            ]),
            model="stub-haiku",
            rubric_version="v1",
        )
        await session.commit()
        second_row_id = row.id

    assert await _score_count(call_id) == 1
    assert second_row_id == first_row_id, "Yangi qator EMAS — o'shasi yangilandi"

    async with SessionFactory() as session:
        stored = await existing_score(session, call_id)

    assert stored is not None
    assert stored.overall_score == second.overall
    assert stored.needs_review is True
    assert stored.review_reasons[0]["code"] == "low_confidence"


@pytest.mark.asyncio
async def test_existing_score_bahoni_topadi_yoqda_none_qaytaradi(dataset) -> None:
    """`unscored_calls` — bahosi YO'Q qo'ng'iroq, `None` kutiladi."""
    data = await dataset(scores=[70], unscored_calls=1)

    async with SessionFactory() as session:
        found = await existing_score(session, data.calls[0].call_id)

    assert found is not None
    assert found.overall_score == 70


@pytest.mark.asyncio
async def test_bahosiz_qongiroqda_existing_score_none(dataset) -> None:
    from uuid import uuid4

    await dataset(scores=[])

    async with SessionFactory() as session:
        assert await existing_score(session, uuid4()) is None


@pytest.mark.asyncio
async def test_uch_marta_yurish_ham_bitta_qator_qoldiradi(dataset) -> None:
    """Vazifa uch marta takrorlansa ham — statistikada bitta qo'ng'iroq."""
    data = await dataset(scores=[60])
    call_id = data.calls[0].call_id

    for seed in (3, 4, 5):
        async with SessionFactory() as session:
            await save_score(
                session,
                call_id=call_id,
                draft=_draft(seed=seed),
                review=ReviewDecision(needs_review=False),
                model="stub-haiku",
                rubric_version="v1",
            )
            await session.commit()

    assert await _score_count(call_id) == 1
