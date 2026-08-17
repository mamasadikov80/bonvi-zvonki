"""Celery vazifalari — navbatning yagona kirish nuqtasi.

Vazifa juda yupqa: qulf, idempotentlik va xato yozish dirijyorda
(`orchestrator`). Bu yerda faqat «asinxronni sinxronga o'rash» va
qayta urinish siyosati.
"""

from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from src.modules.pipeline.application.orchestrator import PipelineOrchestrator
from src.modules.pipeline.application.runner import run_async
from src.modules.pipeline.domain.entities import PipelineStage

log = structlog.get_logger(__name__)

#: Infratuzilma nosozligida (baza yiqildi, Redis yo'q) shuncha marta
#: qayta uriniladi. Vendor xatolari bunga kirmaydi — ular dirijyorda
#: ushlanadi va sabab sifatida yoziladi.
INFRA_RETRIES = 3


@shared_task(
    name="pipeline.process_call",
    bind=True,
    acks_late=True,
    max_retries=INFRA_RETRIES,
    default_retry_delay=30,
)
def process_call_task(self: Any, call_id: str, force: bool = False) -> dict[str, Any]:
    """Bitta qo'ng'iroqni transkripsiya qiladi va baholaydi."""
    orchestrator = PipelineOrchestrator()
    try:
        outcome = run_async(orchestrator.process_call(UUID(call_id), force=force))
    except Exception as exc:  # noqa: BLE001 — bu yerga faqat infra xatolari yetadi
        log.error("task.infra_error", call_id=call_id, error=str(exc))
        raise self.retry(exc=exc) from exc

    return {
        "call_id": call_id,
        "stage": outcome.stage.value,
        "score": outcome.overall_score,
        "needs_review": outcome.needs_review,
        "asr_calls": outcome.asr_calls,
        "llm_calls": outcome.llm_calls,
        "elapsed_ms": outcome.elapsed_ms,
        "error_code": outcome.error_code,
        "error": outcome.error_message,
    }


@shared_task(name="pipeline.process_batch", acks_late=True)
def process_batch_task(call_ids: list[str], force: bool = False) -> dict[str, Any]:
    """Ro'yxatni BITTA vazifada, cheklangan parallellik bilan yuritadi.

    Kichik guruhlar va sinov uchun qulay: navbatga yuzlab vazifa
    tashlashdan ko'ra bitta vazifa ichida `asyncio` bilan yurgan
    tezroq (I/O kutishi ustma-ust tushadi).
    """
    orchestrator = PipelineOrchestrator()
    report = run_async(
        orchestrator.run_batch([UUID(cid) for cid in call_ids], force=force)
    )
    return report.as_dict()


@shared_task(name="pipeline.health")
def health_task() -> dict[str, str]:
    """Worker tirikligini tekshirish uchun eng arzon vazifa."""
    return {"status": "ok", "stage": PipelineStage.QUEUED.value}
