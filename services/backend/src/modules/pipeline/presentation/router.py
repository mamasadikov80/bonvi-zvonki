"""Quvur endpointlari — admin ishga tushiradi va kuzatadi.

    POST /pipeline/run            sana oralig'ini navbatga qo'yadi
    GET  /pipeline/status         navbat, workerlar, o'tkazuvchanlik
    GET  /pipeline/failures       nosozliklar — o'zbekcha sabab bilan
    POST /pipeline/calls/{id}/retry   bitta qo'ng'iroqni qayta yuborish

`agents:sync` ruxsati talab qilinadi: bu tugma PUL SARFLAYDI (ASR va
LLM chaqiruvlari), shuning uchun MoyZvonki sinxronizatsiyasi bilan bir
xil darajada himoyalangan — sukut bo'yicha faqat admin.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession, require_permission
from src.core.exceptions import NotFoundError, ValidationError
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.orchestrator import select_calls
from src.modules.pipeline.application.queue import (
    enqueue_calls,
    full_status,
    recent_failures,
)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

MAX_BATCH = 5_000


class RunRequest(BaseModel):
    date_from: datetime = Field(description="Boshlanish sanasi (ISO)")
    date_to: datetime = Field(description="Tugash sanasi (ISO)")
    #: `false` — allaqachon baholanganlar ham qayta baholanadi (qimmat!)
    only_unscored: bool = True
    #: Bahoni ustiga yozadi va transkriptni qayta oladi — ehtiyot bo'ling
    force: bool = False
    limit: int = Field(default=500, ge=1, le=MAX_BATCH)
    agent_ids: list[UUID] | None = None


class RunResponse(BaseModel):
    queued: int
    date_from: datetime
    date_to: datetime
    force: bool
    task_ids: list[str]
    message: str


@router.post(
    "/run",
    response_model=RunResponse,
    summary="Sana oralig'idagi qo'ng'iroqlarni baholashga qo'yish",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def run_range(payload: RunRequest, session: DbSession) -> RunResponse:
    if payload.date_to < payload.date_from:
        raise ValidationError("Tugash sanasi boshlanish sanasidan oldin bo'lolmaydi")

    call_ids = await select_calls(
        session,
        date_from=payload.date_from,
        date_to=payload.date_to,
        only_unscored=payload.only_unscored and not payload.force,
        limit=payload.limit,
        agent_ids=payload.agent_ids,
    )

    if not call_ids:
        return RunResponse(
            queued=0,
            date_from=payload.date_from,
            date_to=payload.date_to,
            force=payload.force,
            task_ids=[],
            message=(
                "Bu oraliqda baholanadigan qo'ng'iroq topilmadi — hammasi "
                "baholangan yoki yozuvi yo'q"
            ),
        )

    task_ids = enqueue_calls(call_ids, force=payload.force)

    return RunResponse(
        queued=len(task_ids),
        date_from=payload.date_from,
        date_to=payload.date_to,
        force=payload.force,
        task_ids=task_ids[:20],
        message=(
            f"{len(task_ids)} ta qo'ng'iroq navbatga qo'yildi. "
            "Holatni «Quvur holati» bo'limida kuzating."
        ),
    )


@router.post(
    "/calls/{call_id}/retry",
    response_model=RunResponse,
    summary="Bitta qo'ng'iroqni qayta baholashga yuborish",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def retry_call(
    call_id: UUID, session: DbSession, force: bool = False
) -> RunResponse:
    call = await session.get(CallModel, call_id)
    if call is None:
        raise NotFoundError("Qo'ng'iroq topilmadi")

    task_ids = enqueue_calls([call_id], force=force)
    return RunResponse(
        queued=1,
        date_from=call.started_at,
        date_to=call.started_at,
        force=force,
        task_ids=task_ids,
        message="Qo'ng'iroq navbatga qo'yildi",
    )


@router.get(
    "/status",
    summary="Navbat holati: kutayotganlar, workerlar, o'tkazuvchanlik",
    dependencies=[Depends(require_permission("scores:read"))],
)
async def status(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    snapshot = await full_status(session)
    snapshot["checked_at"] = datetime.now(UTC)
    return snapshot


class FailureItem(BaseModel):
    call_id: UUID
    external_id: str | None
    started_at: datetime
    stage: str | None
    code: str | None
    reason: str | None
    attempts: int
    last_run_at: datetime | None


@router.get(
    "/failures",
    response_model=list[FailureItem],
    summary="Baholanmagan qo'ng'iroqlar va sababi",
    dependencies=[Depends(require_permission("scores:read"))],
)
async def failures(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[FailureItem]:
    rows = await recent_failures(session, limit=limit)
    return [FailureItem(**row) for row in rows]
