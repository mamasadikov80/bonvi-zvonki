"""AI provayderlari domeni — sof Python, hech qanday vendor SDK'siga bog'liq emas.

Bu yerda ikkita narsa yashaydi:

1. **Umumiy interfeys** (`ASRClient`, `LLMClient`) — chaqiruvchi kod qaysi
   vendor ortida turganini BILMAYDI. Provayder almashtirilganda chaqiruv
   joyi o'zgarmaydi.
2. **Provayder tavsifi** (`AIProvider`) — reyestrdagi bitta yozuv.
   Yangi provayder qo'shish = shu yozuvdan yana bittasini yozish.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── Rollar ────────────────────────────────────────────────────
# ASR: audio → matn.   LLM: matn → baho.
ROLE_ASR = "asr"
ROLE_LLM = "llm"
AI_ROLES: tuple[str, ...] = (ROLE_ASR, ROLE_LLM)

ROLE_LABEL_UZ: dict[str, str] = {
    ROLE_ASR: "Nutqni matnga (ASR)",
    ROLE_LLM: "AI baholovchi (LLM)",
}


# ── Transkript ────────────────────────────────────────────────


@dataclass(slots=True)
class TranscriptSegment:
    """Bitta gapiruvchining bitta bo'lagi."""

    text: str
    speaker: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None


@dataclass(slots=True)
class Transcript:
    """ASR natijasi — provayderdan qat'i nazar bir xil shakl."""

    text: str
    provider: str
    model: str
    language: str | None = None
    duration_ms: int | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def has_diarization(self) -> bool:
        return any(s.speaker for s in self.segments)


# ── Klient interfeyslari ──────────────────────────────────────


@runtime_checkable
class ASRClient(Protocol):
    """Audio oqimini matnga o'giradi.

    `audio` — `AsyncIterator[bytes]`. Diskka HECH QACHON yozilmaydi:
    oqim xotirada yig'iladi va to'g'ridan-to'g'ri provayderga uzatiladi.
    """

    provider_key: str
    model: str

    async def transcribe(
        self,
        audio: AsyncIterator[bytes],
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript: ...

    async def ping(self) -> str:
        """Eng arzon haqiqiy chaqiruv — sozlamani tekshirish uchun."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Matndan matn (yoki JSON) hosil qiladi."""

    provider_key: str
    model: str

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str: ...

    async def ping(self) -> str:
        """Eng arzon haqiqiy chaqiruv — sozlamani tekshirish uchun."""
        ...


# ── Provayder tavsifi ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AIProvider:
    """Reyestrdagi BITTA yozuv.

    `client_kind` — qaysi protokol bilan gaplashadi. Shu tufayli
    OpenAI-mos (OpenAI-compatible) yangi vendor qo'shish uchun kodga
    umuman tegilmaydi: `client_kind="openai_compat"` + `base_url` yetarli.
    """

    key: str
    label: str
    roles: frozenset[str]
    api_key_setting: str
    key_label_uz: str
    models: dict[str, list[str]]
    defaults: dict[str, str]
    docs_url: str
    client_kind: str
    #: Vendor SDK paketi — o'rnatilmagan bo'lsa xatoda shu nom ko'rsatiladi
    sdk_package: str
    #: OpenAI-mos provayderlar uchun manzil (rasmiy OpenAI uchun None)
    base_url: str | None = None
    #: `.env` dagi zaxira o'zgaruvchi (baza > .env > standart)
    env_var: str | None = None
    #: Eski (`asr.*` / `llm.*`) sozlamalar — yangi kalit bo'sh bo'lsa shundan olinadi
    legacy_key_settings: tuple[str, ...] = ()
    hint_uz: str | None = None

    def __post_init__(self) -> None:
        unknown = self.roles - set(AI_ROLES)
        if unknown:
            raise ValueError(f"{self.key}: noma'lum rol {sorted(unknown)}")
        if not self.roles:
            raise ValueError(f"{self.key}: kamida bitta rol bo'lishi kerak")
        for role in self.roles:
            if not self.defaults.get(role):
                raise ValueError(f"{self.key}: '{role}' uchun standart model yo'q")

    def supports(self, role: str) -> bool:
        return role in self.roles

    def default_model(self, role: str) -> str:
        return self.defaults[role]

    def suggested_models(self, role: str) -> list[str]:
        return list(self.models.get(role, ()))
