"""Quvur domeni — bosqichlar, natijalar, xatolar.

Ikki bosqich bor va ikkalasi ham IDEMPOTENT:

    1. `transcribe` — MoyZvonki oqimi → ASR → `calls.transcript`
    2. `score`      — transkript + faol rubrika → LLM → `call_scores`

Har bosqich uchta natijadan biri bilan tugaydi: `done` (bajarildi),
`skipped` (allaqachon bor — pul sarflanmadi), `failed` (sabab yozildi).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.core.exceptions import AppError


class Stage(StrEnum):
    #: Tur aniqlash — raqam bo'yicha, provayderga chiqmaydi
    ROUTE = "route"
    TRANSCRIBE = "transcribe"
    SCORE = "score"


class StageResult(StrEnum):
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class PipelineStage(StrEnum):
    """`call_pipeline_state.stage` — qo'ng'iroq quvurning qayerida."""

    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    #: Baholanmaydi (yozuvi yo'q yoki juda qisqa) — xato EMAS
    SKIPPED = "skipped"
    LOCKED = "locked"  # boshqa worker ishlayapti


# ── Xatolar ───────────────────────────────────────────────────


class PipelineError(AppError):
    """Quvurdagi nosozlik. Xabar HAR DOIM o'zbekcha va aniq."""

    status_code = 502
    code = "pipeline_error"

    def __init__(
        self, message: str, *, code: str | None = None, stage: str | None = None
    ) -> None:
        super().__init__(message, code=code)
        self.stage = stage


class NoRecordingError(PipelineError):
    status_code = 404
    code = "no_recording"


class TranscriptEmptyError(PipelineError):
    status_code = 422
    code = "transcript_empty"


class CallTooShortError(PipelineError):
    status_code = 422
    code = "call_too_short"


class DirectoryEmptyError(PipelineError):
    """Kompaniya liniyalari ro'yxati bo'sh — tur aniqlab bo'lmaydi.

    ⚠️ NEGA QO'NG'IROQ SHUNDA ISHLANMAYDI. Ro'yxat bo'sh bo'lsa har
    qanday suhbat «tashqi» bo'lib chiqadi, ya'ni hamkasblar orasidagi
    gaplashuv ham savdo rubrikasi bilan baholanadi va past ball oladi.
    Bu ikki tomonlama zarar: pul sarflanadi va xodimning o'rtachasi
    asossiz tushadi — buni keyin tuzatib ham bo'lmaydi, chunki
    baholangan qo'ng'iroq navbatga qayta tushmaydi.

    Shuning uchun bunday holatda qo'ng'iroq TEGILMAY qoladi va sabab
    yozib qo'yiladi. Ro'yxat birinchi sinxronizatsiyadan keyin to'ladi
    (`calls.agent_number`), keyingi yurishda esa hammasi normal ishlaydi.
    """

    status_code = 503
    code = "internal_directory_empty"


# ── Natijalar ─────────────────────────────────────────────────


@dataclass(slots=True)
class StageOutcome:
    """Bitta bosqich natijasi."""

    stage: Stage
    result: StageResult
    detail: str = ""
    error_code: str | None = None
    #: Haqiqatan provayderga borgan (ya'ni PUL turgan) chaqiruvlar soni
    provider_calls: int = 0
    elapsed_ms: int = 0
    bytes_streamed: int = 0

    @property
    def ok(self) -> bool:
        return self.result is not StageResult.FAILED


@dataclass(slots=True)
class CallOutcome:
    """Bitta qo'ng'iroqning to'liq quvur natijasi."""

    call_id: UUID
    stage: PipelineStage
    transcribe: StageOutcome | None = None
    route: StageOutcome | None = None
    """Tur aniqlash bosqichi — RAQAM bo'yicha, provayderga chiqmaydi.

    Ilgari bu yerda LLM chaqiruvi turardi va `llm_calls` ga kirardi.
    Endi bosqich bepul: `provider_calls` doim 0."""
    score: StageOutcome | None = None
    error_code: str | None = None
    error_message: str | None = None
    needs_review: bool = False
    overall_score: int | None = None
    elapsed_ms: int = 0

    call_type: str | None = None
    """Aniqlangan tur. `sales` dan boshqasi BAHOLANMAYDI.

    `overall_score` bunda `None` bo'ladi va bu XATO emas: savdo
    bo'lmagan suhbatni savdo rubrikasi bilan baholash xodimning
    o'rtachasini asossiz pasaytirardi."""

    @property
    def failed(self) -> bool:
        return self.stage is PipelineStage.FAILED

    @property
    def scored(self) -> bool:
        return self.overall_score is not None

    @property
    def asr_calls(self) -> int:
        return self.transcribe.provider_calls if self.transcribe else 0

    @property
    def llm_calls(self) -> int:
        """LLM ga ketgan chaqiruvlar — faqat BAHOLASH.

        ⚠️ Tur aniqlash bosqichi bu songa KIRMAYDI, chunki u endi
        provayderga umuman chiqmaydi (raqam bo'yicha hal bo'ladi).
        Ilgari kirardi: o'shanda tasnif ham LLM chaqiruvi edi.

        Aynan shu son bilan «bitta audio uchun nechta so'rov ketdi» va
        «vendor chegarasi nega to'ldi» degan savollarga javob beriladi.
        """
        return self.score.provider_calls if self.score else 0


@dataclass(slots=True)
class BatchReport:
    """Guruh yurishining yakuni — loglarda va API javobida bir xil."""

    total: int = 0
    completed: int = 0
    """Xatosiz tugagan — BAHOLANGANI shart emas."""
    scored: int = 0
    """Baho yozilgani. ⚠️ `completed` dan KAM bo'lishi normal: savdo
    bo'lmagan suhbat muvaffaqiyatli tugaydi, lekin baholanmaydi."""
    not_sales: int = 0
    """Tugadi, lekin savdo suhbati bo'lmagani uchun baholanmadi.

    Bu son bo'lmasa hisobot yolg'on gapiradi: «completed: 63» degan
    qator 63 ta qo'ng'iroq baholanganini bildirardi, aslida 96% i
    baholanmagan. Ma'lumotda o'lchandi — 69 tadan 63 tasi savdo emas."""
    failed: int = 0
    skipped: int = 0
    """Takroriy yurish: hamma bosqich allaqachon bajarilgan edi."""
    not_scorable: int = 0
    """TEXNIK sabab bilan chetlab o'tilgan: audio yo'q yoki juda qisqa.
    Bu — `SKIPPED` bosqichi, savdo emasligi bilan aloqasi YO'Q."""
    locked: int = 0
    asr_calls: int = 0
    llm_calls: int = 0
    needs_review: int = 0
    bytes_streamed: int = 0
    started_at: datetime | None = None
    elapsed_sec: float = 0.0
    errors: dict[str, int] = field(default_factory=dict)

    def add(self, outcome: CallOutcome) -> None:
        self.total += 1
        self.asr_calls += outcome.asr_calls
        self.llm_calls += outcome.llm_calls
        if outcome.transcribe:
            self.bytes_streamed += outcome.transcribe.bytes_streamed

        if outcome.stage is PipelineStage.FAILED:
            self.failed += 1
            key = outcome.error_code or "pipeline_error"
            self.errors[key] = self.errors.get(key, 0) + 1
        elif outcome.stage is PipelineStage.LOCKED:
            self.locked += 1
        elif outcome.stage is PipelineStage.SKIPPED:
            self.not_scorable += 1
        else:
            self.completed += 1
            if outcome.scored:
                self.scored += 1
                if outcome.needs_review:
                    self.needs_review += 1
            elif outcome.call_type is not None:
                # Tugadi, bahosi yo'q, turi ma'lum → savdo emas
                self.not_sales += 1

            # Takroriy yurish: BIR ham provayder chaqiruvi bo'lmagan.
            # Ilgari bu `score is not None` shartiga tayanardi — savdo
            # bo'lmagan qo'ng'iroqda baho bosqichi umuman ishlamaydi
            # (`score is None`), ya'ni takroriy yurish ham «yangi ish»
            # deb sanalardi va bu son doim kam ko'rsatardi.
            if outcome.asr_calls == 0 and outcome.llm_calls == 0:
                self.skipped += 1

    @property
    def per_minute(self) -> float:
        if self.elapsed_sec <= 0:
            return 0.0
        return round(self.total / self.elapsed_sec * 60.0, 1)

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "completed": self.completed,
            "scored": self.scored,
            "not_sales": self.not_sales,
            "failed": self.failed,
            "skipped_idempotent": self.skipped,
            "not_scorable": self.not_scorable,
            "locked": self.locked,
            "asr_calls": self.asr_calls,
            "llm_calls": self.llm_calls,
            "needs_review": self.needs_review,
            "bytes_streamed": self.bytes_streamed,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "calls_per_minute": self.per_minute,
            "errors": dict(self.errors),
        }
