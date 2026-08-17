"""So'rovnoma klaviaturalari."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def group_invite_kb(bot_username: str, token: str) -> InlineKeyboardMarkup:
    """Guruhga yuboriladigan tugma.

    Bosilganda shaxsiy chat ochiladi — guruhda hech narsa ko'rinmaydi.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Baholashni boshlash",
                    url=f"https://t.me/{bot_username}?start=srv_{token}",
                )
            ]
        ]
    )


def csat_kb() -> InlineKeyboardMarkup:
    """1-savol: 1–5 yulduz."""
    builder = InlineKeyboardBuilder()
    for score in range(1, 6):
        builder.button(text="⭐" * score, callback_data=f"csat:{score}")
    builder.adjust(1)
    return builder.as_markup()


def resolution_kb() -> InlineKeyboardMarkup:
    """2-savol: muammo hal bo'ldimi."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha", callback_data="res:yes")
    builder.button(text="🟡 Qisman", callback_data="res:partial")
    builder.button(text="❌ Yo'q", callback_data="res:no")
    builder.adjust(3)
    return builder.as_markup()


def skip_comment_kb() -> InlineKeyboardMarkup:
    """3-savol: izohni o'tkazib yuborish."""
    builder = InlineKeyboardBuilder()
    builder.button(text="O'tkazib yuborish", callback_data="comment:skip")
    return builder.as_markup()
