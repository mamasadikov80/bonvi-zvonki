"""Guruh haqidagi kichik ma'lumotlar — Telegram'dan o'qiladigan yordamchilar.

NEGA ALOHIDA MODUL
  Bu uchta funksiyaga endi UCH joy muhtoj: guruhni ro'yxatga oluvchi
  handler (`handlers/groups.py`), navbatdagi so'rovnoma yuboruvchi
  (`tasks/pending.py`) va avtomatik biriktiruvchi (`services/binding.py`).
  Ular handler faylida qolganda servis qatlami handler'ga bog'lanib,
  aylanma import (`binding → handlers.groups → binding`) paydo bo'lardi.

  Nomlar `handlers/groups.py` dan ham import qilinadi va o'sha yerdan
  ko'rinadi — eski `from src.handlers.groups import member_count_of`
  importlari ishlashda davom etadi.

Har bir funksiya XATONI YUTADI. A'zolar soni yoki adminlar ro'yxati
olinmasligi mumkin (bot huquqsiz, guruh o'chirilgan, tarmoq uzilgan) —
bu ma'lumot «bo'lsa yaxshi», «bo'lmasa halokat» emas.
"""

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType

logger = logging.getLogger(__name__)

GROUP_CHATS = {ChatType.GROUP, ChatType.SUPERGROUP}

# Shartnomadagi to'rtta holat (`bot_status`)
STATUS_MAP = {
    ChatMemberStatus.CREATOR: "administrator",
    ChatMemberStatus.ADMINISTRATOR: "administrator",
    ChatMemberStatus.MEMBER: "member",
    ChatMemberStatus.RESTRICTED: "member",
    ChatMemberStatus.LEFT: "left",
    ChatMemberStatus.KICKED: "kicked",
}
INSIDE = {"member", "administrator"}


async def member_count_of(bot: Bot, chat_id: int) -> int | None:
    """A'zolar soni. Olinmasa — muammo emas, `None` qaytadi.

    Bu son PANELDA KO'RSATISH uchun yuboriladi, guruhni tasniflash
    uchun emas: bir necha kishi bo'lgan guruh ham mijozsiz bo'lishi
    mumkin, buni botning bilishiga imkon yo'q.
    """
    try:
        return await bot.get_chat_member_count(chat_id)
    except Exception as exc:
        logger.debug("a'zolar soni olinmadi (guruh %s): %s", chat_id, exc)
        return None


async def current_status(bot: Bot, chat_id: int) -> str:
    """Botning guruhdagi hozirgi holati (`getChatMember` orqali)."""
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
        return STATUS_MAP.get(member.status, "member")
    except Exception as exc:
        logger.debug("bot holati aniqlanmadi (guruh %s): %s", chat_id, exc)
        # Xabar kelgan ekan, demak bot guruhda
        return "member"


async def administrator_ids(bot: Bot, chat_id: int) -> list[int]:
    """Guruh adminlarining Telegram id lari (botlarsiz).

    Botlar chiqarib tashlanadi: bot o'zi ham admin bo'lishi mumkin va
    u hech qachon savdo xodimi emas.
    """
    try:
        members = await bot.get_chat_administrators(chat_id)
    except Exception as exc:
        logger.debug("adminlar ro'yxati olinmadi (guruh %s): %s", chat_id, exc)
        return []

    return [
        member.user.id
        for member in members
        if member.user is not None and not member.user.is_bot
    ]
