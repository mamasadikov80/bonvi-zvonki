"""Vendorda HOZIR mavjud modellar ro'yxati.

NEGA BU MODUL BOR. Model nomlari ilgari kodda qo'lda yozilgan ro'yxatdan
kelardi. Vendor modelni yopib qo'yganda ro'yxat eskirar, admin esa
ishlamaydigan modelni tanlar edi — xato faqat birinchi baholashda,
soatlar keyin chiqardi. Aynan shunday bo'ldi: `gemini-2.5-pro` yangi
akkauntlarda yopilgan, lekin standart qiymat sifatida turgan edi.

Endi ro'yxat provayderning O'Z API'sidan olinadi. Vendor yangi model
chiqarsa — u o'zi paydo bo'ladi, kodga tegilmaydi.

Zaxira: kalit yo'q, tarmoq yo'q yoki vendor javob bermasa — reyestrdagi
qo'lda yozilgan ro'yxat ishlatiladi va javobda `source: "fallback"`
turadi, ya'ni UI buni yashirmasdan ko'rsata oladi.
"""

import time
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError
from src.modules.ai.application.factory import build_client, resolve
from src.modules.ai.domain.entities import AIProvider

log = structlog.get_logger(__name__)

#: Ro'yxat tez-tez o'zgarmaydi, lekin sozlamalar sahifasi har ochilganda
#: so'ralishi mumkin. 10 daqiqa — vendorni ham, sahifani ham qiynamaydi.
CACHE_TTL_SEC = 600


@dataclass(slots=True)
class ModelCatalog:
    """Bitta rol uchun model ro'yxati va uning kelib chiqishi."""

    role: str
    provider_key: str
    provider_label: str
    models: list[str]
    default: str
    #: `live` — vendordan olindi, `fallback` — reyestrdagi zaxira
    source: str
    #: Zaxiraga tushgan bo'lsa — sababi (UI ko'rsatishi mumkin)
    note: str | None = None


_cache: dict[tuple[str, str], tuple[float, list[str]]] = {}


def _cached(provider_key: str, role: str) -> list[str] | None:
    hit = _cache.get((provider_key, role))
    if hit is None:
        return None
    stamp, models = hit
    if time.monotonic() - stamp > CACHE_TTL_SEC:
        return None
    return models


def _order(models: list[str], provider: AIProvider, role: str) -> list[str]:
    """Tavsiya etilganlar tepada, qolgani alifbo bo'yicha.

    Vendor ro'yxati yuzlab yozuvdan iborat bo'lishi mumkin va u hech
    qanday tartibda kelmaydi. Admin ochganda birinchi ko'rishi kerak
    bo'lgan narsa — biz sinab ko'rgan modellar.
    """
    known = [m for m in provider.suggested_models(role) if m in models]
    rest = sorted(set(models) - set(known))
    return known + rest


async def load_catalog(session: AsyncSession, role: str) -> ModelCatalog:
    """Joriy provayder uchun model ro'yxati. HECH QACHON xato ko'tarmaydi."""
    try:
        resolution = await resolve(session, role)
    except AppError as exc:
        # Provayder tanlanmagan yoki kalit yo'q — ro'yxat ham yo'q
        from src.modules.ai.domain.registry import default_provider_key, get_provider

        provider = get_provider(default_provider_key(role))
        return ModelCatalog(
            role=role,
            provider_key=provider.key if provider else "",
            provider_label=provider.label if provider else "",
            models=list(provider.suggested_models(role)) if provider else [],
            default=provider.default_model(role) if provider else "",
            source="fallback",
            note=str(exc),
        )

    provider = resolution.provider
    fallback = ModelCatalog(
        role=role,
        provider_key=provider.key,
        provider_label=provider.label,
        models=list(provider.suggested_models(role)),
        default=provider.default_model(role),
        source="fallback",
    )

    cached = _cached(provider.key, role)
    if cached is not None:
        return ModelCatalog(
            role=role,
            provider_key=provider.key,
            provider_label=provider.label,
            models=_order(cached, provider, role),
            default=provider.default_model(role),
            source="live",
        )

    try:
        client = build_client(resolution, timeout=20.0)
        models = await client.list_models()
    except Exception as exc:  # noqa: BLE001 — ro'yxat hech qachon sahifani buzmasin
        log.warning("ai.catalog_failed", role=role, provider=provider.key, error=str(exc))
        fallback.note = "Vendor ro'yxatni bermadi — tavsiya etilganlar ko'rsatilyapti"
        return fallback

    if not models:
        fallback.note = "Vendor ro'yxatni bermadi — tavsiya etilganlar ko'rsatilyapti"
        return fallback

    _cache[(provider.key, role)] = (time.monotonic(), models)
    return ModelCatalog(
        role=role,
        provider_key=provider.key,
        provider_label=provider.label,
        models=_order(models, provider, role),
        default=provider.default_model(role),
        source="live",
    )


def as_dict(catalog: ModelCatalog) -> dict[str, Any]:
    return {
        "role": catalog.role,
        "provider": catalog.provider_key,
        "provider_label": catalog.provider_label,
        "models": catalog.models,
        "default": catalog.default,
        "source": catalog.source,
        "note": catalog.note,
    }
