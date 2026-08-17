"""Provayder klientlari uchun umumiy asos.

Bu yerda vendor'ga bog'liq bo'lmagan narsalar:
  • `ClientConfig` — fabrikadan klientga uzatiladigan hamma narsa
  • audio oqimini xotirada yig'ish (DISKKA YOZILMAYDI)
  • tekshirish uchun 1 soniyalik jimlik (WAV) generatori
"""

import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from src.modules.ai.domain.entities import AIProvider
from src.modules.ai.domain.errors import audio_too_large, translate

#: Bir qo'ng'iroq uchun oqilona chegara. Undan kattasi — deyarli har doim xato.
MAX_AUDIO_MB = 200


@dataclass(slots=True)
class ClientConfig:
    """Klient qurish uchun yetarli bo'lgan minimal ma'lumot."""

    provider: AIProvider
    role: str
    model: str
    api_key: str
    #: Test uchun HTTP qatlamini almashtirish (httpx.AsyncClient / MockTransport)
    http_client: Any | None = None
    #: `async_client_args` shaklidagi SDK'lar uchun (google-genai)
    http_args: dict[str, Any] = field(default_factory=dict)
    timeout: float = 120.0

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.api_key,) if self.api_key else ()


class BaseClient:
    """Umumiy xatolik tarjimasi va identifikatsiya."""

    def __init__(self, config: ClientConfig) -> None:
        self._config = config
        self.provider_key = config.provider.key
        self.model = config.model

    @property
    def label(self) -> str:
        return self._config.provider.label

    def _fail(self, exc: BaseException) -> Exception:
        return translate(
            exc,
            provider_label=self.label,
            model=self.model,
            secrets=self._config.secrets,
        )

    async def list_models(self) -> list[str]:
        """Vendorda HOZIR mavjud modellar (shu rol uchun mos kelganlari).

        ⚠️ NEGA JONLI RO'YXAT KERAK. Ilgari model nomlari kodda qo'lda
        yozilgan ro'yxatdan kelardi. Vendor modelni yopib qo'yganda
        ro'yxat eskirib qolardi va admin ishlamaydigan modelni tanlar,
        xato esa faqat birinchi baholashda — soatlar keyin — chiqardi.
        Aynan shunday bo'ldi: `gemini-2.5-pro` yangi akkauntlarda
        yopilgan edi, lekin standart qiymat sifatida turgan edi.

        Bo'sh ro'yxat = «vendor aytmadi». Chaqiruvchi bunda reyestrdagi
        zaxira ro'yxatga qaytadi, xato ko'tarmaydi.
        """
        return []


async def collect_audio(
    audio: AsyncIterator[bytes], *, limit_mb: int = MAX_AUDIO_MB
) -> bytes:
    """Oqimni XOTIRADA yig'adi.

    ⚠️ Ataylab diskka yozilmaydi: shartnomaning 1-qoidasi —
    audio na faylda, na bazada saqlanadi.
    """
    limit = limit_mb * 1024 * 1024
    buffer = bytearray()
    async for chunk in audio:
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise audio_too_large(limit_mb)
    return bytes(buffer)


def silence_wav(seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Tekshirish uchun eng arzon audio — bir soniyalik jimlik (WAV, 16 kB).

    Haqiqiy fayl kerak emas, provayder faqat «kalit ishlayaptimi» ni
    tasdiqlashi kerak.
    """
    frames = int(seconds * sample_rate)
    data = b"\x00\x00" * frames
    header = b"RIFF"
    header += struct.pack("<I", 36 + len(data))
    header += b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


def guess_mime(filename: str) -> str:
    lowered = (filename or "").lower()
    for suffix, mime in (
        (".mp3", "audio/mpeg"),
        (".m4a", "audio/mp4"),
        (".mp4", "audio/mp4"),
        (".wav", "audio/wav"),
        (".ogg", "audio/ogg"),
        (".opus", "audio/ogg"),
        (".flac", "audio/flac"),
        (".webm", "audio/webm"),
    ):
        if lowered.endswith(suffix):
            return mime
    return "audio/mpeg"
