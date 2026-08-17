"""Telegram Mini App — `initData` imzosini tekshirish.

BU MODUL — SAHIFANING YAGONA HIMOYASI.
So'rovnoma sahifasi ochiq: JWT yo'q, parol yo'q, sessiya yo'q. Kim baho
qo'yayotganini faqat shu yerdagi imzo tekshiruvi aniqlaydi. Agar u
noto'g'ri bo'lsa, endpoint ochiq eshikka aylanadi: istalgan odam istalgan
`user_id` yozib, cheksiz baho qo'yib, bir xodimning reytingini yerga urib
yoki ko'kka ko'tarib yuborishi mumkin.

Shuning uchun modul ATAYLAB toza saqlanadi: ichida na FastAPI, na
SQLAlchemy, na baza chaqiruvi bor. `verify_init_data(init_data, bot_token)`
— oddiy funksiya, uni HTTP va bazasiz, to'g'ridan-to'g'ri sinash mumkin.
Tekshiruvni "qulaylik uchun" endpoint ichiga ko'chirmang.

Telegram rasmiy algoritmi
─────────────────────────
    secret_key        = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
    data_check_string = "\\n".join(sorted("k=v")), `hash` maydonisiz
    expected          = HMAC_SHA256(key=secret_key, msg=data_check_string)
    expected == initData ichidagi `hash`  ➜  ma'lumot Telegramdan kelgan

`signature` maydoni haqida (muhim!)
───────────────────────────────────
Yangi Telegram mijozlari `hash` dan tashqari `signature` maydonini ham
qo'shadi — bu Telegramning Ed25519 imzosi, uchinchi tomon bot tokenisiz
tekshira olishi uchun. Rasmiy hujjatda `hash` va `signature` ikkalasi ham
chiqarib tashlanadi deyilgan — LEKIN bu FAQAT uchinchi tomon (Ed25519)
tekshiruviga tegishli.

Bot tokeni bilan qilinadigan HMAC tekshiruvida `data_check_string` dan
FAQAT `hash` chiqariladi, `signature` esa ICHIDA QOLADI.

Bu taxmin emas — haqiqiy, Telegram imzolagan `initData` bilan tekshirilgan
(`signature` maydoni bor, 2024-12):

    faqat `hash` chiqarildi        ➜ hash mos keldi
    `hash` + `signature` chiqarildi ➜ hash mos kelmadi

Xuddi shu yo'l rasmiy kutubxonalarda ham: `@telegram-apps/init-data-node`
(`validateFp` faqat `hash` ni ajratadi, `validate3rdFp` esa ikkalasini),
`init-data-golang` va aiogram `check_webapp_signature`. Ya'ni `signature`
ni ham chiqarib tashlasangiz, yangi mijozlardan kelgan HAR QANDAY haqiqiy
`initData` rad etiladi — sahifa hech kimda ishlamaydi.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from src.core.exceptions import AppError, UnauthorizedError

# `initData` odatda 1 KB atrofida. Chegara — HMAC ni cheksiz uzun matnga
# hisoblab o'tirmaslik uchun: imzo tekshirilgunga qadar biz hali hech kimga
# ishonmaymiz, demak ish hajmini ham cheklashimiz kerak.
INIT_DATA_MAX_LEN = 4096

# Eskirgan `initData` qabul qilinmaydi. Imzo to'g'ri bo'lsa ham: bir marta
# o'g'irlangan havola abadiy amal qilmasligi kerak.
INIT_DATA_TTL = timedelta(hours=24)

# Server soati bir necha soniyaga oldinda bo'lishi mumkin — kelajakdagi
# `auth_date` ni shuncha kechiramiz, undan nariga o'tsa rad etamiz.
CLOCK_SKEW = timedelta(minutes=5)

# `survey_responses.respondent_hash` ustuni String(64).
HASH_LENGTH = 64


class BotNotConfiguredError(AppError):
    """Bot tokeni sozlanmagan — imzoni tekshirib bo'lmaydi (503).

    ATAYLAB 401 EMAS va ataylab "o'tkazib yuborish" ham emas. Token bo'sh
    bo'lsa `secret_key` bo'sh kalitdan hisoblanardi va soxta `initData` ni
    ham xuddi shu bo'sh kalit bilan yasash mumkin bo'lardi — ya'ni HAR
    QANDAY qalbaki imzo haqiqiy deb topilardi. Sozlanmagan bot — vaqtinchalik
    ishlamayotgan xizmat, shuning uchun 503.
    """

    status_code = 503
    code = "bot_not_configured"


@dataclass(frozen=True, slots=True, repr=False)
class WebAppInitData:
    """`initData` dan olingan, imzo bilan TASDIQLANGAN maydonlar.

    Ataylab kam maydon: ism, familiya, username — hech biri kerak emas,
    demak ularni olib yurmaymiz ham.
    """

    user_id: int
    """Telegram identifikatori. BAZAGA YOZILMAYDI va LOGGA CHIQMAYDI —
    faqat `respondent_hash()` ga kiritish uchun yashaydi."""

    start_param: str | None
    """`?startapp=<token>` dan kelgan so'rovnoma tokeni."""

    auth_date: datetime

    def __repr__(self) -> str:
        """`user_id` tasodifan logga tushib qolmasligi uchun.

        `logger.info("...%s", payload)` yoki xatolik traceback'i obyektni
        o'zi chop etadi — standart dataclass `__repr__` esa Telegram
        identifikatorini ochiq matnda logga yozib qo'yardi.
        """
        return (
            f"WebAppInitData(user_id=<yashirin>, "
            f"start_param={self.start_param!r}, auth_date={self.auth_date!r})"
        )


def respondent_hash(token: str, telegram_user_id: int) -> str:
    """Javob beruvchining qaytarib bo'lmaydigan belgisi.

    Formula BOTNIKI bilan bayt-ba-bayt bir xil bo'lishi SHART
    (`services/bot/src/core/anonymity.py`): bitta odam eski guruh oqimida
    ham, Mini App sahifasida ham baho berishi mumkin. Hash farq qilsa
    `uq_response_per_respondent` ishlamay qoladi va o'sha odam bitta
    so'rovnomaga ikki marta baho qo'yib yuboradi.
    """
    raw = f"{token}:{telegram_user_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:HASH_LENGTH]


def _bad(message: str) -> UnauthorizedError:
    """401. Xabar ataylab umumiy — qaysi qadamda yiqilgani aytilmaydi.

    "hash yo'q" / "user yo'q" / "imzo mos emas" deb ajratib aytish soxta
    `initData` yig'ayotgan odamga bepul yo'l-yo'riq bo'lardi.
    """
    return UnauthorizedError(message, code="init_data_invalid")


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: timedelta = INIT_DATA_TTL,
    now: datetime | None = None,
) -> WebAppInitData:
    """`initData` ni tekshiradi va ichidagi tasdiqlangan ma'lumotni qaytaradi.

    Xatoliklar:
      • `BotNotConfiguredError` (503) — bot tokeni sozlanmagan
      • `UnauthorizedError` (401) — imzo noto'g'ri, buzilgan yoki eskirgan
    """
    if not bot_token or not bot_token.strip():
        raise BotNotConfiguredError(
            "Bot hozircha sozlanmagan, keyinroq urinib ko'ring"
        )

    if not init_data or len(init_data) > INIT_DATA_MAX_LEN:
        raise _bad("Telegram ma'lumotlari yaroqsiz")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise _bad("Telegram ma'lumotlari yaroqsiz") from None

    # Takrorlangan kalit — Telegram hech qachon yubormaydi, lekin hujumchi
    # yuborishi mumkin. `dict()` oxirgisini oladi, `data_check_string` esa
    # ikkalasini ham qamrab oladi: shu tafovutda "imzolangan bitta qiymat,
    # o'qiladigan boshqa qiymat" degan klassik hiyla yashiringan.
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise _bad("Telegram ma'lumotlari yaroqsiz")

    fields = dict(pairs)
    supplied_hash = fields.pop("hash", None)
    if not supplied_hash:
        raise _bad("Telegram ma'lumotlari yaroqsiz")

    # ── data_check_string ─────────────────────────────────────
    # Kalitlar bo'yicha alifbo tartibida, `\n` bilan ulanadi. `hash` dan
    # boshqa HAMMA maydon kiradi — `signature` ham (yuqoridagi izohga qarang).
    #
    # Eslatma: rasmiy kutubxonalar tayyor "k=v" satrlarini saralaydi, biz
    # kalit bo'yicha saraylaymiz. Telegram maydon nomlarida natija bir xil:
    # farq faqat bitta kalit ikkinchisining boshlanishi bo'lganda va davomi
    # '=' (0x3D) dan kichik belgi bilan boshlanganda chiqadi (masalan `a`
    # va `a1`) — Telegramda bunday juftlik yo'q.
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    # `==` EMAS. Oddiy solishtirish birinchi farqli baytda to'xtaydi va
    # javob vaqti orqali "nechta bayt to'g'ri edi" degan ma'lumot sizib
    # chiqadi — shu bilan hash ni bayt-bayt topib olish mumkin.
    if not hmac.compare_digest(expected, supplied_hash):
        raise _bad("Telegram ma'lumotlari yaroqsiz")

    # ── Bu yerdan pastda ma'lumot TASDIQLANGAN ────────────────

    # Yangilik tekshiruvi imzodan ALOHIDA turadi: imzo to'g'ri bo'lsa ham
    # eski `initData` qabul qilinmaydi (o'g'irlangan havolani qayta ishlatish).
    now = now or datetime.now(UTC)
    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
    except (KeyError, ValueError, OverflowError, OSError):
        raise _bad("Telegram ma'lumotlari yaroqsiz") from None

    if auth_date < now - max_age or auth_date > now + CLOCK_SKEW:
        raise _bad("Havola muddati tugagan, so'rovnomani qaytadan oching")

    # `user` — JSON matn. Guruh/kanal kontekstida umuman bo'lmasligi mumkin;
    # bizga esa hash uchun aynan shu kerak, shuning uchun yo'qligi — rad javob.
    try:
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise _bad("Telegram foydalanuvchisi aniqlanmadi") from None

    if user_id <= 0:
        raise _bad("Telegram foydalanuvchisi aniqlanmadi")

    start_param = fields.get("start_param") or None

    return WebAppInitData(
        user_id=user_id, start_param=start_param, auth_date=auth_date
    )
