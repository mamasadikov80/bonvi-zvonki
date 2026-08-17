"""Savdo xodimining bir martalik ro'yxatdan o'tishi (shaxsiy chat).

NEGA BU KERAK — VA NEGA BOSHQA YO'L YO'Q
  Bot guruh a'zosining telefon raqamini KO'RA OLMAYDI. Bot API dagi
  `User` obyektida `phone_number` maydoni umuman yo'q, foydalanuvchi
  raqamini profilida «hamma ko'rsin» qilib qo'yishi ham bunga ta'sir
  qilmaydi — o'sha sozlama odamlarga tegishli, botlarga emas. Bu
  Telegram'ning ataylab qo'ygan chegarasi va uni aylanib o'tish yo'li
  yo'q.

  Yagona yo'l: foydalanuvchi raqamini O'ZI yuboradi
  (`KeyboardButton(request_contact=True)`). Shundan keyin bot
  `contact.phone_number` va `contact.user_id` ni oladi.

  Shuning uchun butun oqim shunday quriladi: BIR MARTALIK ro'yxatdan
  o'tish → keyin ~1000 ta guruh o'zi biriktiriladi
  (`services/binding.py`).

XAVFSIZLIK — shu fayldagi eng muhim qator
  Telegram'da BOSHQA odamning kontakt kartasini ham yuborish mumkin
  (chatdan «Kontakt yuborish» orqali). Agar bot uni qabul qilsa,
  o'sha odamning guruhlari yuborgan kishiga biriktirilardi: begona
  xodim boshqa xodimning mijozlarini va baholarini ko'rib qolardi.
  Shuning uchun `contact.user_id != message.from_user.id` bo'lgan
  har qanday kontakt RAD ETILADI. `user_id` umuman bo'lmagan
  (qo'lda yozilgan) kontakt ham rad etiladi.

MAXFIYLIK
  Telefon raqami LOGGA HECH QACHON TUSHMAYDI va Redis'ga
  saqlanmaydi. U faqat bitta HTTP so'rovda backend'ga uzatiladi
  (`internal.enroll`) va shu yerda tugaydi. Telegram id ham
  loglanmaydi — natija xodim ISMI bilan yoziladi.
"""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from src.services.internal_api import InternalApiClient
from src.views.enroll import (
    contact_kb,
    foreign_contact_text,
    hide_kb,
    matched_text,
    not_found_text,
    prompt_text,
    unavailable_text,
)

logger = logging.getLogger(__name__)
router = Router(name="enroll")


async def prompt(message: Message) -> None:
    """Shaxsiy chatdagi `/start` (deep-link'siz) shu yerga olib keladi.

    Chaqiruvchi — `handlers/survey.py` dagi `start_plain`: `srv_`
    deep-link'ining yagona kirish nuqtasi o'sha yerda va uni ikkiga
    bo'lish oqimni chalkashtirardi.
    """
    await message.answer(prompt_text(), reply_markup=contact_kb())


@router.message(F.chat.type == ChatType.PRIVATE, F.contact)
async def on_contact(message: Message, internal: InternalApiClient) -> None:
    """Kelgan kontakt kartasi — ro'yxatdan o'tishning yagona qadami."""
    contact = message.contact
    sender = message.from_user
    if contact is None or sender is None:
        return

    # ── Xavfsizlik tekshiruvi (fayl boshidagi izohga qarang) ──────
    if contact.user_id is None or contact.user_id != sender.id:
        # Tugma ATAYLAB olib tashlanmaydi: odam to'g'ri tugmani
        # bosib qayta urinib ko'rishi kerak.
        await message.answer(foreign_contact_text(), reply_markup=contact_kb())
        logger.warning("⛔ Begona kontakt rad etildi (shaxsiy chat)")
        return

    result = await internal.enroll(
        phone=contact.phone_number,
        telegram_user_id=sender.id,
        telegram_username=sender.username,
    )

    if result is None:
        # Backend javob bermadi — hech narsa o'zgarmadi, qayta urinsa bo'ladi
        await message.answer(unavailable_text(), reply_markup=contact_kb())
        logger.warning("⚠️  Ro'yxatdan o'tkazib bo'lmadi — backend javob bermadi")
        return

    if not result.matched:
        await message.answer(not_found_text(), reply_markup=hide_kb())
        logger.info("🔎 Raqam xodimlar ro'yxatidan topilmadi")
        return

    name = result.full_name or "Xodim"
    await message.answer(
        matched_text(name, result.bound_groups), reply_markup=hide_kb()
    )
    logger.info(
        "🪪 Xodim ro'yxatdan o'tdi: %s · biriktirilgan guruhlar=%s",
        name,
        result.bound_groups,
    )
