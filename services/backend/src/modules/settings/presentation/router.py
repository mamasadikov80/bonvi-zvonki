"""Sozlamalar endpointlari.

Faqat ADMIN yozishi mumkin. MANAGER ko'ra oladi (maxfiy kalitlarsiz).

Bundan tashqari ikkita ICHKI endpoint bor (`/bot-config`, `/bot-identity`) —
ular Telegram bot uchun. Bot foydalanuvchi emas, unda JWT yo'q, shuning uchun
himoya `X-Internal-Token` umumiy maxfiy kaliti orqali beriladi.
"""

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from src.core.config import settings as env_settings
from src.core.deps import CurrentUser, DbSession, RequireAdmin, require_permission
from src.core.exceptions import AppError, UnauthorizedError, ValidationError
from src.modules.ai.application.catalog import as_dict, load_catalog
from src.modules.ai.application.factory import resolve_from_values
from src.modules.ai.application.tester import run_connection_test
from src.modules.ai.domain.entities import AI_ROLES, ROLE_ASR, ROLE_LLM
from src.modules.ai.domain.registry import AI_PROVIDERS
from src.modules.settings.application.services import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


class UpdateSettingsRequest(BaseModel):
    values: dict[str, Any]


# ══════════════════════════════════════════════════════════════
#  ICHKI XIZMATLAR HIMOYASI
#
#  ⚠️  "Docker ichki tarmog'ida turibdi" — bu HIMOYA EMAS.
#      docker-compose.yml da backend porti hostga chiqarilgan
#      (`8010:8000`), ya'ni kompyuterdagi (yoki serverdagi) istalgan
#      jarayon `http://localhost:8010/api/v1/settings/bot-config`
#      manzilini bemalol so'rashi mumkin. Bu endpoint esa Telegram
#      bot tokenini MASKASIZ qaytaradi — token qo'lga tushsa,
#      begona odam bot nomidan yozadi va so'rovnoma javoblarini
#      o'g'irlaydi.
#
#      Shuning uchun har bir so'rovda `X-Internal-Token` sarlavhasi
#      talab qilinadi va u `INTERNAL_API_TOKEN` (.env) bilan
#      taqqoslanadi. Taqqoslash `secrets.compare_digest` orqali —
#      vaqt bo'yicha hujumga (timing attack) yo'l qo'ymaslik uchun.
#      `INTERNAL_API_TOKEN` bo'sh bo'lsa endpointlar butunlay yopiq
#      (fail-closed): sozlanmagan tizim ochiq qolib ketmasin.
# ══════════════════════════════════════════════════════════════


async def require_internal_token(
    x_internal_token: str | None = Header(
        default=None,
        alias="X-Internal-Token",
        description="Ichki xizmatlar kaliti (.env → INTERNAL_API_TOKEN)",
    ),
) -> None:
    expected = env_settings.INTERNAL_API_TOKEN
    if not expected:
        raise UnauthorizedError("INTERNAL_API_TOKEN sozlanmagan — ichki API yopiq")
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise UnauthorizedError("X-Internal-Token yaroqsiz")


InternalOnly = Depends(require_internal_token)


@router.get(
    "",
    summary="Barcha sozlamalar (kategoriyalar bo'yicha)",
    dependencies=[Depends(require_permission("settings:read"))],
)
async def list_settings(session: DbSession, user: CurrentUser):
    """UI shu javob asosida formani avtomatik quradi.

    Maxfiy qiymatlar qaytarilmaydi — faqat `is_set` bayrog'i.
    """
    return await SettingsService(session).list_for_ui()


@router.put("", summary="Sozlamalarni saqlash")
async def update_settings(
    payload: UpdateSettingsRequest,
    session: DbSession,
    user: RequireAdmin,
):
    service = SettingsService(session)
    await service.set_many(payload.values, user_id=user.id)
    await session.commit()
    return await service.list_for_ui()


# ══════════════════════════════════════════════════════════════
#  AI PROVAYDERLARI
#
#  Ro'yxat ham, tekshiruv ham `modules/ai` reyestridan quriladi —
#  bu yerda birorta provayder nomi qo'lda yozilmagan.
# ══════════════════════════════════════════════════════════════


class AITestRequest(BaseModel):
    role: Literal["asr", "llm"] = Field(
        description="Qaysi rol tekshiriladi: audio→matn (asr) yoki baholovchi (llm)"
    )


@router.get(
    "/ai/providers",
    summary="AI provayderlari reyestri (rollar va model takliflari)",
    dependencies=[Depends(require_permission("settings:read"))],
)
async def ai_providers() -> list[dict[str, Any]]:
    """UI shu javob asosida provayder va model takliflarini ko'rsatadi.

    Model ro'yxati — faqat TAKLIF. Admin istalgan model nomini qo'lda
    kiritishi mumkin, shuning uchun vendor yangi model chiqarganda kodga
    tegilmaydi.
    """
    return [
        {
            "key": provider.key,
            "label": provider.label,
            "roles": sorted(provider.roles),
            "api_key_setting": provider.api_key_setting,
            "key_label": provider.key_label_uz,
            "models": {role: provider.suggested_models(role) for role in AI_ROLES},
            "default_models": {
                role: provider.default_model(role)
                for role in AI_ROLES
                if provider.supports(role)
            },
            "docs_url": provider.docs_url,
            "hint": provider.hint_uz,
        }
        for provider in AI_PROVIDERS
    ]


@router.get(
    "/ai/models",
    summary="Vendorda hozir mavjud modellar (jonli ro'yxat)",
    dependencies=[Depends(require_permission("settings:read"))],
)
async def ai_models(session: DbSession) -> list[dict[str, Any]]:
    """Har rol uchun tanlangan provayderning JONLI model ro'yxati.

    Ro'yxat vendorning o'z API'sidan olinadi — kodda qo'lda yozilgan
    ro'yxatdan emas. Vendor yangi model chiqarsa u o'zi paydo bo'ladi,
    yopib qo'ysa — o'zi yo'qoladi.

    Vendor javob bermasa xato QAYTARILMAYDI: reyestrdagi zaxira ro'yxat
    beriladi va `source: "fallback"` deb belgilanadi.
    """
    return [as_dict(await load_catalog(session, role)) for role in (ROLE_ASR, ROLE_LLM)]


@router.post(
    "/ai/test",
    summary="Tanlangan AI provayderni haqiqiy chaqiruv bilan tekshirish",
    dependencies=[Depends(require_permission("settings:write"))],
)
async def ai_test(payload: AITestRequest, session: DbSession) -> dict[str, Any]:
    """Eng arzon haqiqiy chaqiruv qiladi (LLM — bir necha token,
    ASR — bir soniyalik jimlik) va natijani darhol qaytaradi.

    Javob doim 200: ichida `ok: true` yoki `ok: false` + o'zbekcha sabab.
    Kalitning o'zi javobga ham, logga ham HECH QACHON tushmaydi.
    """
    return await run_connection_test(session, payload.role)


# ── Bot uchun ichki endpointlar ───────────────────────────────


class BotConfigResponse(BaseModel):
    """Bot uchun HAQIQIY qiymatlar — maskasiz."""

    bot_token: str = ""
    bot_username: str = ""
    miniapp_name: str = ""
    """BotFather'dagi Mini App short name. Bo'sh bo'lsa bot eski oqimda
    (guruhdagi 1-5 tugmalari) ishlashda davom etadi."""

    survey_mode: str = "miniapp"
    """`miniapp` yoki `buttons` — admin panelidagi ANIQ tanlov.

    Ilgari rejim faqat `miniapp_name` bo'sh yoki to'laligidan bilvosita
    chiqarilardi: tugmalar rejimiga o'tish uchun admin qisqa nomni
    o'chirib tashlashi kerak edi va keyin uni qayta terib chiqardi.
    Endi tanlov alohida turadi, qisqa nom esa joyida saqlanadi —
    rejimni ikki tomonga ham bir bosishda almashtirsa bo'ladi."""


class BotIdentityRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


@router.get(
    "/bot-config",
    summary="[ichki] Bot konfiguratsiyasi",
    response_model=BotConfigResponse,
    dependencies=[InternalOnly],
)
async def bot_config(session: DbSession) -> BotConfigResponse:
    """Telegram bot ishga tushganda va davriy ravishda shu yerdan o'qiydi.

    Qiymat `SettingsService` ustuvorligi bo'yicha hisoblanadi:
    baza > .env > standart. Ya'ni admin Sozlamalar sahifasida tokenni
    o'zgartirsa, bot keyingi tekshiruvda yangisini oladi.

    Oddiy `GET /settings` dan farqi: bu yerda token MASKALANMAYDI.
    Shuning uchun `X-Internal-Token` majburiy.
    """
    values = await SettingsService(session).get_all_values()
    return BotConfigResponse(
        bot_token=str(values.get("telegram.bot_token") or ""),
        bot_username=str(values.get("telegram.bot_username") or "").lstrip("@"),
        miniapp_name=str(values.get("telegram.miniapp_name") or "").strip(),
        survey_mode=str(values.get("survey.mode") or "miniapp").strip(),
    )


@router.post(
    "/bot-identity",
    summary="[ichki] Bot o'z username'ini yozib qo'yadi",
    dependencies=[InternalOnly],
)
async def bot_identity(payload: BotIdentityRequest, session: DbSession) -> dict[str, str]:
    """Bot `get_me()` dan keyin shu yerga o'z username'ini yuboradi.

    Buning sababi: deep-link `t.me/<username>?start=srv_<token>` uchun
    username kerak, lekin uni qo'lda kiritish — ortiqcha xato manbai.
    Bot tokendan kim ekanini o'zi biladi, shuning uchun o'zi yozib qo'yadi.
    """
    username = payload.username.strip().lstrip("@")
    if not username:
        raise ValidationError("Bot username bo'sh bo'lishi mumkin emas")

    service = SettingsService(session)
    current = await service.get_value("telegram.bot_username")
    if str(current or "").lstrip("@") != username:
        # `updated_by` = None — bu odam emas, xizmat yozuvi
        await service.set_value("telegram.bot_username", username)
        await session.commit()

    return {"bot_username": username}


@router.get(
    "/health",
    summary="Integratsiyalar holati",
    dependencies=[Depends(require_permission("settings:read"))],
)
async def integrations_health(session: DbSession, user: CurrentUser):
    """Qaysi integratsiya sozlangan, qaysi biri yo'q — bir qarashda."""
    values = await SettingsService(session).get_all_values()

    def ok(*keys: str) -> bool:
        return all(values.get(k) not in ("", None) for k in keys)

    def ai_row(role: str, label: str) -> dict[str, Any]:
        """AI rolining holati — AYNAN quvur ishlatadigan yo'l bilan.

        ⚠️ Ilgari bu yerda eski `asr.provider` / `llm.anthropic_api_key`
        kalitlari o'qilardi. Ular hech qayerda ISHLATILMASDI, ya'ni
        sahifa haqiqatga aloqasi yo'q javob berardi: Gemini to'liq
        sozlangan bo'lsa ham «sozlanmagan» deb ko'rsatardi. Endi
        `resolve_from_values()` — quvur chaqiradigan o'sha funksiya —
        ishlatiladi, demak bu yerdagi «tayyor» so'zi haqiqiy tayyorlikni
        anglatadi.
        """
        try:
            resolution = resolve_from_values(values, role)
        except AppError as exc:
            return {
                "id": role,
                "label": label,
                "configured": False,
                "detail": str(exc),
            }
        return {
            "id": role,
            "label": label,
            "configured": True,
            "detail": f"{resolution.provider.label} · {resolution.model}",
        }

    return [
        ai_row(ROLE_ASR, "Nutqni matnga (ASR)"),
        ai_row(ROLE_LLM, "AI baholovchi (LLM)"),
        {
            "id": "telegram",
            "label": "Telegram bot",
            "configured": ok("telegram.bot_token", "telegram.bot_username"),
            "detail": f"@{values.get('telegram.bot_username') or '—'}",
        },
        {
            "id": "moizvonki",
            "label": "MoyZvonki",
            "configured": ok("moizvonki.domain", "moizvonki.user", "moizvonki.api_key"),
            "detail": values.get("moizvonki.domain") or "—",
        },
        {
            "id": "sms",
            "label": "SMS (Eskiz.uz)",
            "configured": ok("sms.eskiz_email", "sms.eskiz_password"),
            "detail": "Zaxira kanal",
        },
        {
            "id": "survey",
            "label": "Client so'rovnomasi",
            "configured": bool(values.get("survey.enabled")),
            "detail": f"Har {values.get('survey.period_days')} kunda",
        },
    ]
