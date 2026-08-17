"""Quvurning tashqi dunyo bilan uchta aloqasi.

Ular ataylab bitta joyga yig'ilgan va almashtiriladigan qilingan:
testda haqiqiy MoyZvonki, ASR va LLM o'rniga stub qo'yiladi, quvur
kodining o'zi esa o'zgarmaydi. Ish vaqtida standart qiymatlar
ishlatiladi va hech kim vendorni bilmaydi.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ai.application.factory import get_asr_client, get_llm_client
from src.modules.ai.domain.entities import ASRClient, LLMClient
from src.modules.moizvonki.application.factory import moizvonki_client


@asynccontextmanager
async def default_open_recording(
    session: AsyncSession, audio_key: str
) -> AsyncIterator[Any]:
    """Yozuvni MoyZvonki'dan OQIM sifatida ochadi.

    ⚠️ Diskka yozilmaydi, `bytes` ga yig'ilmaydi — ochilgan oqim
    to'g'ridan-to'g'ri ASR klientiga uzatiladi.
    """
    async with moizvonki_client(session) as client:
        async with client.open_recording(audio_key) as stream:
            yield stream


async def _asr(session: AsyncSession) -> ASRClient:
    return await get_asr_client(session)


async def _llm(session: AsyncSession) -> LLMClient:
    return await get_llm_client(session)


@dataclass(slots=True)
class PipelineDeps:
    open_recording: Callable[[AsyncSession, str], Any] = field(
        default=default_open_recording
    )
    asr_factory: Callable[[AsyncSession], Awaitable[ASRClient]] = field(default=_asr)
    llm_factory: Callable[[AsyncSession], Awaitable[LLMClient]] = field(default=_llm)


def default_deps() -> PipelineDeps:
    return PipelineDeps()
