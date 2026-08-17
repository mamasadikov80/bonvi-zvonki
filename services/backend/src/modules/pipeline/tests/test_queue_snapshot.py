"""`queue.db_snapshot()` — «navbat qotib qoldimi?» degan savolning javobi.

NEGA MUHIM: admin quvurni faqat shu raqamlar orqali ko'radi. Bosqich
sanog'i yoki o'tkazuvchanlik noto'g'ri hisoblansa, to'xtagan navbat
sog'lom ko'rinadi va baholanmagan qo'ng'iroqlar jimgina yig'ilib
boraveradi.

⚠️ IZOLYATSIYA
  `db_snapshot()` BUTUN jadval bo'yicha hisoblaydi — uni `agent_id`
  bilan filtrlab bo'lmaydi. Shuning uchun aniq raqam kutadigan testlar
  TRANZAKSIYA ichida ishlaydi: jadval tozalanadi, o'z qatorlari
  qo'yiladi, o'lchov olinadi va oxirida `rollback()` — bazada hech
  qanday iz qolmaydi. Mavjud yozuvlar o'chirilmaydi.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from src.core.database import SessionFactory
from src.modules.pipeline.application.queue import db_snapshot
from src.modules.pipeline.domain.entities import PipelineStage
from src.modules.pipeline.infrastructure.models import CallPipelineStateModel

#: `db_snapshot()` HAR DOIM shu kalitlarni beradi — nol bo'lsa ham.
#: Frontend ularni kutadi: yo'q kalit grafikda «—» emas, xato beradi.
KUTILGAN_BOSQICHLAR = {
    "queued",
    "transcribing",
    "scoring",
    "completed",
    "failed",
    "skipped",
}


def _state(call_id, stage: str, **kwargs) -> CallPipelineStateModel:
    return CallPipelineStateModel(call_id=call_id, stage=stage, **kwargs)


@pytest.mark.asyncio
async def test_bosh_jadvalda_hamma_son_nol() -> None:
    """Yangi o'rnatilgan tizim — 500 emas, tartibli nol ko'rsatilsin."""
    async with SessionFactory() as session:
        try:
            await session.execute(delete(CallPipelineStateModel))

            snapshot = await db_snapshot(session)

            assert set(snapshot["stages"]) == KUTILGAN_BOSQICHLAR
            assert all(value == 0 for value in snapshot["stages"].values())
            assert snapshot["scored_last_hour"] == 0
            assert snapshot["scored_last_15min"] == 0
            assert snapshot["per_minute_15min"] == 0.0
            assert snapshot["asr_calls_total"] == 0
            assert snapshot["llm_calls_total"] == 0
            assert snapshot["audio_bytes_streamed"] == 0
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_bosqichlar_boyicha_sanaladi(dataset) -> None:
    """Uch xil bosqich — har biri o'z ustuniga tushishi kerak."""
    data = await dataset(scores=[90, 80, 70, 60])
    stages = [
        PipelineStage.COMPLETED.value,
        PipelineStage.COMPLETED.value,
        PipelineStage.FAILED.value,
        PipelineStage.SKIPPED.value,
    ]

    async with SessionFactory() as session:
        try:
            await session.execute(delete(CallPipelineStateModel))
            for call, stage in zip(data.calls, stages, strict=True):
                session.add(_state(call.call_id, stage))
            await session.flush()

            snapshot = await db_snapshot(session)

            assert snapshot["stages"]["completed"] == 2
            assert snapshot["stages"]["failed"] == 1
            assert snapshot["stages"]["skipped"] == 1
            # Ishlatilmagan bosqichlar YO'QOLMAYDI — nol bo'lib qoladi
            assert snapshot["stages"]["queued"] == 0
            assert snapshot["stages"]["transcribing"] == 0
            assert snapshot["stages"]["scoring"] == 0
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_per_minute_15min_uchdan_bir_qismga_bolinadi(dataset) -> None:
    """3 ta baho / 15 daqiqa = 0.2 ta daqiqasiga."""
    data = await dataset(scores=[90, 80, 70])
    now = datetime.now(UTC)

    async with SessionFactory() as session:
        try:
            await session.execute(delete(CallPipelineStateModel))
            for call in data.calls:
                session.add(
                    _state(
                        call.call_id,
                        PipelineStage.COMPLETED.value,
                        scored_at=now - timedelta(minutes=2),
                        asr_calls=1,
                        llm_calls=2,
                        audio_bytes=1_000,
                    )
                )
            await session.flush()

            snapshot = await db_snapshot(session)

            assert snapshot["scored_last_15min"] == 3
            assert snapshot["scored_last_hour"] == 3
            assert snapshot["per_minute_15min"] == 0.2
            assert snapshot["per_minute_15min"] == round(3 / 15.0, 2)
            # Pul turgan chaqiruvlar ham yig'iladi
            assert snapshot["asr_calls_total"] == 3
            assert snapshot["llm_calls_total"] == 6
            assert snapshot["audio_bytes_streamed"] == 3_000
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_eski_baho_15_daqiqa_oynasiga_kirmaydi(dataset) -> None:
    """20 daqiqa oldingi baho «hozirgi tezlik» ni ko'tarmasligi kerak."""
    data = await dataset(scores=[90, 80])
    now = datetime.now(UTC)

    async with SessionFactory() as session:
        try:
            await session.execute(delete(CallPipelineStateModel))
            session.add(
                _state(
                    data.calls[0].call_id,
                    PipelineStage.COMPLETED.value,
                    scored_at=now - timedelta(minutes=20),
                )
            )
            session.add(
                _state(
                    data.calls[1].call_id,
                    PipelineStage.COMPLETED.value,
                    scored_at=now - timedelta(hours=3),
                )
            )
            await session.flush()

            snapshot = await db_snapshot(session)

            assert snapshot["scored_last_15min"] == 0
            assert snapshot["per_minute_15min"] == 0.0
            # 20 daqiqalik hali soatlik oynada
            assert snapshot["scored_last_hour"] == 1
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_bahosiz_qator_otkazuvchanlikka_qoshilmaydi(dataset) -> None:
    """Navbatda turgan (`scored_at is None`) qo'ng'iroq hali sanalmaydi."""
    data = await dataset(scores=[90])

    async with SessionFactory() as session:
        try:
            await session.execute(delete(CallPipelineStateModel))
            session.add(_state(data.calls[0].call_id, PipelineStage.QUEUED.value))
            await session.flush()

            snapshot = await db_snapshot(session)

            assert snapshot["stages"]["queued"] == 1
            assert snapshot["scored_last_hour"] == 0
            assert snapshot["scored_last_15min"] == 0
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_haqiqiy_bazada_hamma_kalit_va_manfiy_bolmagan_sonlar() -> None:
    """Tranzaksiyasiz, HAQIQIY holat: shakl har doim to'g'ri bo'lsin."""
    async with SessionFactory() as session:
        snapshot = await db_snapshot(session)

    assert set(snapshot["stages"]) == KUTILGAN_BOSQICHLAR
    assert all(isinstance(v, int) and v >= 0 for v in snapshot["stages"].values())

    for key in (
        "scored_last_hour",
        "scored_last_15min",
        "asr_calls_total",
        "llm_calls_total",
        "audio_bytes_streamed",
        "needs_review_pending",
    ):
        assert isinstance(snapshot[key], int), f"«{key}» butun son bo'lishi kerak"
        assert snapshot[key] >= 0

    # 15 daqiqalik oyna soatlik oynaning ICHIDA
    assert snapshot["scored_last_15min"] <= snapshot["scored_last_hour"]
    assert snapshot["per_minute_15min"] == round(
        snapshot["scored_last_15min"] / 15.0, 2
    )
