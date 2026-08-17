"""«Tekshirish» tugmasi ortidagi mantiq.

Admin kalitni kiritgach darhol bilishi kerak: ishladimi yoki yo'q.
Aks holda xato faqat birinchi qo'ng'iroq baholanganda — soatlar keyin —
ma'lum bo'ladi.

Chaqiruv eng arzoni: LLM uchun bir necha tokenlik so'rov, ASR uchun bir
soniyalik jimlik.
"""

from time import perf_counter
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ai.application.factory import (
    MODEL_SETTING,
    PROVIDER_SETTING,
    build_client,
    resolve_from_values,
)
from src.modules.ai.domain.entities import AI_ROLES, ROLE_LABEL_UZ
from src.modules.ai.domain.errors import AIError, translate
from src.modules.ai.domain.registry import default_provider_key, get_provider
from src.modules.settings.application.services import SettingsService

log = structlog.get_logger(__name__)


async def run_connection_test(
    session: AsyncSession,
    role: str,
    *,
    http_client: Any | None = None,
    http_args: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Haqiqiy (lekin eng arzon) chaqiruv qiladi va natijani qaytaradi.

    Hech qachon exception ko'tarmaydi — javob doim 200, ichida `ok`.
    """
    if role not in AI_ROLES:
        return {
            "ok": False,
            "role": role,
            "code": "ai_bad_role",
            "error": f"Noma'lum rol: «{role}». Faqat: {', '.join(AI_ROLES)}",
        }

    values = await SettingsService(session).get_all_values()
    configured_provider = (
        str(values.get(PROVIDER_SETTING[role]) or "") or default_provider_key(role)
    )
    configured_model = str(values.get(MODEL_SETTING[role]) or "") or None

    # Xato bo'lsa ham UI qaysi provayder/model haqida gap ketayotganini ko'rsin
    known = get_provider(configured_provider)
    if known is not None and configured_model is None and known.supports(role):
        configured_model = known.default_model(role)

    result: dict[str, Any] = {
        "ok": False,
        "role": role,
        "role_label": ROLE_LABEL_UZ[role],
        "provider": configured_provider,
        "provider_label": known.label if known else None,
        "model": configured_model,
        "latency_ms": 0,
    }

    started = perf_counter()
    try:
        resolution = resolve_from_values(values, role)
        result["provider"] = resolution.provider.key
        result["provider_label"] = resolution.provider.label
        result["model"] = resolution.model
        client = build_client(
            resolution, http_client=http_client, http_args=http_args, timeout=timeout
        )
        answer = await client.ping()
    except Exception as exc:  # noqa: BLE001 — foydalanuvchiga o'zbekcha sabab
        error: AIError = (
            exc
            if isinstance(exc, AIError)
            else translate(
                exc,
                provider_label=result["provider_label"] or "AI provayder",
                model=result["model"] or "?",
                secrets=(),
            )
        )
        result["latency_ms"] = _elapsed(started)
        result["error"] = error.message
        result["code"] = error.code
        # Loglarda kalit yo'q: faqat provayder, model va xato kodi
        log.warning(
            "ai.test.failed",
            role=role,
            provider=result["provider"],
            model=result["model"],
            code=error.code,
        )
        return result

    result["latency_ms"] = _elapsed(started)
    result["ok"] = True
    result["key_source"] = resolution.key_source
    result["detail"] = _detail(role, answer, result["latency_ms"])
    log.info(
        "ai.test.ok",
        role=role,
        provider=result["provider"],
        model=result["model"],
        latency_ms=result["latency_ms"],
    )
    return result


def _elapsed(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _detail(role: str, answer: str, latency_ms: int) -> str:
    trimmed = " ".join((answer or "").split())[:120]
    label = ROLE_LABEL_UZ[role]
    if trimmed:
        return f"{label} ishladi ({latency_ms} ms). Javob: «{trimmed}»"
    return f"{label} ishladi ({latency_ms} ms)."
