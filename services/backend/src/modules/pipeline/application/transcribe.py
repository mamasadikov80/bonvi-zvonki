"""1-bosqich: yozuv oqimi → transkript.

Zanjir: MoyZvonki `open_recording` → `AsyncIterator[bytes]` → ASR klienti.

⚠️ **Audio hech qayerda MODDIYLASHMAYDI.** Bu faylda `open()`, `write()`,
`tempfile`, `BytesIO` yo'q va bo'lmaydi. Yagona qo'shimchamiz —
baytlarni SANAYDIGAN generator (o'lchov uchun), u baytlarni ushlab
qolmaydi. Shartnomaning 1-qoidasi shu joyda hal bo'ladi.

Idempotentlik: `calls.transcript` to'la bo'lsa ASR umuman chaqirilmaydi
— demak takroriy yurish PUL SARFLAMAYDI.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ai.domain.entities import Transcript
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.deps import PipelineDeps
from src.modules.pipeline.domain.config import PipelineConfig
from src.modules.pipeline.domain.entities import (
    NoRecordingError,
    Stage,
    StageOutcome,
    StageResult,
    TranscriptEmptyError,
)
from src.modules.pipeline.infrastructure.limits import RateLimiter, with_backoff
from src.modules.settings.application.services import SettingsService

log = structlog.get_logger(__name__)

#: `Content-Type` → fayl nomi kengaytmasi. ASR provayderlari fayl
#: nomidan MIME turini taxmin qiladi, shuning uchun to'g'ri bo'lsin.
_EXTENSION = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
}


@dataclass(slots=True)
class _Counter:
    total: int = 0


async def _counted(
    chunks: AsyncIterator[bytes], counter: _Counter
) -> AsyncIterator[bytes]:
    """Baytlarni sanaydi va DARHOL uzatadi — hech narsa yig'ilmaydi."""
    async for chunk in chunks:
        counter.total += len(chunk)
        yield chunk


class TranscribeStage:
    def __init__(self, deps: PipelineDeps, config: PipelineConfig) -> None:
        self._deps = deps
        self._config = config
        self._limiter = RateLimiter("asr", config.asr_rpm)

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    async def _language(self, session: AsyncSession) -> str | None:
        """Audio tili (`ai.asr_language`). Bo'sh bo'lsa — `None`.

        ⚠️ Bu ko'rsatma Whisper oilasi uchun HAL QILUVCHI. Usiz Groq
        Whisper o'zbek nutqini turkcha yoki inglizcha deb o'qidi va
        transkript o'rniga bema'ni tarjima qaytardi — beshta sinov
        qo'ng'irog'ining beshtasi ham shu sababdan 0 ball oldi.

        `None` qaytishi ATAYLAB ruxsat etilgan: admin maydonni ataylab
        bo'shatib, provayderga tilni o'zi aniqlashni topshirishi mumkin
        (masalan qo'ng'iroqlar haqiqatan ko'p tilli bo'lsa).
        """
        try:
            raw = await SettingsService(session).get_value("ai.asr_language")
        except Exception:  # noqa: BLE001 — sozlama o'qilmasa quvur to'xtamasin
            return None
        return (str(raw).strip() or None) if raw is not None else None

    async def run(
        self, session: AsyncSession, call: CallModel, *, force: bool = False
    ) -> tuple[StageOutcome, Transcript | None]:
        started = perf_counter()

        # ── Idempotentlik: bor narsa uchun ikkinchi marta to'lanmaydi ──
        if not force and (call.transcript or "").strip():
            return (
                StageOutcome(
                    stage=Stage.TRANSCRIBE,
                    result=StageResult.SKIPPED,
                    detail=f"Transkript allaqachon bor ({len(call.transcript)} belgi)",
                ),
                None,
            )

        if not (call.audio_key or "").strip():
            raise NoRecordingError(
                "Qo'ng'iroqda MoyZvonki yozuvi yo'q — javobsiz bo'lgan yoki "
                "saqlash muddati o'tgan, shuning uchun baholanmaydi",
                stage=Stage.TRANSCRIBE.value,
            )

        asr = await self._deps.asr_factory(session)
        language = await self._language(session)
        counter = _Counter()
        calls_made = 0

        async def attempt() -> Transcript:
            nonlocal calls_made
            counter.total = 0
            await self._limiter.acquire()
            async with self._deps.open_recording(session, call.audio_key) as stream:
                content_type = (getattr(stream, "content_type", "") or "").lower()
                filename = f"call-{call.id}{_EXTENSION.get(content_type, '.mp3')}"
                # Oqim to'g'ridan-to'g'ri provayderga: oraliq bufer yo'q
                result = await asr.transcribe(
                    _counted(stream.chunks, counter),
                    filename=filename,
                    language=language,
                )
                # Hisoblagich JAVOB KELGANDAN keyin o'sadi: 429 uchun
                # pul olinmaydi, demak uni «chaqiruv» deb yozish xato
                calls_made += 1
                return result

        transcript = await with_backoff(
            attempt,
            max_retries=self._config.max_retries,
            base_sec=self._config.backoff_base_sec,
            max_sec=self._config.backoff_max_sec,
            label=Stage.TRANSCRIBE.value,
            call_id=call.id,
        )

        text = (transcript.text or "").strip()
        if not text:
            raise TranscriptEmptyError(
                "ASR bo'sh transkript qaytardi — yozuvda nutq topilmadi "
                "yoki fayl buzilgan",
                stage=Stage.TRANSCRIBE.value,
            )

        call.transcript = text

        elapsed_ms = int((perf_counter() - started) * 1000)
        log.info(
            "pipeline.transcribed",
            call_id=str(call.id),
            provider=getattr(asr, "provider_key", "?"),
            model=getattr(asr, "model", "?"),
            chars=len(text),
            audio_kb=round(counter.total / 1024, 1),
            elapsed_ms=elapsed_ms,
        )

        return (
            StageOutcome(
                stage=Stage.TRANSCRIBE,
                result=StageResult.DONE,
                detail=f"{len(text)} belgi",
                provider_calls=calls_made,
                elapsed_ms=elapsed_ms,
                bytes_streamed=counter.total,
            ),
            transcript,
        )
