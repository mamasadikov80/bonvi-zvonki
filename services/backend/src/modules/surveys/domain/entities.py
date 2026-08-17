"""So'rovnoma domeni — client baholash tizimi (PLAN.md 2-bo'lim)."""

import secrets
from enum import StrEnum

# Deep-link tokeni uzunligi — `surveys.token` ustuni String(64)
SURVEY_TOKEN_MAX_LEN = 64

# Minimal javoblar soni — shundan kam bo'lsa dashboardda reyting ko'rsatilmaydi.
#
# ⚠️ Bu ZAXIRA qiymat, yagona manba EMAS. Haqiqiy chegarani admin
# Sozlamalardan boshqaradi (`survey.min_responses`), uni o'qish esa
# `surveys.application.services.resolve_min_responses()` orqali bo'ladi.
# To'g'ridan-to'g'ri shu konstantaga tayanmang: sozlama "ishlaydigandek"
# ko'rinib, aslida hech narsaga ta'sir qilmay qolgan holat aynan shundan
# kelib chiqqan edi.
MIN_RESPONSES_FOR_RATING = 5

# Kadans: har 14 kunda bir marta
SURVEY_PERIOD_DAYS = 14

# Suppression: oxirgi N kunda so'ralgan bo'lsa qayta so'ralmaydi
SURVEY_SUPPRESSION_DAYS = 10

# Token amal qilish muddati
SURVEY_TOKEN_TTL_DAYS = 7

# Guruhdagi so'rovnoma xabari shuncha soatdan keyin o'chiriladi.
# Zaxira qiymat — haqiqiysi `survey.message_ttl_hours` sozlamasida.
SURVEY_MESSAGE_TTL_HOURS = 24

# ⚠️ Telegram cheklovi, sozlama emas: bot o'z xabarini yuborilganidan
# 48 soat o'tgach O'CHIRA OLMAYDI. Kattaroq muddat qo'yish "o'chadi"
# degan va'dani beradi-yu, amalda xabar guruhda qolib ketadi.
TELEGRAM_DELETE_LIMIT_HOURS = 48


class SurveyChannel(StrEnum):
    TELEGRAM_GROUP = "telegram_group"  # asosiy kanal
    SMS = "sms"  # zaxira (Eskiz)


class SurveyStatus(StrEnum):
    PENDING = "pending"  # yaratilgan, hali yuborilmagan
    SENT = "sent"  # guruhga yuborilgan
    OPENED = "opened"  # client tugmani bosgan
    COMPLETED = "completed"  # baho qo'yilgan
    EXPIRED = "expired"  # muddati o'tgan
    FAILED = "failed"  # yuborib bo'lmadi


class Resolution(StrEnum):
    """2-savol: muammoingiz hal bo'ldimi?"""

    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


RESOLUTION_LABEL_UZ: dict[Resolution, str] = {
    Resolution.YES: "Ha",
    Resolution.PARTIAL: "Qisman",
    Resolution.NO: "Yo'q",
}


# ── Red flag registri ─────────────────────────────────────────
#
# Bitta ro'yxat, ko'p tanlovli — ikkita kategoriyaga bo'linmaydi.
# Mijoz shaxsiy chatda kerakli bandlarni belgilaydi.
#
# Bu — YAGONA MANBA. Bot ham, frontend ham yorliqlarni qo'lda
# ko'chirmaydi: `GET /surveys/red-flags` shu ro'yxatni qaytaradi.
# Kalitlar bazaga yoziladi (`survey_responses.red_flags`), shuning
# uchun mavjud kalit HECH QACHON o'zgartirilmaydi — faqat yangisi
# qo'shiladi, aks holda eski javoblarning ma'nosi yo'qoladi.

RED_FLAGS: list[tuple[str, str]] = [
    ("rude", "Qo'pol muomala qildi"),
    ("no_answer", "Telefonni ko'tarmadi"),
    ("late_reply", "Juda kech javob berdi"),
    ("broken_promise", "Va'da berib bajarmadi"),
    ("wrong_price", "Narxni noto'g'ri aytdi"),
    ("late_delivery", "Yetkazib berish kechikdi"),
    ("wrong_order", "Buyurtma xato keldi"),
    ("bad_quality", "Tovar sifati yomon"),
    ("no_document", "Hujjat berilmadi yoki kechikdi"),
    ("pushy", "Keraksiz mahsulotni majburladi"),
]
RED_FLAG_LABELS: dict[str, str] = dict(RED_FLAGS)


def normalize_red_flags(keys: list[str] | None) -> list[str]:
    """Kalitlarni tekshiradi va takrorlarini olib tashlaydi.

    Noma'lum kalit kelsa `ValueError` — chaqiruvchi uni 422 ga aylantiradi.
    Tartib saqlanadi: mijoz belgilagan ketma-ketlik ma'lumot beradi.
    """
    if not keys:
        return []

    unknown = [k for k in keys if k not in RED_FLAG_LABELS]
    if unknown:
        raise ValueError(", ".join(sorted(set(unknown))))

    seen: dict[str, None] = {}
    for key in keys:
        seen.setdefault(key, None)
    return list(seen)


def new_survey_token() -> str:
    """Yangi deep-link tokeni: `t.me/<bot>?start=srv_<token>`.

    Toza domen mantig'i — I/O yo'q, shuning uchun shu yerda turadi.
    `secrets` ishlatiladi (`random` emas): token — bu haqiqiy kirish kaliti,
    uni topib olgan odam boshqa clientning so'rovnomasini to'ldira oladi.
    """
    return secrets.token_urlsafe(24)[:SURVEY_TOKEN_MAX_LEN]
