"""Sinov uchun soxta ASR, LLM va yozuv oqimi.

Haqiqiy kalitlarsiz butun quvurni yurgizish uchun. Stublar `PipelineDeps`
orqali ulanadi — ishlab chiqarish kodida «test rejimi» degan shart YO'Q,
shuning uchun tasodifan jonli tizimda yoqilib qolishi ham mumkin emas.

`StubASR.calls` va `StubLLM.calls` — idempotentlikni ISBOTLAYDIGAN
hisoblagichlar: ikkinchi yurishda ular o'smasligi kerak.
"""

import json
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from src.modules.ai.domain.entities import Transcript

# ── Namuna transkript (o'zbek/rus aralash) ────────────────────

SAMPLE_TRANSCRIPT = """[00:02] Sotuvchi: Assalomu alaykum, men Sardor, Bonvi kompaniyasidan qo'ng'iroq qilyapman.
[00:06] Mijoz: Va alaykum assalom, ha eshitaman.
[00:09] Sotuvchi: Ozgina vaqtingizni olsam maylimi? Do'koningizda hozir qaysi mahsulotlarimiz bor edi?
[00:15] Mijoz: X-200 dan bor, lekin tugab qoldi. Y-50 umuman yo'q.
[00:22] Sotuvchi: Tushunarli. Y-50 hozir aksiyada, 50 tadan olsangiz narxi ancha qulay bo'ladi.
[00:31] Mijoz: А сколько будет стоить? Narxi qanday?
[00:35] Sotuvchi: Bir dona 42 ming so'm, 50 tadan olsangiz 39 mingdan.
[00:44] Mijoz: Qimmatroq ekan, o'ylab ko'ray.
[00:47] Sotuvchi: Albatta. Aksiya juma kuni tugaydi, shuning uchun bugun-erta hal qilsangiz yaxshi bo'lardi.
[00:58] Mijoz: Mayli, ertaga aytaman.
[01:02] Sotuvchi: Yaxshi, men payshanba kuni soat 10 da qayta qo'ng'iroq qilaman. Xaridingiz uchun rahmat!
[01:09] Mijoz: Xayr, ko'rishguncha."""

SHORT_TRANSCRIPT = "[00:01] Sotuvchi: Assalomu alaykum. [00:03] Mijoz: Noto'g'ri raqam."


# ── ASR ───────────────────────────────────────────────────────


@dataclass
class StubASR:
    """Oqimni OXIRIGACHA o'qiydi (haqiqiy klient kabi), lekin saqlamaydi."""

    provider_key: str = "stub"
    model: str = "stub-scribe-v1"
    text: str = SAMPLE_TRANSCRIPT
    language: str = "mixed"
    calls: int = 0
    bytes_seen: int = 0
    #: Shuncha marta 429 qaytaradi, keyin muvaffaqiyat
    fail_with_429: int = 0
    error: Exception | None = None

    async def transcribe(
        self,
        audio: AsyncIterator[bytes],
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript:
        self.calls += 1
        seen = 0
        async for chunk in audio:
            seen += len(chunk)
        self.bytes_seen = seen

        if self.fail_with_429 > 0:
            self.fail_with_429 -= 1
            from src.modules.ai.domain.errors import AIRateLimitError

            raise AIRateLimitError(
                "Stub provayder so'rovlar chegarasiga yetdi (429) — "
                "biroz kutib qayta urinib ko'ring"
            )
        if self.error is not None:
            raise self.error

        return Transcript(
            text=self.text,
            provider=self.provider_key,
            model=self.model,
            language=self.language,
            duration_ms=90_000,
        )

    async def ping(self) -> str:
        return "ok"


# ── LLM ───────────────────────────────────────────────────────


@dataclass
class StubLLM:
    """Rubrikadan haqiqiy shaklga mos JSON quradi."""

    model: str = "stub-haiku"
    provider_key: str = "stub"
    calls: int = 0
    #: Tayyor javob(lar) — berilsa, qurilgan javob o'rniga shular qaytadi
    responses: list[str] = field(default_factory=list)
    fail_with_429: int = 0
    ratio: float = 0.8
    red_flags: tuple[str, ...] = ()
    confidence: float = 0.92
    quality: str = "high"
    seed: int = 0
    rubric_blocks: list[dict[str, Any]] = field(default_factory=list)
    rubric_red_flags: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        self.calls += 1
        if self.fail_with_429 > 0:
            self.fail_with_429 -= 1
            from src.modules.ai.domain.errors import AIRateLimitError

            raise AIRateLimitError(
                "Stub provayder so'rovlar chegarasiga yetdi (429) — "
                "biroz kutib qayta urinib ko'ring"
            )
        if self.responses:
            index = min(self.calls - 1, len(self.responses) - 1)
            return self.responses[index]
        return json.dumps(
            build_payload(
                self.rubric_blocks,
                self.rubric_red_flags,
                ratio=self.ratio,
                red_flags=self.red_flags,
                confidence=self.confidence,
                quality=self.quality,
                # Har chaqiruvda boshqacha ball — 50 ta bir xil 76 emas,
                # haqiqiy taqsimotga o'xshash natija chiqsin
                seed=self.seed + self.calls,
            ),
            ensure_ascii=False,
        )

    async def ping(self) -> str:
        return "OK"


def build_payload(
    rubric_blocks: list[dict[str, Any]],
    rubric_red_flags: list[dict[str, Any]],
    *,
    ratio: float = 0.8,
    red_flags: tuple[str, ...] = (),
    confidence: float = 0.92,
    quality: str = "high",
    seed: int = 0,
    overall_override: int | None = None,
    invented_flag: str | None = None,
) -> dict[str, Any]:
    """Rubrikaga mos, arifmetikasi TO'G'RI javob quradi.

    `overall_override` va `invented_flag` — ataylab buzilgan javob
    yasash uchun (validatsiya sinovlari).
    """
    rng = random.Random(seed)
    blocks: dict[str, Any] = {}
    total = 0

    for block in rubric_blocks:
        criteria = []
        block_total = 0
        for criterion in block.get("criteria", []):
            points = int(criterion.get("points", 0))
            noise = rng.uniform(-0.15, 0.15)
            score = max(0, min(points, round(points * (ratio + noise))))
            block_total += score
            criteria.append(
                {
                    "id": criterion["id"],
                    "score": score,
                    "verdict": "pass" if score >= points * 0.8 else "partial",
                    "evidence": f"[00:1{rng.randint(0, 9)}] — stub dalil ({criterion['id']})",
                    "improvement": None if score == points else "Yaxshilash mumkin",
                }
            )
        blocks[block["key"]] = {"score": block_total, "criteria": criteria}
        total += block_total

    known = {f["type"]: f for f in rubric_red_flags}
    flags = []
    penalty = 0
    zeroed = False
    for flag_type in red_flags:
        spec = known.get(flag_type)
        if spec is None:
            continue
        penalty += int(spec.get("penalty", 0))
        zeroed = zeroed or bool(spec.get("zeroes_score"))
        flags.append(
            {
                "type": flag_type,
                "severity": "high",
                "timestamp": "07:42",
                "quote": "stub iqtibos",
            }
        )
    if invented_flag:
        flags.append(
            {
                "type": invented_flag,
                "severity": "high",
                "timestamp": "03:11",
                "quote": "stub iqtibos",
            }
        )

    overall = 0 if zeroed else max(0, min(100, total + penalty))

    return {
        "language_detected": "mixed",
        "transcript_quality": quality,
        "blocks": blocks,
        "red_flags": flags,
        "outcome_signal": {
            "type": "follow_up",
            "products_mentioned": ["X-200", "Y-50"],
            "quantity_mentioned": 50,
            "confidence": 0.7,
            "evidence": "[00:58] — «Mayli, ertaga aytaman»",
        },
        "client_sentiment": "neutral",
        "coaching_note": (
            "Mahsulot yaxshi taqdim etildi. E'tiroz bilan ishlashni "
            "kuchaytiring: narx e'tirozidan keyin qiymat argumenti kerak edi."
        ),
        "confidence": confidence,
        "overall_score": overall if overall_override is None else overall_override,
    }


# ── Yozuv oqimi ───────────────────────────────────────────────


@dataclass
class StubStream:
    content_type: str
    chunks: AsyncIterator[bytes]


def stub_recording(size_bytes: int = 512 * 1024, chunk_size: int = 64 * 1024):
    """`PipelineDeps.open_recording` o'rniga qo'yiladigan fabrika.

    Baytlar generatordan chiqadi — hech qayerda to'planmaydi va
    diskka yozilmaydi (aynan haqiqiy MoyZvonki oqimi kabi).
    """

    @asynccontextmanager
    async def opener(_session: Any, _audio_key: str) -> AsyncIterator[StubStream]:
        async def gen() -> AsyncIterator[bytes]:
            import asyncio

            block = b"\xff\xfb\x90\x64" + bytes(chunk_size - 4)
            sent = 0
            while sent < size_bytes:
                take = min(chunk_size, size_bytes - sent)
                sent += take
                # Haqiqiy tarmoq oqimi kabi boshqaruvni qaytaramiz
                await asyncio.sleep(0)
                yield block[:take]

        yield StubStream(content_type="audio/mpeg", chunks=gen())

    return opener
