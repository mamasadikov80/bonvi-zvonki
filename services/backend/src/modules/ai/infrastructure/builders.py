"""`client_kind` → klient klassi.

Reyestrdagi yozuv qaysi protokol bilan gaplashishini `client_kind` orqali
aytadi. Shu sabab OpenAI-mos yangi vendor qo'shish uchun BU FAYLGA HAM
tegilmaydi — mavjud `openai_compat` qatoridan foydalaniladi.

⚠️ Bu modul vendor SDK'larini IMPORT QILMAYDI. SDK faqat klient haqiqiy
chaqiruv qilayotganda (`_build_sdk`) import qilinadi — shuning uchun
vendor kutubxonasi o'rnatilmagan bo'lsa ham backend ko'tariladi.
"""

from collections.abc import Callable
from typing import Any

from src.modules.ai.domain.entities import AI_ROLES, ROLE_ASR, ROLE_LLM, AIProvider
from src.modules.ai.domain.registry import AI_PROVIDERS
from src.modules.ai.infrastructure.providers.anthropic_provider import (
    AnthropicLLMClient,
)
from src.modules.ai.infrastructure.providers.base import ClientConfig
from src.modules.ai.infrastructure.providers.gemini_provider import (
    GeminiASRClient,
    GeminiLLMClient,
)
from src.modules.ai.infrastructure.providers.openai_compat import (
    OpenAICompatASRClient,
    OpenAICompatLLMClient,
)

Builder = Callable[[ClientConfig], Any]

BUILDERS: dict[str, dict[str, Builder]] = {
    "openai_compat": {
        ROLE_ASR: OpenAICompatASRClient,
        ROLE_LLM: OpenAICompatLLMClient,
    },
    "anthropic": {
        ROLE_LLM: AnthropicLLMClient,
    },
    "gemini": {
        ROLE_ASR: GeminiASRClient,
        ROLE_LLM: GeminiLLMClient,
    },
}


def builder_for(provider: AIProvider, role: str) -> Builder:
    kind = BUILDERS.get(provider.client_kind)
    if kind is None:  # pragma: no cover — `check_registry()` buni oldini oladi
        raise KeyError(f"{provider.key}: noma'lum client_kind={provider.client_kind}")
    builder = kind.get(role)
    if builder is None:  # pragma: no cover
        raise KeyError(f"{provider.key}: {role} roli uchun klient yo'q")
    return builder


def check_registry() -> list[str]:
    """Reyestr va klientlar bir-biriga mos kelishini tekshiradi.

    Bo'sh ro'yxat = hammasi joyida. Test shu funksiyani chaqiradi.
    """
    problems: list[str] = []
    for provider in AI_PROVIDERS:
        kind = BUILDERS.get(provider.client_kind)
        if kind is None:
            problems.append(f"{provider.key}: client_kind={provider.client_kind} yo'q")
            continue
        for role in AI_ROLES:
            if provider.supports(role) and role not in kind:
                problems.append(f"{provider.key}: '{role}' uchun klient yo'q")
    return problems
