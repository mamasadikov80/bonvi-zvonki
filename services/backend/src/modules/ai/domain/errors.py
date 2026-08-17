"""AI xatoliklari — vendor xatosi → aniq o'zbekcha sabab.

Ikkita qat'iy qoida:

1. **Kalit hech qachon xabarga tushmaydi.** Vendor matni foydalanuvchiga
   yetib borishidan oldin `redact()` dan o'tadi: sozlangan maxfiy
   qiymatlar ham, kalitga o'xshash naqshlar ham yo'q qilinadi.
   Jonli API kaliti chiqib ketgan stack-trace — bu haqiqiy insident.
2. **401 uchun vendor matni umuman ko'rsatilmaydi.** Ba'zi provayderlar
   401 javobida kalitning bir qismini qaytaradi.
"""

import re
from typing import Any

from src.core.exceptions import AppError

# ── Maxfiy qiymatlarni tozalash ───────────────────────────────

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"gsk_[A-Za-z0-9_\-]{12,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxi-api-key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:api[_\-]?key|authorization|bearer)\b\s*[:=]\s*\S+", re.IGNORECASE),
)

REDACTED = "«yashirildi»"


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Matndan maxfiy qiymatlarni olib tashlaydi.

    `secrets` — hozir sozlangan haqiqiy kalitlar. Ular aynan mos kelgan
    joyda kesiladi; qolgani naqsh bo'yicha topiladi.
    """
    cleaned = text or ""
    for secret in secrets:
        if secret and len(secret) >= 6:
            cleaned = cleaned.replace(secret, REDACTED)
            # Ba'zi provayderlar kalitni qisqartirib qaytaradi (sk-abc…xyz)
            cleaned = cleaned.replace(secret[:8], REDACTED)
            cleaned = cleaned.replace(secret[-8:], REDACTED)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(REDACTED, cleaned)
    return cleaned


def _short(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── Xatolik turlari ───────────────────────────────────────────


class AIError(AppError):
    """Barcha AI xatoliklarining asosi."""

    status_code = 502
    code = "ai_error"


class AIConfigError(AIError):
    """Bizning sozlamamiz noto'g'ri — vendor aybdor emas."""

    status_code = 409
    code = "ai_not_configured"


class AIDependencyError(AIError):
    """Vendor SDK'si o'rnatilmagan."""

    status_code = 503
    code = "ai_sdk_missing"


class AIAuthError(AIError):
    code = "ai_auth"


class AIModelError(AIError):
    code = "ai_model"


class AIRateLimitError(AIError):
    status_code = 429
    code = "ai_rate_limit"


class AIRequestError(AIError):
    code = "ai_bad_request"


class AIUnavailableError(AIError):
    code = "ai_unavailable"


class AINetworkError(AIError):
    code = "ai_network"


# ── Tayyor o'zbekcha xabarlar ─────────────────────────────────


def missing_key(provider_label: str, setting_key: str) -> AIConfigError:
    return AIConfigError(
        f"{provider_label} uchun API kalit kiritilmagan — Sozlamalar → AI "
        f"bo'limida «{setting_key}» ni to'ldiring"
    )


def unknown_provider(key: str, role: str, known: list[str]) -> AIConfigError:
    return AIConfigError(
        f"Noma'lum AI provayderi: «{key}». «{role}» roli uchun mavjudlari: "
        + ", ".join(known)
    )


def role_not_supported(provider_label: str, role: str) -> AIConfigError:
    return AIConfigError(
        f"{provider_label} «{role}» roli uchun ishlatilmaydi — "
        "Sozlamalar → AI bo'limida boshqa provayder tanlang"
    )


def sdk_missing(provider_label: str, package: str) -> AIDependencyError:
    return AIDependencyError(
        f"{provider_label} kutubxonasi o'rnatilmagan ({package}) — "
        "backend konteynerini qayta qurish kerak"
    )


def audio_too_large(limit_mb: int) -> AIRequestError:
    return AIRequestError(
        f"Audio juda katta — {limit_mb} MB dan oshdi, qayta ishlanmadi"
    )


# ── Vendor xatosini tarjima qilish ────────────────────────────


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response: Any = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _message_of(exc: BaseException) -> str:
    for attr in ("message", "detail"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return str(exc)


def _is_network(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if any(token in name for token in ("timeout", "connect", "transport", "ssl")):
        return True
    module = type(exc).__module__.split(".")[0]
    if module in {"httpx", "httpcore", "aiohttp"} and _status_of(exc) is None:
        return True
    return isinstance(exc, (OSError, ConnectionError, TimeoutError))


_MODEL_HINTS = ("model", "модель", "not_found", "does not exist", "unknown model")

#: Ba'zi provayderlar (masalan Gemini) noto'g'ri kalitga 401 emas, 400 qaytaradi —
#: shuning uchun holat kodiga qo'shimcha matn ham tekshiriladi.
_AUTH_HINTS = (
    "api key not valid",
    "invalid api key",
    "incorrect api key",
    "api_key_invalid",
    "invalid_api_key",
    "invalid authentication",
    "authentication_error",
    "unauthenticated",
    "unauthorized",
    "missing api key",
    "no api key",
    "api kaliti",
)


def translate(
    exc: BaseException,
    *,
    provider_label: str,
    model: str,
    secrets: tuple[str, ...] = (),
) -> AIError:
    """Istalgan vendor xatosini o'zbekcha `AIError` ga aylantiradi."""
    if isinstance(exc, AIError):
        return exc

    if isinstance(exc, ModuleNotFoundError):
        return sdk_missing(provider_label, exc.name or "?")

    if _is_network(exc):
        return AINetworkError(
            f"{provider_label} serveriga ulanib bo'lmadi — internet yoki "
            "provayder manzilini tekshiring"
        )

    status = _status_of(exc)
    raw = _message_of(exc)
    detail = _short(redact(raw, secrets))
    lowered = raw.lower()

    if status in (401, 403) or any(hint in lowered for hint in _AUTH_HINTS):
        # Vendor matni ataylab ko'rsatilmaydi — ichida kalit bo'lishi mumkin
        return AIAuthError(
            f"{provider_label} API kalit noto'g'ri yoki bekor qilingan — "
            "Sozlamalar → AI bo'limida kalitni yangilang"
        )

    if status == 404 or (
        status in (400, 422) and any(hint in lowered for hint in _MODEL_HINTS)
    ):
        return AIModelError(
            f"«{model}» modelini {provider_label} tanimadi — model nomini "
            f"tekshiring. Provayder javobi: {detail}"
        )

    if status == 429:
        return AIRateLimitError(
            f"{provider_label} so'rovlar chegarasiga yetdi (429) — biroz kutib "
            "qayta urinib ko'ring"
        )

    if status is not None and status >= 500:
        return AIUnavailableError(
            f"{provider_label} serveri javob bermadi ({status}) — keyinroq urinib ko'ring"
        )

    if status is not None and 400 <= status < 500:
        return AIRequestError(
            f"{provider_label} so'rovni qabul qilmadi ({status}): {detail}"
        )

    return AIError(f"{provider_label} bilan ishlashda kutilmagan xato: {detail}")
