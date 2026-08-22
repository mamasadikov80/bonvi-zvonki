"""Telegram'ga xabar yuborish — backend tomonidan, to'g'ridan-to'g'ri.

⚠️ BU MODULDAGI YAGONA FUNKSIYA TASHQARIGA CHIQADI. Butun loyihada
backend'dan Telegram'ga ketadigan boshqa yo'l yo'q, shuning uchun
testda faqat shu bittasini almashtirish kifoya — «tasodifan haqiqiy
guruhga xabar ketib qolmasin» degan xavf bir joyda jamlangan.

════════════════════════════════════════════════════════════════
 NEGA BOT ORQALI EMAS
════════════════════════════════════════════════════════════════

Guruh so'rovnomalari boshqacha ishlaydi: backend navbatga yozadi,
bot esa har ~60 soniyada `GET /groups/pending-surveys` bilan olib
yuboradi (`services/bot/src/tasks/pending.py`). O'sha mexanizm
so'rovnomaga MOSLANGAN — reyestr, hisoblagich tahriri, xabarni
keyin o'chirish, deep-link va tugmalar. Kunlik xabarda bularning
biri ham kerak emas.

Hal qiluvchi sabab esa boshqa: «Sinov xabari» tugmasi bosilganda
foydalanuvchi DARHOL javob kutadi — «ketdimi yoki yo'qmi, matni
qanaqa». Navbat orqali bunga javob berib bo'lmaydi: backend faqat
«navbatga qo'yildi» deya olardi, natijani esa bir daqiqadan keyin
bot bilardi va foydalanuvchiga aytadigan odam qolmasdi.

Shuning uchun bu yerda oddiy HTTP chaqiruvi. QAYTA YOZILGAN NARSA
YO'Q: token o'sha-o'sha (`telegram.bot_token` sozlamasi, botnikidan
farq qilmaydi), guruhlar o'sha-o'sha (`telegram_groups`), yangi
maxfiy kalit ham, yangi navbat ham qo'shilmadi.
"""

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger(__name__)

#: Telegram'ning bitta xabar uchun chegarasi — belgilarda.
#
# Undan uzun matn `400 Bad Request: message is too long` bilan
# QAYTARILADI, ya'ni xabar umuman ketmaydi. Shuning uchun matn
# yig'ilayotgan paytda qisqartiriladi (`digest.py`), bu yerda esa
# faqat chegaraning o'zi e'lon qilinadi.
TELEGRAM_TEXT_LIMIT = 4096

#: Bitta so'rov shuncha kutadi. Kunlik vazifa Telegram sekinlashsa
#: ham osilib qolmasligi kerak.
TIMEOUT_SECONDS = 20.0

API_BASE = "https://api.telegram.org"


@dataclass(slots=True)
class SendResult:
    """Yuborish natijasi — istisno emas, javob.

    Kunlik vazifa uchun Telegram nosozligi FALOKAT EMAS: ertaga yangi
    xabar keladi. Shuning uchun xato ko'tarilmaydi, qaytariladi va
    chaqiruvchi uni logga ham, audit yozuviga ham yozadi.
    """

    ok: bool
    message_id: int | None = None
    error: str | None = None


async def send_message(*, token: str, chat_id: str, text: str) -> SendResult:
    """Bitta xabar yuboradi (Telegram HTML)."""
    if len(text) > TELEGRAM_TEXT_LIMIT:
        # Bu yerga yetib kelishi — chaqiruvchidagi xato. Tarmoqqa
        # chiqmaymiz: Telegram baribir rad etardi.
        return SendResult(
            ok=False,
            error=(
                f"Matn juda uzun: {len(text)} belgi "
                f"(chegara {TELEGRAM_TEXT_LIMIT})"
            ),
        )

    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        # Xabardagi havola panelga olib boradi — uning ko'rinishi
        # (preview) guruhda ortiqcha joy egallaydi va matnni bosib
        # qo'yadi.
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001 — tarmoq xatosi ham natija
        log.error("sales.digest.send_failed", error=str(exc))
        return SendResult(ok=False, error=str(exc))

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code != 200 or not body.get("ok"):
        # Telegram sababni matn bilan aytadi («chat not found»,
        # «bot was kicked…») — uni yutib yuborish admin uchun eng
        # yomon holat bo'lardi.
        reason = str(body.get("description") or response.text or response.status_code)
        log.error("sales.digest.rejected", status=response.status_code, reason=reason)
        return SendResult(ok=False, error=reason)

    message_id = (body.get("result") or {}).get("message_id")
    return SendResult(ok=True, message_id=message_id)
