"""Telegram Mini App so'rovnoma sahifasi uchun ikkita OCHIQ endpoint.

Nega alohida fayl? Marshrut TARTIBI uchun. `router.py` da
`POST /surveys/{token}/open` bor, u `/surveys/webapp/open` ni ham
`token="webapp"` deb ushlab oladi — Starlette marshrutlarni ro'yxatdan
o'tish TARTIBIDA solishtiradi, "aniqroq mos keladigani" degan tushuncha
yo'q. Shuning uchun bu router `router.py` ning eng boshida, `{token}`
marshrutlaridan OLDIN ulanadi.

JWT YO'Q va qo'shilmasin. Autentifikatsiya vazifasini `initData`
imzosi bajaradi (`application/webapp.py`): baho beruvchi — do'kondor,
u Telegram ichida o'tiribdi va dashboardga hech qachon kirmaydi.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from src.core.deps import DbSession
from src.core.exceptions import NotFoundError
from src.modules.settings.application.services import SettingsService
from src.modules.surveys.application.services import SurveyService
from src.modules.surveys.application.webapp import (
    respondent_hash,
    verify_init_data,
)
from src.modules.surveys.domain.entities import RED_FLAGS

router = APIRouter()

# `router.py` dagi izoh maydoni bilan bir xil chegara.
CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
]


class RedFlagItem(BaseModel):
    key: str
    label: str


class WebAppOpenRequest(BaseModel):
    init_data: str = Field(description="`Telegram.WebApp.initData` xom matni")


class WebAppOpenResponse(BaseModel):
    """Sahifa ko'rsatadigan hamma narsa. Baho beruvchi kimligi bu yerda YO'Q."""

    token: str
    agent_name: str
    period_start: datetime
    period_end: datetime
    already_rated: bool
    red_flags: list[RedFlagItem]


class WebAppSubmitRequest(BaseModel):
    init_data: str
    csat: Annotated[int, Field(ge=1, le=5, description="1..5 yulduz")]
    comment: CommentText | None = None
    red_flags: list[str] = []


class WebAppSubmitResponse(BaseModel):
    ok: bool
    agent_name: str
    response_count: int


async def _resolve(session: DbSession, init_data: str) -> tuple[str, str]:
    """Imzoni tekshiradi va `(token, respondent_hash)` qaytaradi.

    ┌─ NEGA TOKEN `initData` ICHIDAN OLINADI, YO'LDAN (path) EMAS ─────┐
    │                                                                  │
    │ Token `start_param` sifatida `initData` ning ichida keladi va    │
    │ Telegramning imzosi bilan QOPLANGAN. Ya'ni uni o'zgartirib       │
    │ bo'lmaydi: bitta belgi almashtirilsa `hash` mos kelmay qoladi.   │
    │                                                                  │
    │ Agar token alohida maydonda yoki yo'l parametrida yuborilsa      │
    │ (`/surveys/webapp/{token}/submit`), u imzodan TASHQARIDA qoladi. │
    │ O'shanda istalgan odam O'ZINING haqiqiy `initData` si bilan      │
    │ BOSHQA guruhning tokenini juftlab yuborishi mumkin bo'lardi —    │
    │ va o'zi hech qachon xizmat ko'rsatmagan xodimga baho qo'yardi.   │
    │ Bitta `initData` bilan hamma so'rovnomani "to'ldirib" chiqish    │
    │ mumkin bo'lardi.                                                 │
    │                                                                  │
    │ Shuning uchun BU YERNI "soddalashtirmang": tokenni yo'l          │
    │ parametriga chiqarish — bu qulaylik emas, himoyani yo'qotish.    │
    └──────────────────────────────────────────────────────────────────┘
    """
    # Token baza > .env tartibida. Bo'sh bo'lsa `verify_init_data` 503
    # chiqaradi — bo'sh kalit bilan tekshiruv qilinmaydi.
    bot_token = await SettingsService(session).get_value("telegram.bot_token")
    payload = verify_init_data(init_data, bot_token or "")

    token = payload.start_param
    if not token:
        raise NotFoundError("So'rovnoma topilmadi yoki havola noto'g'ri")

    # `user_id` shu qatordan nariga o'tmaydi: pastga faqat qaytarib
    # bo'lmaydigan hash uzatiladi.
    return token, respondent_hash(token, payload.user_id)


@router.post(
    "/webapp/open",
    response_model=WebAppOpenResponse,
    summary="Mini App sahifasini ochish (ochiq, `initData` imzosi bilan)",
    responses={
        401: {"description": "Imzo noto'g'ri yoki eskirgan"},
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "So'rovnoma muddati o'tgan"},
        503: {"description": "Bot sozlanmagan"},
    },
)
async def webapp_open(payload: WebAppOpenRequest, session: DbSession):
    token, digest = await _resolve(session, payload.init_data)
    result = await SurveyService(session).webapp_open(token, respondent_hash=digest)
    # Red flag yorliqlari serverdan beriladi — sahifa ularni qo'lda
    # yozmasin, aks holda ro'yxat ertami-kechmi asl nusxadan ajralib qoladi.
    result["red_flags"] = [
        RedFlagItem(key=key, label=label) for key, label in RED_FLAGS
    ]
    return result


@router.post(
    "/webapp/submit",
    response_model=WebAppSubmitResponse,
    summary="Mini App'dan bahoni yuborish (ochiq, `initData` imzosi bilan)",
    responses={
        401: {"description": "Imzo noto'g'ri yoki eskirgan"},
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "Siz allaqachon baho bergansiz"},
        422: {"description": "Noma'lum red flag kaliti"},
        503: {"description": "Bot sozlanmagan"},
    },
)
async def webapp_submit(payload: WebAppSubmitRequest, session: DbSession):
    token, digest = await _resolve(session, payload.init_data)
    return await SurveyService(session).webapp_submit(
        token,
        respondent_hash=digest,
        csat=payload.csat,
        comment=payload.comment,
        red_flags=payload.red_flags,
    )
