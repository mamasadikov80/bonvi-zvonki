"""Navbatga qo'yish va navbat holatini o'qish.

«Navbat qotib qoldimi?» degan savolga JAVOB BERADIGAN joy. Uchta
manba birlashtiriladi:

  · Redis — kutayotgan vazifalar soni (broker navbati uzunligi)
  · Celery — hozir bajarilayotgan vazifalar (workerlardan so'raladi)
  · Baza  — bosqichlar bo'yicha holat, o'tkazuvchanlik, xatolar

Worker o'chiq bo'lsa ham endpoint ISHLAYDI: `workers: 0` va navbat
uzunligi ko'rinadi — bu aynan admin bilishi kerak bo'lgan holat.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.orchestrator import resolve_min_duration
from src.modules.pipeline.domain.config import load_config
from src.modules.pipeline.domain.entities import PipelineStage
from src.modules.pipeline.infrastructure.models import CallPipelineStateModel
from src.modules.scoring.infrastructure.models import CallScoreModel

log = structlog.get_logger(__name__)

TASK_PROCESS_CALL = "pipeline.process_call"


def enqueue_calls(call_ids: list[UUID], *, force: bool = False) -> list[str]:
    """Har qo'ng'iroq uchun bitta vazifa. Vazifa id'lari qaytadi."""
    from src.worker import PIPELINE_QUEUE, celery_app

    task_ids: list[str] = []
    for call_id in call_ids:
        result = celery_app.send_task(
            TASK_PROCESS_CALL,
            args=[str(call_id), force],
            queue=PIPELINE_QUEUE,
        )
        task_ids.append(result.id)
    return task_ids


async def broker_depth() -> int | None:
    """Navbatda kutayotgan vazifalar. Redis yo'q bo'lsa — `None`."""
    try:
        from redis.asyncio import from_url

        from src.worker import BROKER_URL, PIPELINE_QUEUE

        client = from_url(BROKER_URL, decode_responses=True)
        try:
            return int(await client.llen(PIPELINE_QUEUE))
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline.broker_depth_failed", error=str(exc))
        return None


# Bitta `inspect` chaqiruvining kutish vaqti (soniya)
INSPECT_TIMEOUT = 1.5


def _inspect() -> dict[str, Any]:
    """Celery'dan workerlarni so'raydi (sinxron, shuning uchun threadda).

    Har bir `inspect` chaqiruvi broker orqali broadcast qiladi va o'z
    kutish vaqtiga ega. Ikkitasi ketma-ket chaqirilgani uchun tashqi
    chegara ularning yig'indisidan kattaroq bo'lishi shart — aks holda
    worker sog'lom bo'lsa ham «worker yo'q» deb ko'rsatiladi.
    """
    from src.worker import celery_app

    inspector = celery_app.control.inspect(timeout=INSPECT_TIMEOUT)
    active = inspector.active() or {}
    reserved = inspector.reserved() or {}
    # `active` bo'sh ro'yxat qaytarsa ham worker BOR: {'worker@worker': []}
    names = sorted(set(active) | set(reserved))
    return {
        "workers": names,
        "active": sum(len(v) for v in active.values()),
        "reserved": sum(len(v) for v in reserved.values()),
    }


async def worker_snapshot() -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_inspect), timeout=INSPECT_TIMEOUT * 2 + 3.0
        )
    except Exception as exc:  # noqa: BLE001
        # `TimeoutError` ning matni bo'sh — turini ham yozamiz, aks holda
        # logda «error=» dan boshqa hech narsa qolmaydi
        log.warning(
            "pipeline.inspect_failed",
            error=str(exc) or type(exc).__name__,
            kind=type(exc).__name__,
        )
        return {"workers": [], "active": None, "reserved": None}


async def db_snapshot(session: AsyncSession) -> dict[str, Any]:
    stages = {
        stage: 0
        for stage in (
            PipelineStage.QUEUED.value,
            PipelineStage.TRANSCRIBING.value,
            PipelineStage.SCORING.value,
            PipelineStage.COMPLETED.value,
            PipelineStage.FAILED.value,
            PipelineStage.SKIPPED.value,
        )
    }
    rows = (
        await session.execute(
            select(CallPipelineStateModel.stage, func.count())
            .group_by(CallPipelineStateModel.stage)
        )
    ).all()
    for stage, count in rows:
        stages[stage] = int(count)

    now = datetime.now(UTC)
    scored_hour = (
        await session.execute(
            select(func.count()).select_from(CallPipelineStateModel).where(
                CallPipelineStateModel.scored_at >= now - timedelta(hours=1)
            )
        )
    ).scalar_one()
    scored_15m = (
        await session.execute(
            select(func.count()).select_from(CallPipelineStateModel).where(
                CallPipelineStateModel.scored_at >= now - timedelta(minutes=15)
            )
        )
    ).scalar_one()

    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(CallPipelineStateModel.asr_calls), 0),
                func.coalesce(func.sum(CallPipelineStateModel.llm_calls), 0),
                func.coalesce(func.sum(CallPipelineStateModel.audio_bytes), 0),
            )
        )
    ).one()

    review_pending = (
        await session.execute(
            select(func.count())
            .select_from(CallScoreModel)
            .where(CallScoreModel.needs_review.is_(True))
        )
    ).scalar_one()

    return {
        "stages": stages,
        "scored_last_hour": int(scored_hour),
        "scored_last_15min": int(scored_15m),
        "per_minute_15min": round(int(scored_15m) / 15.0, 2),
        "asr_calls_total": int(totals[0]),
        "llm_calls_total": int(totals[1]),
        "audio_bytes_streamed": int(totals[2]),
        "needs_review_pending": int(review_pending),
    }


async def recent_failures(
    session: AsyncSession, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Oxirgi nosozliklar — sababi bilan. Admin shu ro'yxatni o'qiydi."""
    rows = (
        await session.execute(
            select(
                CallPipelineStateModel.call_id,
                CallPipelineStateModel.error_stage,
                CallPipelineStateModel.error_code,
                CallPipelineStateModel.error_message,
                CallPipelineStateModel.attempts,
                CallPipelineStateModel.last_run_at,
                CallModel.external_id,
                CallModel.started_at,
            )
            .join(CallModel, CallModel.id == CallPipelineStateModel.call_id)
            .where(CallPipelineStateModel.stage == PipelineStage.FAILED.value)
            .order_by(CallPipelineStateModel.last_run_at.desc())
            .limit(limit)
        )
    ).all()

    return [
        {
            "call_id": row.call_id,
            "external_id": row.external_id,
            "started_at": row.started_at,
            "stage": row.error_stage,
            "code": row.error_code,
            "reason": row.error_message,
            "attempts": row.attempts,
            "last_run_at": row.last_run_at,
        }
        for row in rows
    ]


async def full_status(session: AsyncSession) -> dict[str, Any]:
    config = load_config()
    # ⚠️ `config.min_duration_sec` — MUHIT qiymati, quvur esa SOZLAMANI
    # ishlatadi. Ular farq qilardi (30 va 10) va admin holat panelida
    # 30 ni ko'rib «10–29 soniyali qo'ng'iroqlar baholanmaydi» degan
    # xulosaga kelardi — aslida baholanardi. `resolve_min_duration`
    # aynan shu ikkilanishni yo'q qilish uchun yozilgan edi, bu joy
    # esa e'tibordan chetda qolgan.
    min_duration = await resolve_min_duration(session, config)
    depth, workers, database = await asyncio.gather(
        broker_depth(), worker_snapshot(), db_snapshot(session)
    )
    return {
        "queue_depth": depth,
        "workers": workers["workers"],
        "worker_count": len(workers["workers"]),
        "active_tasks": workers["active"],
        "reserved_tasks": workers["reserved"],
        "limits": {
            "concurrency": config.concurrency,
            "asr_rpm": config.asr_rpm,
            "llm_rpm": config.llm_rpm,
            "max_retries": config.max_retries,
            "min_duration_sec": min_duration,
        },
        **database,
    }
