"""So'rovnoma oqimi (eski, client uchun).

MUHIM DIZAYN QARORI (PLAN.md, D1):
  Chaqiruv guruhga yuboriladi (client u yerni har kuni ochadi),
  lekin BAHO SHAXSIY CHATDA qo'yiladi — savdo xodimi ko'rmaydi.
  Aks holda client rostini aytmaydi (social desirability bias).

Bu modulda yana `srv_` deep-link'ining YAGONA kirish nuqtasi turadi:
endi bitta prefiks IKKI oqimga xizmat qiladi (eski client oqimi va
yangi guruh oqimi), shuning uchun qaysi biri ekani `start_survey`
ichida hal qilinadi va guruh oqimi `handlers/groups.py` ga uzatiladi.
"""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.handlers import enroll, groups
from src.keyboards.survey import (
    csat_kb,
    resolution_kb,
    skip_comment_kb,
)
from src.services.api import ApiClient
from src.services.internal_api import InternalApiClient
from src.services.registry import GroupSurveyRegistry
from src.states.survey import SurveyFlow

logger = logging.getLogger(__name__)
router = Router(name="survey")

TOKEN_PREFIX = "srv_"


@router.message(CommandStart(deep_link=True), F.chat.type == ChatType.PRIVATE)
async def start_survey(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    api: ApiClient,
    internal: InternalApiClient,
    registry: GroupSurveyRegistry,
) -> None:
    """Deep-link orqali kirish: t.me/<bot>?start=srv_<token>"""
    payload = (command.args or "").strip()

    if not payload.startswith(TOKEN_PREFIX):
        # Notanish payload — deep-link'siz `/start` bilan bir xil
        await enroll.prompt(message)
        return

    token = payload[len(TOKEN_PREFIX) :]

    # ── Qaysi oqim? ────────────────────────────────────────────
    # 1) Eng ishonchli manba — botning o'z reyestri: guruh
    #    so'rovnomasini guruhga aynan bot yuborgan va tokenni
    #    Redis'da belgilab qo'ygan.
    if await registry.is_group_survey(token):
        await groups.open_detail(message, state, internal, token)
        return

    survey = await api.open_survey(token)

    if survey is None:
        await message.answer(
            "⏳ Bu so'rovnoma muddati tugagan yoki allaqachon to'ldirilgan.\n"
            "Rahmat!"
        )
        return

    # 2) Zaxira belgi: guruh so'rovnomasida client bo'lmaydi
    #    (shartnoma: `surveys.client_id` nullable, `group_id` to'ladi).
    #    Redis tozalangan bo'lsa ham oqim to'g'ri tanlanadi.
    if _looks_like_group(survey):
        await groups.open_detail(message, state, internal, token)
        return

    await state.set_state(SurveyFlow.csat)
    await state.update_data(token=token, agent_name=survey.get("agent_name", ""))

    await message.answer(
        f"Rahmat, vaqt ajratganingiz uchun! 🙏\n\n"
        f"<b>{survey.get('agent_name', 'Savdo xodimi')}</b> bilan ishlashdan "
        f"qanchalik roziligingizni belgilang:\n\n"
        f"🔒 <i>Javobingiz maxfiy — guruhda hech kim ko'rmaydi.</i>",
        reply_markup=csat_kb(),
    )


@router.callback_query(SurveyFlow.csat, F.data.startswith("csat:"))
async def handle_csat(call: CallbackQuery, state: FSMContext) -> None:
    score = int(call.data.split(":")[1])
    await state.update_data(csat=score)
    await state.set_state(SurveyFlow.resolution)

    await call.message.edit_text(
        f"Bahoyingiz: {'⭐' * score}\n\n" "Savollaringizga to'liq javob oldingizmi?",
        reply_markup=resolution_kb(),
    )
    await call.answer()


@router.callback_query(SurveyFlow.resolution, F.data.startswith("res:"))
async def handle_resolution(call: CallbackQuery, state: FSMContext) -> None:
    resolution = call.data.split(":")[1]
    await state.update_data(resolution=resolution)
    await state.set_state(SurveyFlow.comment)

    await call.message.edit_text(
        "Rahmat! Oxirgi savol:\n\n"
        "<b>Nimani yaxshilashimiz mumkin?</b>\n"
        "<i>Xohlasangiz yozing, yoki o'tkazib yuboring.</i>",
        reply_markup=skip_comment_kb(),
    )
    await call.answer()


@router.callback_query(SurveyFlow.comment, F.data == "comment:skip")
async def skip_comment(call: CallbackQuery, state: FSMContext, api: ApiClient) -> None:
    await _submit(state, api, comment=None)
    await call.message.edit_text(_thanks_text())
    await call.answer()


@router.message(SurveyFlow.comment, F.text)
async def handle_comment(message: Message, state: FSMContext, api: ApiClient) -> None:
    await _submit(state, api, comment=message.text)
    await message.answer(_thanks_text())


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start_plain(message: Message) -> None:
    """Oddiy `/start` — deep-link'siz.

    Shaxsiy chatga bot bilan O'ZI kelgan odam deyarli har doim savdo
    xodimi: mijoz botga faqat guruhdagi havola orqali tushadi va u
    havolada `srv_<token>` bo'ladi. Shuning uchun bu yerda salomlashish
    o'rniga ro'yxatdan o'tish taklif qilinadi (`handlers/enroll.py`).
    Matn mijozni ham chalkashtirmaydi — oxirgi qatorda unga «hech
    narsa qilish shart emas» deyilgan.
    """
    await enroll.prompt(message)


# ── Yordamchilar ──────────────────────────────────────────────


def _looks_like_group(survey: dict) -> bool:
    """`/open` javobi guruh so'rovnomasiga o'xshaydimi?

    Backend javobga guruh belgisini qo'shsa (`group_id`, `chat_id`
    yoki `is_group`) — shundan bilamiz. Qo'shmasa, `client_id` ning
    ochiq-oydin `null` bo'lishi ham yetarli belgi.
    """
    if survey.get("is_group") or survey.get("group_id") or survey.get("chat_id"):
        return True
    return "client_id" in survey and survey.get("client_id") is None


async def _submit(state: FSMContext, api: ApiClient, comment: str | None) -> None:
    data = await state.get_data()
    await api.submit_survey(
        token=data["token"],
        csat=data["csat"],
        resolution=data.get("resolution"),
        comment=comment,
    )
    await state.clear()


def _thanks_text() -> str:
    return (
        "✅ <b>Rahmat!</b>\n\n"
        "Javobingiz qabul qilindi va faqat rahbariyatga ko'rinadi.\n"
        "Fikringiz xizmatimizni yaxshilashga yordam beradi."
    )
