"""Savdo xodimi ro'yxatdan o'tishining matni va tugmasi.

Matn AUTOBIND_CONTRACT.md ning 2-bo'limidan olingan. Birinchi ikki
qator o'zgarmaydi — qolgani foydalanuvchining savoliga oldindan javob
beradi: «raqamim nima uchun kerak?» va «men mijozman, nima qilay?».
"""

from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

CONTACT_BUTTON = "📱 Raqamimni yuborish"


def contact_kb() -> ReplyKeyboardMarkup:
    """`request_contact=True` — raqamni Telegram'ning o'zi biriktiradi.

    Bu tugmani bosgan odam raqamni qo'lda yozmaydi: Telegram uning
    PROFILDAGI raqamini yuboradi va yoniga egasining id sini qo'shadi.
    Aynan shu juftlik tekshiruvni mumkin qiladi (qarang:
    `handlers/enroll.py`).
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CONTACT_BUTTON, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tugmani bosing",
    )


def hide_kb() -> ReplyKeyboardRemove:
    """Tugma osilib qolmasin — bir marta ishlatiladi va yo'qoladi."""
    return ReplyKeyboardRemove()


def prompt_text() -> str:
    return (
        "Assalomu alaykum! Siz Bonvi savdo xodimisiz.\n"
        "Guruhlaringiz avtomatik aniqlanishi uchun raqamingizni yuboring.\n\n"
        "Quyidagi tugmani bosing — raqam faqat sizni xodimlar ro'yxatidan "
        "topish uchun ishlatiladi.\n\n"
        "<i>Agar siz mijoz bo'lsangiz, bu yerda hech narsa qilish shart "
        "emas: so'rovnoma o'zi guruhingizga tushadi.</i>"
    )


def matched_text(full_name: str, bound_groups: int) -> str:
    """Xodim topildi. Nechta guruh biriktirilgani darhol aytiladi."""
    head = (
        f"✅ Rahmat, <b>{full_name}</b>!\n"
        f"Raqamingiz tasdiqlandi — endi guruhlaringiz o'zi aniqlanadi."
    )
    if bound_groups > 0:
        body = (
            f"\n\n🔗 Sizga <b>{bound_groups} ta guruh</b> biriktirildi.\n"
            "Ular admin panelida ko'rinadi."
        )
    else:
        body = (
            "\n\nHozircha guruh topilmadi — bu normal holat.\n"
            "Guruhlaringizda biror xabar yozsangiz yoki botni yangi "
            "guruhga qo'shsangiz, ular o'zi sizga biriktiriladi."
        )
    return head + body + "\n\nBoshqa hech narsa qilish shart emas."


def not_found_text() -> str:
    """Shartnomadagi xushmuomala javob (`matched: false`)."""
    return (
        "🤔 <b>Raqamingiz tizimda topilmadi, administratorga murojaat "
        "qiling.</b>\n\n"
        "Xodimlar ro'yxatida raqamingiz boshqacha yozilgan bo'lishi "
        "mumkin — administrator uni tekshirib to'g'rilaydi, keyin "
        "tugmani qayta bosasiz."
    )


def foreign_contact_text() -> str:
    """Boshqa odamning kontakt kartasi yuborilgan."""
    return (
        "⚠️ <b>Bu raqam sizniki emas.</b>\n\n"
        "Boshqa odamning kontakt kartasi qabul qilinmaydi: aks holda "
        "o'sha odamning guruhlari sizga biriktirilib qolardi.\n\n"
        f"«{CONTACT_BUTTON}» tugmasini bosing — Telegram raqamingizni "
        "o'zi yuboradi."
    )


def unavailable_text() -> str:
    """Backend javob bermadi — holat saqlanadi, qayta urinsa bo'ladi."""
    return (
        "⚠️ Hozir tekshirib bo'lmadi — server javob bermadi.\n"
        f"Birozdan keyin «{CONTACT_BUTTON}» tugmasini qayta bosing."
    )
