"""Guruh so'rovnomasining ko'rinishi — matn va tugmalar.

Nega matn ham shu yerda, `keyboards/` da emas?
Guruh xabari — bitta butun: matnni tugmalarsiz tahrirlab bo'lmaydi
(`editMessageText` `reply_markup` berilmasa tugmalarni O'CHIRIB yuboradi).
Uni uch joyda — poller, throttle va callback handler'da — qayta chizish
kerak, shuning uchun matn va klaviatura bitta modulda turadi. Shakl
GROUPS_CONTRACT.md ning 4-bo'limidan olingan, o'zgartirilmaydi.

IKKI REJIM
  Guruh xabari ikki xil ko'rinishda chiziladi (MINIAPP_CONTRACT.md,
  5-bo'lim). Bu modul QAROR QABUL QILMAYDI — unga tayyor `miniapp_name`
  keladi:

    nom BO'SH   → TUGMALAR rejimi: guruhda 1️⃣–5️⃣ va tamom. Izoh ham,
                  shaxsiy chatga o'tish ham yo'q.
    nom TO'LA   → Mini App: matn va BITTA URL tugma. Ball, izoh va
                  sabab — hammasi Telegram ichida ochiladigan sahifada.

  Qaysi biri ekanini `services/config_client.py` hisoblaydi va u ikki
  manbaga qaraydi: admin paneldagi ANIQ tanlov (`survey.mode`) va
  Mini App qisqa nomi (`telegram.miniapp_name`). Nom to'ldirilmagan
  bo'lsa Mini App tanlangan bo'lsa ham tugmalar rejimi ishlaydi —
  BotFather'da ro'yxatdan o'tkazilmagan ilovaga havola qurish
  guruhga buzuq tugma yuborardi.

  Shuning uchun bu yerdagi `miniapp_name` parametrlari standart
  bo'yicha bo'sh: chaqiruvchi hech narsa bermasa tugmalar chiziladi.
"""

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Deep-link prefiksi — guruh xabaridagi URL tugma va shaxsiy chatdagi
# `/start` bir xil formatdan foydalanadi.
TOKEN_PREFIX = "srv_"

# Ball tugmalari uchun raqam emojilari
DIGITS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")

# Mini App rejimidagi yagona tugma
MINIAPP_BUTTON = "⭐ Baholash"

# BotFather qoidasi: qisqa nom 3–30 belgi, faqat a–z, 0–9 va pastki chiziq.
# Tekshiruv MAJBURIY: admin panelga «@survey» yoki to'liq havola yozib
# qo'ysa, undan buzuq URL quriladi va HAQIQIY guruhda ishlamaydigan
# tugma paydo bo'ladi. Noto'g'ri qiymat — bo'sh qiymat kabi: eski oqim.
MINIAPP_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def is_valid_miniapp_name(name: str) -> bool:
    """Qisqa nom havola qurishga yaroqlimi?"""
    return bool(MINIAPP_NAME_RE.match(name or ""))


def miniapp_link(bot_username: str, miniapp_name: str, token: str) -> str:
    """`https://t.me/<bot>/<app>?startapp=<token>`.

    `startapp` — Telegram'ning standart parametri: sahifa ochilganda
    qiymat `initData.start_param` ichida keladi va u bot tokeni bilan
    IMZOLANGAN bo'ladi. Ya'ni token sahifaga qo'shimcha so'rovsiz,
    soxtalashtirib bo'lmaydigan holda yetib boradi.
    """
    return f"https://t.me/{bot_username}/{miniapp_name}?startapp={token}"


def _counter_line(response_count: int) -> str:
    """Faqat UMUMIY son — kim bosgani hech qayerda yo'q."""
    if response_count > 0:
        return f"✅ {response_count} kishi baho berdi"
    return "✳️ Hali hech kim baho bermadi"


def survey_text(response_count: int, miniapp_name: str = "") -> str:
    """Guruhga yuboriladigan (va keyin tahrirlanadigan) matn.

    Hisoblagich ikkala rejimda ham bir xil — shakli va siqib
    yangilanishi (`services/throttle.py`) o'zgarmadi.
    """
    if miniapp_name:
        # MINIAPP_CONTRACT.md, 5-bo'limdagi matn.
        return (
            "📊 <b>Xizmat sifatini baholang</b>\n\n"
            "Hurmatli mijozlar! So'nggi kunlardagi ishimizni baholang.\n"
            "Baholash anonim — kim baho qo'yganini hech kim ko'rmaydi.\n"
            "Bir daqiqadan kam vaqt oladi.\n\n"
            f"{_counter_line(response_count)}"
        )

    return (
        "📊 <b>Xizmat sifatini baholang</b>\n\n"
        "Hurmatli mijozlar! So'nggi 2 hafta ichidagi ishimizni baholang.\n"
        "Baholash anonim — kim baho qo'yganini hech kim ko'rmaydi.\n\n"
        f"{_counter_line(response_count)}"
    )


def survey_kb(
    bot_username: str, token: str, miniapp_name: str = ""
) -> InlineKeyboardMarkup:
    """Guruh xabarining klaviaturasi.

    Mini App rejimida — BITTA URL tugma, hech qanday `callback_data`
    yo'q. Sabab foydalanuvchidan: eski oqimda izoh yozish uchun botni
    alohida `/start` qilish kerak edi, bu ortiqcha qadam edi. Endi
    havola Telegram ICHIDA sahifani ochadi va ball ham, izoh ham
    o'sha yerda qoladi.

    URL tugma anonimlik uchun ham yaxshiroq: callback'dan farqli
    o'laroq, uni bosgani haqida Telegram hech kimga hech narsa
    yubormaydi.

    Eski rejimda — FAQAT beshta ball tugmasi. Izoh uchun botga
    o'tkazadigan tugma ATAYLAB olib tashlangan: shaxsiy chatga o'tish
    uchun mijoz botni alohida `/start` qilishi kerak edi va bu ortiqcha
    qadam edi. Izoh va sabab endi faqat Mini App'da so'raladi; Mini App
    sozlanmagan bo'lsa, guruhda faqat ball yig'iladi.
    """
    if miniapp_name:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=MINIAPP_BUTTON,
                        url=miniapp_link(bot_username, miniapp_name, token),
                    )
                ]
            ]
        )

    rating = [
        InlineKeyboardButton(text=DIGITS[n - 1], callback_data=f"rate:{token}:{n}")
        for n in range(1, 6)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[rating])


# ── Shaxsiy chatdagi tafsilot bosqichi ────────────────────────

FLAG_PREFIX = "gd:flag:"
DONE = "gd:done"
COMMENT = "gd:comment"
CANCEL = "gd:cancel"
BACK = "gd:back"


def red_flags_kb(
    flags: list[tuple[str, str]], selected: list[str], has_comment: bool
) -> InlineKeyboardMarkup:
    """Ko'p tanlovli sabablar ro'yxati (bitta ro'yxat, 2 ta kategoriya emas).

    Yorliqlar `GET /surveys/red-flags` dan keladi — bu yerda ro'yxat
    YO'Q. Tanlangan band ✅ bilan chiziladi va bosilganda klaviatura
    qayta chiziladi (Telegram'da "checkbox" shunday quriladi).
    """
    builder = InlineKeyboardBuilder()
    chosen = set(selected)

    for key, label in flags:
        mark = "✅" if key in chosen else "▫️"
        builder.button(text=f"{mark} {label}", callback_data=f"{FLAG_PREFIX}{key}")

    comment_label = "✏️ Izohni o'zgartirish" if has_comment else "💬 Izoh yozish"
    builder.button(text=comment_label, callback_data=COMMENT)
    builder.button(text="✅ Tayyor", callback_data=DONE)
    builder.button(text="❌ Bekor qilish", callback_data=CANCEL)

    # Har sabab alohida qatorda — yorliqlar uzun, ikkitasi sig'maydi.
    builder.adjust(*([1] * len(flags)), 1, 2)
    return builder.as_markup()


def comment_kb() -> InlineKeyboardMarkup:
    """Izoh yozish bosqichi — orqaga qaytish."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Orqaga", callback_data=BACK)
    return builder.as_markup()


def detail_intro(selected_count: int, comment: str | None) -> str:
    """Tafsilot oynasining matni."""
    lines = [
        "🙏 <b>Rahmat!</b> Bahoyingiz qabul qilindi.",
        "",
        "Xohlasangiz sababini belgilang yoki izoh yozing.",
        "Bu <b>ixtiyoriy</b> — javobingiz baribir anonim qoladi.",
    ]
    if selected_count:
        lines += ["", f"Tanlangan sabablar: <b>{selected_count}</b>"]
    if comment:
        preview = comment if len(comment) <= 120 else comment[:117] + "…"
        lines += [f"💬 Izoh: <i>{preview}</i>"]
    return "\n".join(lines)


def flags_unavailable_text() -> str:
    """Sabablar ro'yxati kelmaganda — izoh baribir yozilsin."""
    return (
        "🙏 <b>Rahmat!</b> Bahoyingiz qabul qilindi.\n\n"
        "Sabablar ro'yxatini hozir yuklab bo'lmadi, lekin izoh "
        "yozishingiz mumkin — quyidagi tugmani bosing."
    )
