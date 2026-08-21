"""2-bosqich: transkript + FAOL rubrika → tekshirilgan baho.

Muhim: rubrika versiyasi baho bilan birga yoziladi. Rubrika ertaga
o'zgarsa, kechagi ball qaysi mezon bo'yicha qo'yilgani ma'lum qoladi —
aks holda taqqoslash ma'nosini yo'qotadi.

Idempotentlik: `call_scores.call_id` UNIQUE va bosqich boshida
tekshiriladi — takroriy yurishda LLM umuman chaqirilmaydi.
"""

from time import perf_counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.deps import PipelineDeps
from src.modules.pipeline.domain.config import PipelineConfig
from src.modules.pipeline.domain.entities import Stage, StageOutcome, StageResult
from src.modules.pipeline.infrastructure.limits import RateLimiter, with_backoff
from src.modules.scoring.application.review_rules import decide
from src.modules.scoring.application.rubric_service import RubricService
from src.modules.scoring.application.score_writer import (
    agent_client_rating,
    existing_score,
    save_score,
)
from src.modules.scoring.application.scorer import CallContext, CallScorer

log = structlog.get_logger(__name__)


class ScoreStage:
    def __init__(self, deps: PipelineDeps, config: PipelineConfig) -> None:
        self._deps = deps
        self._config = config
        self._limiter = RateLimiter("llm", config.llm_rpm)

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    async def run(
        self, session: AsyncSession, call: CallModel, *, force: bool = False
    ) -> StageOutcome:
        started = perf_counter()

        if not force:
            already = await existing_score(session, call.id)
            if already is not None:
                return StageOutcome(
                    stage=Stage.SCORE,
                    result=StageResult.SKIPPED,
                    detail=(
                        f"Baho allaqachon bor: {already.overall_score} ball "
                        f"({already.model}, rubrika {already.rubric_version})"
                    ),
                )

        rubric = await RubricService(session).get_active()
        llm = await self._deps.llm_factory(session)

        async def invoke(*, system: str, user: str, schema: dict) -> str:
            async def attempt() -> str:
                await self._limiter.acquire()
                return await llm.complete(
                    system=system, user=user, schema=schema, max_tokens=4096
                )

            return await with_backoff(
                attempt,
                max_retries=self._config.max_retries,
                base_sec=self._config.backoff_base_sec,
                max_sec=self._config.backoff_max_sec,
                label=Stage.SCORE.value,
                call_id=call.id,
            )

        scorer = CallScorer(
            llm,
            rubric_blocks=rubric.blocks,
            rubric_red_flags=rubric.red_flags,
            # Admin yozgan qo'shimcha qoidalar — rubrikaning bir qismi,
            # ya'ni versiyalanadi va `rubric_version` bilan bog'lanadi
            extra_rules=rubric.extra_rules,
            invalid_retries=self._config.invalid_retries,
            invoke=invoke,
        )

        transcript = call.transcript or ""
        outcome = await scorer.score(
            CallContext(
                transcript=transcript,
                duration_sec=call.duration_sec or 0,
                direction=str(call.direction),
                started_at=call.started_at.strftime("%d/%m/%Y %H:%M"),
                # Nom bor = raqam kontaktlar kitobida saqlangan, ya'ni
                # TANISH mijoz. Bu baholashda muhim signal: tanish
                # mijozdan to'liq tanishtirish talab qilinmaydi.
                client_label=call.client_name,
            )
        )
        draft = outcome.draft

        if draft.warnings:
            # ⚠️ Ballga ta'sir qilmagan nomuvofiqliklar JIMGINA
            # yo'qolmasligi kerak: ular modelning qayerda adashayotganini
            # ko'rsatadi va promptni sozlashda yagona manba shu.
            log.warning(
                "score.warnings",
                call_id=str(call.id),
                warnings=draft.warnings,
            )

        rating, rating_count = await agent_client_rating(session, call.agent_id)
        review = decide(
            confidence=draft.confidence,
            transcript_quality=draft.transcript_quality,
            transcript_text=transcript,
            duration_sec=call.duration_sec or 0,
            red_flag_types=[f["type"] for f in draft.red_flags],
            ai_score=draft.overall,
            client_rating=rating,
            client_rating_count=rating_count,
            na_over_budget=draft.na_over_budget,
        )

        await save_score(
            session,
            call_id=call.id,
            draft=draft,
            review=review,
            model=getattr(llm, "model", "unknown"),
            rubric_version=f"v{rubric.version}",
        )

        elapsed_ms = int((perf_counter() - started) * 1000)
        log.info(
            "pipeline.scored",
            call_id=str(call.id),
            model=getattr(llm, "model", "?"),
            rubric=f"v{rubric.version}",
            score=draft.overall,
            confidence=draft.confidence,
            red_flags=len(draft.red_flags),
            needs_review=review.needs_review,
            review_reasons=review.codes or None,
            llm_calls=outcome.llm_calls,
            elapsed_ms=elapsed_ms,
        )

        return StageOutcome(
            stage=Stage.SCORE,
            result=StageResult.DONE,
            detail=f"{draft.overall} ball, rubrika v{rubric.version}",
            provider_calls=outcome.llm_calls,
            elapsed_ms=elapsed_ms,
        )
