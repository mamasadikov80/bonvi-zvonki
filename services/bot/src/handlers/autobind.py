"""Guruhda yozgan odam — biriktirishning UCHINCHI yo'li.

Nega bu eng muhimi: 1000 ta guruhda savdo xodimi ko'pincha admin ham
emas, botni ham u qo'shmagan (guruhni mijoz ochgan yoki bot ancha
oldin qo'shilgan). Lekin xodim o'sha guruhda ISHLAYDI — ya'ni ertami
kechmi yozadi. Shu bitta xabar guruhni biriktirish uchun yetadi.

ROUTER ENG OXIRIDA TURADI
  Bu yerdagi handler guruhdagi HAR QANDAY xabarga mos keladi. Agar u
  oldinda tursa, `/bind`, guruh nomi o'zgarishi va boshqa aniq
  handler'larni bosib ketardi (aiogram birinchi mos kelgan handler'da
  to'xtaydi). Shuning uchun `runner.py` da eng oxirgi router sifatida
  ulanadi — hech nimani soya qilmaydi.

SO'ROV SONI
  Har xabarda backend chaqirilmaydi. Nomzod SHU GURUHDA hali
  aytilmagan bo'lsagina so'rov ketadi — qoida va sabablari
  `services/binding.py` da batafsil yozilgan.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from src.services.binding import AgentBinder
from src.services.chat_info import GROUP_CHATS

logger = logging.getLogger(__name__)
router = Router(name="autobind")


@router.message(F.chat.type.in_(GROUP_CHATS))
async def on_group_message(
    message: Message, bot: Bot, binder: AgentBinder
) -> None:
    """Guruhdagi oddiy xabar — yozgan odam nomzod sifatida qaraladi."""
    sender = message.from_user
    if sender is None or sender.is_bot:
        # Anonim admin (`GroupAnonymousBot`), kanal nomidan yozilgan
        # xabar va boshqa botlar — hech biri savdo xodimi emas.
        return

    await binder.discover(
        bot,
        message.chat.id,
        message.chat.title,
        sender_id=sender.id,
    )
