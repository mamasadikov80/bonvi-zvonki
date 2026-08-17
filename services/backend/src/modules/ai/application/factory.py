"""AI klient fabrikasi.

Chaqiruvchi kod faqat shuni biladi:

    asr = await get_asr_client(session)
    llm = await get_llm_client(session)

Qaysi vendor ortida turgani — sozlamada. Provayder almashtirilganda
chaqiruv joyi o'zgarmaydi.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ai.domain.entities import (
    ROLE_ASR,
    ROLE_LLM,
    AIProvider,
    ASRClient,
    LLMClient,
)
from src.modules.ai.domain.errors import (
    missing_key,
    role_not_supported,
    unknown_provider,
)
from src.modules.ai.domain.registry import (
    default_provider_key,
    get_provider,
    providers_for_role,
)
from src.modules.ai.infrastructure.builders import builder_for
from src.modules.ai.infrastructure.providers.base import ClientConfig
from src.modules.settings.application.services import SettingsService

#: Sozlama kalitlari — reyestrga bog'liq emas, provayderdan qat'i nazar bir xil
PROVIDER_SETTING = {ROLE_ASR: "ai.asr_provider", ROLE_LLM: "ai.llm_provider"}
MODEL_SETTING = {ROLE_ASR: "ai.asr_model", ROLE_LLM: "ai.llm_model"}


@dataclass(slots=True)
class AIResolution:
    """Sozlamalardan hisoblangan joriy holat."""

    role: str
    provider: AIProvider
    model: str
    api_key: str
    key_source: str  # "ai" | "legacy"


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def resolve_from_values(values: dict[str, Any], role: str) -> AIResolution:
    """Sozlama qiymatlaridan provayder/model/kalitni aniqlaydi.

    Bazaga tegmaydi — shuning uchun testda ham, ish vaqtida ham bir xil.
    """
    provider_key = _clean(values.get(PROVIDER_SETTING[role])) or default_provider_key(
        role
    )
    provider = get_provider(provider_key)
    if provider is None:
        raise unknown_provider(
            provider_key, role, [p.key for p in providers_for_role(role)]
        )
    if not provider.supports(role):
        raise role_not_supported(provider.label, role)

    model = _clean(values.get(MODEL_SETTING[role])) or provider.default_model(role)

    api_key = _clean(values.get(provider.api_key_setting))
    key_source = "ai"
    if not api_key:
        # Eski sozlamada kalit bor bo'lsa qayta kiritishga majburlamaymiz
        for legacy in provider.legacy_key_settings:
            api_key = _clean(values.get(legacy))
            if api_key:
                key_source = "legacy"
                break
    if not api_key:
        raise missing_key(provider.label, provider.api_key_setting)

    return AIResolution(
        role=role,
        provider=provider,
        model=model,
        api_key=api_key,
        key_source=key_source,
    )


async def resolve(session: AsyncSession, role: str) -> AIResolution:
    values = await SettingsService(session).get_all_values()
    return resolve_from_values(values, role)


def build_client(
    resolution: AIResolution,
    *,
    http_client: Any | None = None,
    http_args: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> Any:
    """Klientni yaratadi. `http_client` — faqat test uchun (stub transport)."""
    config = ClientConfig(
        provider=resolution.provider,
        role=resolution.role,
        model=resolution.model,
        api_key=resolution.api_key,
        http_client=http_client,
        http_args=dict(http_args or {}),
        timeout=timeout,
    )
    return builder_for(resolution.provider, resolution.role)(config)


async def get_asr_client(session: AsyncSession, **kwargs: Any) -> ASRClient:
    """Joriy ASR klienti. Kalit yo'q bo'lsa aniq o'zbekcha xato beradi."""
    return build_client(await resolve(session, ROLE_ASR), **kwargs)


async def get_llm_client(session: AsyncSession, **kwargs: Any) -> LLMClient:
    """Joriy LLM klienti. Kalit yo'q bo'lsa aniq o'zbekcha xato beradi."""
    return build_client(await resolve(session, ROLE_LLM), **kwargs)
