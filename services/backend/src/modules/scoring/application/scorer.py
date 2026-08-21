"""Transkript → tekshirilgan baho.

Bu qatlam bazani ham, navbatni ham bilmaydi: kirish — matn, chiqish —
`ScoreDraft`. Shu tufayli uni testda LLM stubi bilan bemalol chaqirish
mumkin, quvurni (`pipeline`) ko'tarmasdan.

Chegaralanish (rate limit) va qayta urinish quvurda: bu yerga tayyor
`invoke` funksiyasi beriladi.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from src.modules.ai.domain.entities import LLMClient
from src.modules.scoring.application.prompt import (
    build_retry_prompt,
    build_schema,
    build_system_prompt,
    build_user_prompt,
)
from src.modules.scoring.application.validator import (
    ScoreDraft,
    ScoreValidationError,
    na_budget,
    validate,
)

log = structlog.get_logger(__name__)

#: Baho JSON'i uzun emas, lekin har kriteriyaga dalil kerak
MAX_TOKENS = 4096

Invoke = Callable[..., Awaitable[str]]


@dataclass(slots=True)
class CallContext:
    """LLM ga beriladigan qo'ng'iroq konteksti (audio emas, faqat matn)."""

    transcript: str
    duration_sec: int
    direction: str
    started_at: str
    client_label: str | None = None
    """Mijoz nomi — TANISHMI degan signal. `None` bo'lsa raqam
    kontaktlar kitobida yo'q."""


@dataclass(slots=True)
class ScoringOutcome:
    draft: ScoreDraft
    llm_calls: int
    attempts: int


class CallScorer:
    """Faol rubrika bo'yicha bitta qo'ng'iroqni baholaydi."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        rubric_blocks: list[dict[str, Any]],
        rubric_red_flags: list[dict[str, Any]],
        extra_rules: str | None = None,
        invalid_retries: int = 1,
        invoke: Invoke | None = None,
    ) -> None:
        self._llm = llm
        self._blocks = rubric_blocks
        self._red_flags = rubric_red_flags
        self._extra_rules = extra_rules
        self._invalid_retries = max(0, invalid_retries)
        self._invoke = invoke or self._direct_invoke

        # Rubrikaga bog'liq qism bir marta quriladi va O'ZGARMAYDI —
        # prompt caching aynan shuni talab qiladi (PLAN.md 3.4).
        self._system = build_system_prompt(
            rubric_blocks, rubric_red_flags, extra_rules
        )
        self._schema = build_schema(rubric_blocks, rubric_red_flags)

    @property
    def system_prompt(self) -> str:
        return self._system

    @property
    def schema(self) -> dict[str, Any]:
        return self._schema

    async def _direct_invoke(self, *, system: str, user: str, schema: dict) -> str:
        return await self._llm.complete(
            system=system, user=user, schema=schema, max_tokens=MAX_TOKENS
        )

    async def score(self, context: CallContext) -> ScoringOutcome:
        # `na` budjeti suhbat uzunligiga bog'liq va u IKKI JOYDA kerak:
        # promptda (model chegarani oldindan bilsin) va validatorda
        # (chegara haqiqatan qo'llansin). Bitta manbadan olinadi —
        # aks holda model bir chegarani ko'rib, boshqasi bilan
        # tekshirilardi.
        budjet = na_budget(context.duration_sec)
        base_user = build_user_prompt(
            transcript=context.transcript,
            duration_sec=context.duration_sec,
            direction=context.direction,
            started_at=context.started_at,
            client_label=context.client_label,
            na_budget=budjet,
        )

        calls = 0
        last_error: ScoreValidationError | None = None

        for attempt in range(self._invalid_retries + 1):
            user = base_user
            if last_error is not None:
                user = base_user + build_retry_prompt(last_error.message)
            # Oxirgi urinishda `na` budjeti YUMSHOQ: rad etishda ma'no
            # qolmaydi — qo'ng'iroq umuman baholanmagan bo'lib qolardi
            # va to'langan pul behuda ketardi. Baho qabul qilinadi,
            # lekin `na_over_budget` uni tekshiruv navbatiga chiqaradi.
            oxirgi = attempt == self._invalid_retries

            raw = await self._invoke(system=self._system, user=user, schema=self._schema)
            calls += 1

            try:
                draft = validate(
                    raw,
                    rubric_blocks=self._blocks,
                    rubric_red_flags=self._red_flags,
                    duration_sec=context.duration_sec,
                    enforce_na_budget=not oxirgi,
                )
            except ScoreValidationError as exc:
                last_error = exc
                log.warning(
                    "score.invalid",
                    attempt=attempt + 1,
                    model=getattr(self._llm, "model", "?"),
                    reason=exc.message,
                )
                continue

            return ScoringOutcome(draft=draft, llm_calls=calls, attempts=attempt + 1)

        assert last_error is not None
        raise last_error
