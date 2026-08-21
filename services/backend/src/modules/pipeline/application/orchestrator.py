"""Quvur dirijyori — uch bosqichni birlashtiradi va HOLATNI yozadi.

Tartib: **tur → transkript → baho**, ya'ni arzondan qimmatga.
Tur raqam bo'yicha aniqlanadi (bepul), transkript ASR ga boradi,
baholash esa faqat SAVDO qo'ng'irog'i uchun ishlaydi.

Qat'iy talablar shu yerda bajariladi:

  · **Idempotentlik** — qulf (Redis `SET NX`) + har bosqichda «bormi?»
    tekshiruvi. Qayta ishga tushirilgan vazifa ikkinchi baho qatorini
    ham, ikkinchi ASR hisobini ham yaratmaydi.
  · **Ko'rinadigan xato** — har nosozlik `call_pipeline_state` ga
    o'zbekcha sabab bilan yoziladi va `calls.status` FAILED bo'ladi.
    «Bo'sh baho va sababsiz qo'ng'iroq» holati bo'lishi mumkin emas.
  · **Cheklangan parallellik** — `run_batch` semaphore bilan ishlaydi,
    har qo'ng'iroq o'z sessiyasida (bir sessiya — bir tranzaksiya).
"""

import asyncio
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

import structlog
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionFactory
from src.core.exceptions import AppError, NotFoundError
from src.modules.calls.domain.entities import CallStatus, CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.route import RouteStage
from src.modules.pipeline.application.deps import PipelineDeps, default_deps
from src.modules.pipeline.application.score import ScoreStage
from src.modules.pipeline.application.transcribe import TranscribeStage
from src.modules.pipeline.domain.config import PipelineConfig, load_config
from src.modules.pipeline.domain.entities import (
    BatchReport,
    CallOutcome,
    CallTooShortError,
    DirectoryEmptyError,
    NoRecordingError,
    PipelineStage,
    Stage,
    StageResult,
)
from src.modules.pipeline.infrastructure.limits import CallLock
from src.modules.pipeline.infrastructure.models import CallPipelineStateModel
from src.modules.scoring.application.score_writer import delete_score, existing_score
from src.modules.settings.application.services import SettingsService

log = structlog.get_logger(__name__)

#: Baholanmaydigan TANISH turlar. Ro'yxat enumdan olinadi, qo'lda
#: sanalmaydi: yangi tur qo'shilsa u avtomatik shu yerga tushadi va
#: «yangi turni tanlovga qo'shishni unutdim» degan xato bo'lishi mumkin
#: emas. Faqat `SALES` baholanadi — bu qoida bitta joyda.
NOT_SCORABLE_TYPES = [tur.value for tur in CallType if tur is not CallType.SALES]


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        config: PipelineConfig | None = None,
        deps: PipelineDeps | None = None,
    ) -> None:
        self.config = config or load_config()
        self.deps = deps or default_deps()
        # ⚠️ TARTIB MUHIM: avval tur (bepul, raqam bo'yicha), keyin
        # transkript, eng oxirida baholash (eng qimmat bosqich).
        self.route_stage = RouteStage()
        self.transcribe_stage = TranscribeStage(self.deps, self.config)
        self.score_stage = ScoreStage(self.deps, self.config)

    # ── Bitta qo'ng'iroq ──────────────────────────────────────

    async def process_call(self, call_id: UUID, *, force: bool = False) -> CallOutcome:
        async with SessionFactory() as session:
            return await self.process_in_session(session, call_id, force=force)

    async def process_in_session(
        self, session: AsyncSession, call_id: UUID, *, force: bool = False
    ) -> CallOutcome:
        started = perf_counter()
        outcome = CallOutcome(call_id=call_id, stage=PipelineStage.QUEUED)

        async with CallLock(call_id, self.config.lock_ttl_sec) as lock:
            if not lock.acquired:
                # Boshqa worker shu qo'ng'iroqni ishlayapti — TEGMAYMIZ.
                # Aks holda ikkita ASR chaqiruvi va ikki marta to'lov.
                log.info("pipeline.locked", call_id=str(call_id))
                outcome.stage = PipelineStage.LOCKED
                outcome.error_code = "locked"
                outcome.error_message = "Boshqa worker shu qo'ng'iroqni ishlamoqda"
                return outcome

            call = await session.get(CallModel, call_id)
            if call is None:
                raise NotFoundError(f"Qo'ng'iroq topilmadi: {call_id}")

            state = await self._ensure_state(session, call_id)
            state.attempts += 1
            state.last_run_at = datetime.now(UTC)

            try:
                await self._run_stages(session, call, state, outcome, force=force)
            except (
                NoRecordingError,
                CallTooShortError,
                DirectoryEmptyError,
            ) as exc:
                # Baholanmaydi, lekin XATO emas — sabab yozib qo'yiladi.
                # `DirectoryEmptyError` VAQTINCHALIK holat: ro'yxat
                # sinxronizatsiyadan keyin to'ladi va qo'ng'iroq
                # keyingi yurishda normal ishlanadi.
                await self._mark_skipped(session, call, state, outcome, exc)
            except AppError as exc:
                await self._mark_failed(session, call, state, outcome, exc)
            except Exception as exc:  # noqa: BLE001 — kutilmagan xato ham ko'rinsin
                await self._mark_failed(session, call, state, outcome, exc)

            outcome.elapsed_ms = int((perf_counter() - started) * 1000)
            state.duration_ms = outcome.elapsed_ms
            await session.commit()
            return outcome

    async def _min_duration(self, session: AsyncSession) -> int:
        return await resolve_min_duration(session, self.config)

    async def _run_stages(
        self,
        session: AsyncSession,
        call: CallModel,
        state: CallPipelineStateModel,
        outcome: CallOutcome,
        *,
        force: bool,
    ) -> None:
        minimum = await self._min_duration(session)
        if (call.duration_sec or 0) < minimum and not call.transcript:
            raise CallTooShortError(
                f"Qo'ng'iroq juda qisqa ({call.duration_sec or 0} soniya) — "
                f"{minimum} soniyadan qisqa suhbatlar baholanmaydi",
                stage=Stage.TRANSCRIBE.value,
            )

        # ── 1-bosqich: QO'NG'IROQ TURI ────────────────────────
        #
        # ⚠️ ENG BIRINCHI va ENG ARZON. Tur suhbatdoshning RAQAMIDAN
        # aniqlanadi, ya'ni na audio, na transkript kerak va na bir
        # tiyin turadi. Shuning uchun u transkripsiyadan ham oldinda:
        # transkripsiya nosozlik bilan tugasa ham qo'ng'iroqning turi
        # ma'lum bo'lib qoladi va ro'yxatda to'g'ri ko'rinadi.
        route, kind = await self.route_stage.run(session, call)
        outcome.route = route
        outcome.call_type = call.call_type
        await session.flush()

        # ── 2-bosqich: TRANSKRIPT ─────────────────────────────
        #
        # ⚠️ ICHKI SUHBAT HAM TRANSKRIPT OLADI. Ball qo'yilmaydi, lekin
        # matn kerak: menejer ichki suhbatni ham o'qiy olishi, qidiruvda
        # topishi va nizo chiqqanda «kim nima degan edi» degan savolga
        # javob berishi kerak. Bu — hujjat, baho emas.
        state.stage = PipelineStage.TRANSCRIBING.value
        call.status = CallStatus.TRANSCRIBING
        await session.flush()

        transcribe, transcript = await self.transcribe_stage.run(
            session, call, force=force
        )
        outcome.transcribe = transcribe
        state.asr_calls += transcribe.provider_calls
        if transcribe.result is StageResult.DONE:
            state.transcribed_at = datetime.now(UTC)
            state.audio_bytes = transcribe.bytes_streamed
            state.transcript_chars = len(call.transcript or "")
            if transcript is not None:
                state.asr_provider = transcript.provider[:32]
                state.asr_model = transcript.model[:64]

        state.stage = PipelineStage.SCORING.value
        call.status = CallStatus.SCORING
        await session.flush()

        if kind is not CallType.SALES:
            # Ichki suhbat — BAHOLANMAYDI. Qimmat baholash chaqiruvi
            # umuman qilinmaydi. Qo'ng'iroq yo'qolmaydi: transkripti,
            # turi va sababi saqlanadi, hisobotda sanaladi.
            #
            # ⚠️ ESKI BAHO O'CHIRILADI. Qo'ng'iroq ilgari boshqa tur
            # bilan (yoki turlar ajratilishidan oldin) baholangan
            # bo'lishi mumkin. O'sha ballni qoldirish tizimni o'z-o'ziga
            # ZID holatga soladi: bir tomondan «bu ichki suhbat, shuning
            # uchun baholanmaydi», ikkinchi tomondan analitikada 43 ball
            # bo'lib turadi va xodimning o'rtachasini pasaytiraveradi.
            # Baho — hisoblanadigan ma'lumot, uni qayta olish mumkin;
            # yolg'on ko'rsatkichni esa hech kim sezmaydi.
            removed = await delete_score(session, call.id)
            if removed:
                log.info(
                    "pipeline.stale_score_removed",
                    call_id=str(call.id),
                    call_type=call.call_type,
                )
            await session.flush()
            state.stage = PipelineStage.COMPLETED.value
            state.error_stage = None
            state.error_code = None
            state.error_message = None
            call.status = CallStatus.COMPLETED
            outcome.stage = PipelineStage.COMPLETED
            log.info(
                "pipeline.not_scored",
                call_id=str(call.id),
                call_type=call.call_type,
                reason=call.call_type_reason,
            )
            return

        # ── 3-bosqich: BAHOLASH (faqat savdo) ─────────────────
        score = await self.score_stage.run(session, call, force=force)
        outcome.score = score
        state.llm_calls += score.provider_calls
        if score.result is StageResult.DONE:
            state.scored_at = datetime.now(UTC)

        row = await existing_score(session, call.id)
        if row is not None:
            outcome.overall_score = row.overall_score
            outcome.needs_review = row.needs_review
            state.llm_model = row.model[:64]
            state.rubric_version = row.rubric_version[:16]

        state.stage = PipelineStage.COMPLETED.value
        state.error_stage = None
        state.error_code = None
        state.error_message = None
        call.status = CallStatus.COMPLETED
        outcome.stage = PipelineStage.COMPLETED

    # ── Holat qatori ──────────────────────────────────────────

    @staticmethod
    async def _ensure_state(
        session: AsyncSession, call_id: UUID
    ) -> CallPipelineStateModel:
        """Qator bo'lmasa yaratadi. Poyga bo'lsa ham nusxa chiqmaydi."""
        await session.execute(
            pg_insert(CallPipelineStateModel)
            .values(call_id=call_id, stage=PipelineStage.QUEUED.value)
            .on_conflict_do_nothing(index_elements=[CallPipelineStateModel.call_id])
        )
        row = (
            await session.execute(
                select(CallPipelineStateModel).where(
                    CallPipelineStateModel.call_id == call_id
                )
            )
        ).scalar_one()
        return row

    async def _mark_failed(
        self,
        session: AsyncSession,
        call: CallModel,
        state: CallPipelineStateModel,
        outcome: CallOutcome,
        exc: BaseException,
    ) -> None:
        code = getattr(exc, "code", None) or type(exc).__name__
        message = getattr(exc, "message", None) or str(exc)
        stage = getattr(exc, "stage", None) or (
            Stage.SCORE.value if outcome.transcribe else Stage.TRANSCRIBE.value
        )

        state.stage = PipelineStage.FAILED.value
        state.error_stage = stage[:16]
        state.error_code = str(code)[:64]
        state.error_message = message
        call.status = CallStatus.FAILED

        outcome.stage = PipelineStage.FAILED
        outcome.error_code = str(code)
        outcome.error_message = message

        log.error(
            "pipeline.failed",
            call_id=str(call.id),
            stage=stage,
            code=str(code),
            reason=message,
        )

    async def _mark_skipped(
        self,
        session: AsyncSession,
        call: CallModel,
        state: CallPipelineStateModel,
        outcome: CallOutcome,
        exc: AppError,
    ) -> None:
        state.stage = PipelineStage.SKIPPED.value
        state.error_stage = (getattr(exc, "stage", None) or Stage.TRANSCRIBE.value)[:16]
        state.error_code = str(exc.code)[:64]
        state.error_message = exc.message
        call.status = CallStatus.SKIPPED

        outcome.stage = PipelineStage.SKIPPED
        outcome.error_code = exc.code
        outcome.error_message = exc.message

        log.info(
            "pipeline.skipped",
            call_id=str(call.id),
            code=exc.code,
            reason=exc.message,
        )

    # ── Guruh ─────────────────────────────────────────────────

    async def run_batch(
        self, call_ids: Sequence[UUID], *, force: bool = False
    ) -> BatchReport:
        """Ro'yxatni cheklangan parallellik bilan yuritadi.

        Loglar har `progress_every` qo'ng'iroqda tezlik bilan chiqadi —
        navbat qotib qolganini odam DARHOL ko'radi.
        """
        report = BatchReport(started_at=datetime.now(UTC))
        semaphore = asyncio.Semaphore(self.config.concurrency)
        started = perf_counter()
        done = 0
        lock = asyncio.Lock()

        log.info(
            "pipeline.batch_start",
            calls=len(call_ids),
            concurrency=self.config.concurrency,
            asr_rpm=self.config.asr_rpm,
            llm_rpm=self.config.llm_rpm,
            force=force,
        )

        async def worker(call_id: UUID) -> None:
            nonlocal done
            async with semaphore:
                try:
                    outcome = await asyncio.wait_for(
                        self.process_call(call_id, force=force),
                        timeout=self.config.call_timeout_sec,
                    )
                except TimeoutError:
                    outcome = CallOutcome(
                        call_id=call_id,
                        stage=PipelineStage.FAILED,
                        error_code="timeout",
                        error_message=(
                            f"Qo'ng'iroq {self.config.call_timeout_sec:.0f} soniyada "
                            "qayta ishlanmadi"
                        ),
                    )
                    log.error("pipeline.timeout", call_id=str(call_id))
                except Exception as exc:  # noqa: BLE001
                    outcome = CallOutcome(
                        call_id=call_id,
                        stage=PipelineStage.FAILED,
                        error_code=getattr(exc, "code", type(exc).__name__),
                        error_message=getattr(exc, "message", str(exc)),
                    )
                    log.error(
                        "pipeline.crashed", call_id=str(call_id), error=str(exc)
                    )

            async with lock:
                report.add(outcome)
                done += 1
                if done % self.config.progress_every == 0 or done == len(call_ids):
                    elapsed = perf_counter() - started
                    log.info(
                        "pipeline.progress",
                        done=done,
                        total=len(call_ids),
                        completed=report.completed,
                        failed=report.failed,
                        skipped=report.skipped,
                        needs_review=report.needs_review,
                        elapsed_sec=round(elapsed, 1),
                        calls_per_min=round(done / elapsed * 60, 1) if elapsed else 0,
                    )

        await asyncio.gather(*(worker(cid) for cid in call_ids))

        report.elapsed_sec = perf_counter() - started
        log.info("pipeline.batch_done", **report.as_dict())
        return report


# ── Baholanmaydigan eng qisqa suhbat ──────────────────────────


async def resolve_min_duration(
    session: AsyncSession, config: PipelineConfig | None = None
) -> int:
    """Minimal davomiylik (soniya) — SOZLAMA USTUN TURADI.

    ⚠️ YAGONA JOY. Bu qiymat ikki joyda kerak: qaysi qo'ng'iroqlar
    NAVBATGA olinishida (`select_calls`) va har bir qo'ng'iroq
    ishlanishidan oldin (`_run_stages`). Ilgari ular boshqa-boshqa
    manbadan o'qirdi — biri muhit o'zgaruvchisidan (30), ikkinchisi
    sozlamadan (10). Natijada admin sozlamada 10 qo'ysa ham «Baholash»
    tugmasi «0 ta qo'ng'iroq» der edi, chunki tanlash hamon 30 dan
    qisqalarini chiqarib tashlardi. Sozlama ishlagandek ko'rinar,
    amalda esa yarmi ishlardi.

    Sozlama bo'sh yoki buzuq bo'lsa — muhit qiymatiga qaytamiz.
    """
    config = config or load_config()
    try:
        raw = await SettingsService(session).get_value("ai.min_duration_sec")
    except Exception:  # noqa: BLE001 — sozlama o'qilmasa quvur to'xtamasin
        return config.min_duration_sec
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return config.min_duration_sec
    return max(0, value)


# ── Qo'ng'iroq tanlash ────────────────────────────────────────


async def select_calls(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    only_unscored: bool = True,
    min_duration_sec: int | None = None,
    limit: int = 5000,
    agent_ids: Iterable[UUID] | None = None,
) -> list[UUID]:
    """Sana oralig'idagi baholanadigan qo'ng'iroqlar.

    `only_unscored` — natijasi ALLAQACHON MA'LUM bo'lganlarini olmaydi.
    Shu tufayli bir xil oraliqni ikki marta yuborish bejiz xarajat
    qilmaydi.

    ⚠️ «Natijasi ma'lum» ikki xil bo'ladi va faqat birinchisiga qarash
    XATO edi:

      1. bahosi bor — savdo suhbati baholangan;
      2. savdo EMASligi aniqlangan — bunday qo'ng'iroqda baho qatori
         hech qachon paydo bo'lmaydi, chunki u ataylab yozilmaydi.

    Faqat birinchi shart qo'yilganda ikkinchi guruh HAR SAFAR qaytadan
    tanlanardi. O'lchandi: 114 ta tanlanganning 63 tasi shunday edi.
    Zarari — pul emas (tur idempotent, LLM qayta chaqirilmaydi), balki
    ishonch: «Baholanmaganlarni baholash» tugmasi bosilgani bilan son
    kamaymaydi, progress esa 63 ta ortiqcha qo'ng'iroqni sanaydi.
    Admin buni nosozlik deb o'qiydi va u haq bo'lardi.

    ⚠️ «Aniqlangan» — bu FAQAT `internal`. Boshqa qiymatlar (eski
    tasnifdan qolgan `service`, `personal`, `unclear`) tanish tur emas
    va qaytadan aniqlanadi: ular hozir savdo bo'lib chiqishi mumkin.
    """
    threshold = (
        await resolve_min_duration(session)
        if min_duration_sec is None
        else min_duration_sec
    )

    query = (
        select(CallModel.id)
        .where(
            CallModel.started_at >= date_from,
            CallModel.started_at <= date_to,
            CallModel.audio_key.is_not(None),
            CallModel.audio_key != "",
            CallModel.duration_sec >= threshold,
        )
        .order_by(CallModel.started_at)
        .limit(limit)
    )

    if agent_ids:
        query = query.where(CallModel.agent_id.in_(list(agent_ids)))

    if only_unscored:
        from src.modules.scoring.infrastructure.models import CallScoreModel

        scored = select(CallScoreModel.call_id)
        query = query.where(
            CallModel.id.not_in(scored),
            # ⚠️ Shart «savdo YOKI bo'sh» deb yozilmaydi, balki
            # «baholanmaydigan TANISH turlardan biri EMAS» deb yoziladi.
            #
            # Farqi buzuq va ESKI qiymatlarda ko'rinadi. Ustun —
            # `varchar(16)`, baza darajasida cheklanmagan; u yerda hali
            # eski tasnifdan qolgan `service`/`personal`/`unclear` bor.
            # Bunday qiymat `= 'sales'` ga ham, `IS NULL` ga ham
            # tushmaydi — ya'ni birinchi variantda qo'ng'iroq navbatga
            # ABADIY tushmay qolardi va buni hech kim sezmasdi. Bu
            # ko'rinishda esa u tanlanadi, `RouteStage` turni raqam
            # bo'yicha qaytadan aniqlaydi — tizim o'zini tuzatadi.
            or_(
                CallModel.call_type.is_(None),
                CallModel.call_type.not_in(NOT_SCORABLE_TYPES),
            ),
        )

    return list((await session.execute(query)).scalars().all())
