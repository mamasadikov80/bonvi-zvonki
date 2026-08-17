"""OpenAI protokoliga mos provayderlar (rasmiy `openai` SDK bilan).

Shu bitta modul OpenAI'ning o'zini ham, protokoliga mos boshqa
vendorlarni ham (DeepSeek, Together, Fireworks, xAI, Cerebras, Mistral…)
xizmat qiladi — ular reyestrga `client_kind="openai_compat"` va
`base_url` bilan yoziladi, kodga tegilmaydi.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from src.modules.ai.domain.entities import Transcript, TranscriptSegment
from src.modules.ai.domain.errors import sdk_missing
from src.modules.ai.infrastructure.providers.base import (
    BaseClient,
    collect_audio,
    guess_mime,
    silence_wav,
)


class _OpenAIStyle(BaseClient):
    """`openai` SDK bilan ishlaydigan umumiy asos."""

    sdk_package = "openai"

    def _build_sdk(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover — konteynerda bor
            raise sdk_missing(self.label, self.sdk_package) from exc

        kwargs: dict[str, Any] = {
            "api_key": self._config.api_key,
            "timeout": self._config.timeout,
            "max_retries": 1,
        }
        if self._config.provider.base_url:
            kwargs["base_url"] = self._config.provider.base_url
        if self._config.http_client is not None:
            kwargs["http_client"] = self._config.http_client
        return AsyncOpenAI(**kwargs)

    #: `GET /v1/models` MODALLIKNI aytmaydi — faqat nomlarni beradi.
    #: Shuning uchun rol bo'yicha nom naqshiga qaraladi. Naqsh keng:
    #: shubhali modelni ro'yxatda qoldirish, kerakligini yashirishdan
    #: yaxshiroq (admin baribir «Tekshirish» tugmasi bilan sinaydi).
    _ASR_HINTS = ("whisper", "transcribe", "audio", "speech-to-text")
    _LLM_SKIP = (
        "whisper", "transcribe", "tts", "embedding", "moderation",
        "dall-e", "image", "sora", "realtime", "audio",
    )

    async def list_models(self) -> list[str]:
        client = self._build_sdk()
        try:
            page = await client.models.list()
            raw = [str(getattr(m, "id", "") or "") for m in page.data]
        except Exception:  # noqa: BLE001 — ro'yxat olinmasa zaxiraga qaytamiz
            return []

        asr = self._config.role == "asr"
        out = []
        for name in raw:
            low = name.lower()
            if not low:
                continue
            if asr:
                if any(h in low for h in self._ASR_HINTS):
                    out.append(name)
            elif not any(h in low for h in self._LLM_SKIP):
                out.append(name)
        return out


class OpenAICompatASRClient(_OpenAIStyle):
    """`POST /v1/audio/transcriptions` (multipart)."""

    async def transcribe(
        self,
        audio: AsyncIterator[bytes],
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript:
        payload = await collect_audio(audio)
        return await self._transcribe_bytes(payload, filename, language)

    async def _transcribe_bytes(
        self, payload: bytes, filename: str, language: str | None
    ) -> Transcript:
        client = self._build_sdk()
        # `verbose_json` faqat whisper oilasida bor — yangi modellar `json`
        verbose = "whisper" in self.model.lower()
        kwargs: dict[str, Any] = {
            "file": (filename, payload, guess_mime(filename)),
            "model": self.model,
            "response_format": "verbose_json" if verbose else "json",
        }
        if language:
            kwargs["language"] = language
        try:
            result = await client.audio.transcriptions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — o'zbekchaga tarjima qilinadi
            raise self._fail(exc) from None

        segments: list[TranscriptSegment] = []
        for raw in getattr(result, "segments", None) or ():
            segments.append(
                TranscriptSegment(
                    text=str(getattr(raw, "text", "") or "").strip(),
                    start_ms=_ms(getattr(raw, "start", None)),
                    end_ms=_ms(getattr(raw, "end", None)),
                )
            )
        return Transcript(
            text=(getattr(result, "text", "") or "").strip(),
            provider=self.provider_key,
            model=self.model,
            language=getattr(result, "language", None) or language,
            duration_ms=_ms(getattr(result, "duration", None)),
            segments=segments,
        )

    async def ping(self) -> str:
        transcript = await self._transcribe_bytes(silence_wav(), "ping.wav", None)
        return transcript.text or "(jimlik)"


class OpenAICompatLLMClient(_OpenAIStyle):
    """`POST /v1/chat/completions`."""

    #: JSON schema'ni to'g'ridan-to'g'ri qo'llaydimi (mos vendorlarda yo'q)
    supports_json_schema = True

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        client = self._build_sdk()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if schema:
            if self.supports_json_schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "schema": schema},
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}
                messages[0]["content"] = (
                    f"{system}\n\nJavobni AYNAN shu JSON sxemasi bo'yicha qaytaring:\n"
                    + json.dumps(schema, ensure_ascii=False, sort_keys=True)
                )
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise self._fail(exc) from None
        return _first_text(response)

    async def ping(self) -> str:
        client = self._build_sdk()
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Javob: OK"}],
                max_tokens=8,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._fail(exc) from None
        return _first_text(response) or "OK"


def _first_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or ()
    for choice in choices:
        content = getattr(getattr(choice, "message", None), "content", None)
        if content:
            return str(content).strip()
    return ""


def _ms(value: Any) -> int | None:
    try:
        return int(float(value) * 1000)
    except (TypeError, ValueError):
        return None
