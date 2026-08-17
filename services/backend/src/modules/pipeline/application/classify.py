"""Oraliq bosqich: transkript → QO'NG'IROQ TURI.

Transkript va baholash orasida turadi va bitta savolga javob beradi:
«bu savdo qo'ng'irog'imi?». Javob «yo'q» bo'lsa baholash bosqichi
UMUMAN ishga tushmaydi.

NEGA SHUNDAY. Ish telefonlari orqali xodimlar viloyat skladlari,
buxgalteriya va hamkasblar bilan ham gaplashadi. Savdo rubrikasi
bunday suhbatga «ehtiyojni aniqladimi» degan savolni beradi va
tabiiy ravishda nol qo'yadi. Haqiqiy ma'lumotda o'lchandi: baholangan
69 qo'ng'iroqdan 14 tasi (20%) ichki suhbat bo'lib chiqdi — muloqot
bali 17/25, savdo bali 6/25, umumiy ball 43. Ya'ni yaxshi o'tgan
ish suhbati xodimning o'rtachasini pasaytirgan.

NARXI KAMAYADI. Bu chaqiruv arzon: chiqishi bir necha o'nlab token
(baholash 1500+ qaytaradi). Savdo bo'lmagan qo'ng'iroq shu bilan
tugaydi — qimmat baholash chaqiruvi qilinmaydi.

Idempotentlik: `calls.call_type` to'la bo'lsa LLM chaqirilmaydi.
"""

from time import perf_counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.calls.domain.entities import CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.deps import PipelineDeps
from src.modules.pipeline.domain.config import PipelineConfig
from src.modules.pipeline.domain.entities import Stage, StageOutcome, StageResult
from src.modules.pipeline.infrastructure.limits import RateLimiter, with_backoff
from src.modules.scoring.application import classifier

log = structlog.get_logger(__name__)


def _tur(raw: str | None) -> CallType | None:
    """Bazadagi matnni `CallType` ga aylantiradi. Notanish bo'lsa `None`.

    `None` — «aniqlanmagan» degani, ya'ni bosqich qaytadan ishlaydi.
    Bu notanish qiymatni `UNCLEAR` deb qabul qilishdan yaxshiroq:
    `UNCLEAR` «AI ko'rdi va aniqlay olmadi» degan MA'NOGA ega va
    baholanmaydigan turlar qatoriga kiradi — buzuq qiymatni shunday
    o'qish qo'ng'iroqni jimgina baholashdan chiqarib tashlardi.
    """
    if not raw:
        return None
    try:
        return CallType(raw)
    except ValueError:
        log.warning("pipeline.unknown_call_type", value=raw[:32])
        return None


class ClassifyStage:
    def __init__(self, deps: PipelineDeps, config: PipelineConfig) -> None:
        self._deps = deps
        self._config = config
        # Baholash bilan BIR XIL cheklovchi: ikkalasi ham LLM ga boradi
        # va vendor chegarasi umumiy
        self._limiter = RateLimiter("llm", config.llm_rpm)

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    async def run(
        self, session: AsyncSession, call: CallModel, *, force: bool = False
    ) -> tuple[StageOutcome, classifier.Classification | None]:
        started = perf_counter()

        # ── Idempotentlik ─────────────────────────────────────
        #
        # ⚠️ `CallType(call.call_type)` deb TO'G'RIDAN-TO'G'RI yozib
        # bo'lmaydi. Ustun — `varchar(16)`, ya'ni baza darajasida hech
        # narsa cheklanmagan: enum kelajakda o'zgarsa, qo'lda SQL
        # yozilsa yoki ma'lumot ko'chirilsa notanish qiymat paydo
        # bo'ladi va `ValueError` butun quvurni yiqitadi — o'sha
        # qo'ng'iroq FAILED bo'lib, sababi «ValueError» deb turadi.
        # Notanish qiymat hech qanday ma'lumot bermaydi, shuning uchun
        # «hali aniqlanmagan» deb qarab, qaytadan aniqlanadi.
        known = _tur(call.call_type)
        if not force and known is not None:
            return (
                StageOutcome(
                    stage=Stage.SCORE,
                    result=StageResult.SKIPPED,
                    detail=f"Turi allaqachon aniqlangan: {known.value}",
                ),
                classifier.Classification(
                    call_type=known,
                    confidence=float(call.call_type_confidence or 0),
                    reason=call.call_type_reason or "",
                    misconduct=False,
                    misconduct_note=None,
                ),
            )

        transcript = (call.transcript or "").strip()
        if not transcript:
            # Transkript yo'q — tur ham aniqlanmaydi. Bu holat
            # `TranscribeStage` da allaqachon xato bilan tugagan bo'lardi,
            # lekin bosqich mustaqil ishlashi kerak.
            return (
                StageOutcome(
                    stage=Stage.SCORE,
                    result=StageResult.SKIPPED,
                    detail="Transkript yo'q — tur aniqlanmadi",
                ),
                None,
            )

        llm = await self._deps.llm_factory(session)
        calls_made = 0

        async def attempt() -> classifier.Classification:
            nonlocal calls_made
            await self._limiter.acquire()
            raw = await llm.complete(
                system=classifier.SYSTEM_PROMPT,
                user=classifier.build_user_prompt(
                    transcript=transcript,
                    duration_sec=call.duration_sec or 0,
                    direction=str(call.direction),
                ),
                schema=classifier.SCHEMA,
                max_tokens=classifier.MAX_TOKENS,
            )
            calls_made += 1
            return classifier.parse(raw)

        result = await with_backoff(
            attempt,
            max_retries=self._config.max_retries,
            base_sec=self._config.backoff_base_sec,
            max_sec=self._config.backoff_max_sec,
            label="classify",
            call_id=call.id,
        )

        call.call_type = result.call_type.value
        call.call_type_reason = result.reason or None
        call.call_type_confidence = round(result.confidence, 2)

        elapsed_ms = int((perf_counter() - started) * 1000)
        log.info(
            "pipeline.classified",
            call_id=str(call.id),
            call_type=result.call_type.value,
            confidence=result.confidence,
            scorable=result.scorable,
            misconduct=result.misconduct,
            elapsed_ms=elapsed_ms,
        )
        if result.misconduct:
            # ⚠️ Baholanmagan qo'ng'iroqda ham qo'pollik ko'rinmay
            # qolmasligi kerak. Bu BAHO emas — xavfsizlik signali.
            log.warning(
                "pipeline.misconduct",
                call_id=str(call.id),
                call_type=result.call_type.value,
                note=result.misconduct_note,
            )

        return (
            StageOutcome(
                stage=Stage.SCORE,
                result=StageResult.DONE,
                detail=f"{result.call_type.value} ({result.reason})"[:200],
                provider_calls=calls_made,
                elapsed_ms=elapsed_ms,
            ),
            result,
        )
