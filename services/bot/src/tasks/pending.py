"""Guruh so'rovnomalarining butun hayot sikli (fon vazifasi).

Har ~60 soniyada uchta ish bajariladi:

  1. hisoblagichni yangilash — `GET /groups/live-surveys`
  2. muddati tugagan xabarni O'CHIRISH — `GET /groups/expired-survey-messages`
  3. navbatdagi so'rovnomani yuborish — `GET /groups/pending-surveys`

Yuborilgandan keyin xabar id si `POST /surveys/{token}/sent` bilan
qaytariladi — backend keyinchalik hisoblagichni tahrirlash va
xabarni o'chirish uchun aynan shu id ga tayanadi.

O'CHIRISH NIMAGA XAVFSIZ
  Bot guruh tarixini o'qimaydi va hech qanday xabarni tahlil qilmaydi.
  U faqat backend bergan `(chat_id, message_id)` juftliklarini
  o'chiradi, ular esa botning o'zi yuborgan so'rovnoma xabarlari.
  Bir bot bir nechta dastur bilan ishlatilsa ham begona xabar bu
  ro'yxatga tusha olmaydi.

IKKI MARTA YUBORMASLIK
  Xabar ketdi, lekin `sent` chaqiruvi tarmoq sababli yiqildi deylik.
  Backend uchun so'rovnoma hamon `pending` — keyingi aylanishda u yana
  ro'yxatga tushadi va guruhga IKKINCHI xabar ketardi. Shuning uchun
  yuborilgan tokenlar `_posted` da eslab qolinadi: keyingi aylanishda
  qayta yuborilmaydi, faqat `sent` qayta urinib ko'riladi. Belgi
  `sent` muvaffaqiyatli bo'lgandan keyin o'chiriladi.

XABAR SHAKLI
  Har aylanishda `telegram.miniapp_name` sozlamasi qayta o'qiladi.
  To'ldirilgan bo'lsa xabar Mini App havolasi bilan ketadi, bo'sh
  bo'lsa — eski 1–5 tugmalari bilan. Sozlama panelda o'zgarsa bot
  QAYTA ISHGA TUSHIRILMASDAN yangi shaklga o'tadi.

TEZLIK — 1000 TA GURUH
  Broadcast bir zumda mingta navbat yozuvi yaratadi. Ularni to'liq
  tezlikda yuborish Telegram'ning ~30 xabar/s chegarasini birinchi
  soniyadayoq buzadi va bot 429 bilan to'xtatib qo'yiladi. Shuning
  uchun har `send_message`/`edit_message_text` umumiy pacer orqali
  o'tadi (`services/ratelimit.py`, ~20/s) va jarayon loglarda
  ko'rinib turadi — admin «qotib qoldimi yoki ketyaptimi» degan
  savolga loglardan javob topadi.

Vazifa HECH QACHON sessiyani yiqitmaydi: har aylanish `try` ichida.
"""

import asyncio
import logging
import time
from typing import Any

from aiogram import Bot

from src.core.config import settings
from src.services.chat_info import current_status, member_count_of
from src.services.config_client import ConfigClient
from src.services.internal_api import InternalApiClient
from src.services.ratelimit import SendRateLimiter
from src.services.registry import GroupSurveyRegistry
from src.views.groups import survey_kb, survey_text

logger = logging.getLogger(__name__)


class PendingSurveyPoster:
    """`pending` so'rovnomalarni guruhlarga joylashtiruvchi."""

    def __init__(
        self,
        internal: InternalApiClient,
        registry: GroupSurveyRegistry,
        config: ConfigClient,
        interval: float | None = None,
        limiter: SendRateLimiter | None = None,
    ) -> None:
        self._internal = internal
        self._registry = registry
        # Xabar shakli (`telegram.miniapp_name`) shundan o'qiladi
        self._config = config
        self._interval = (
            interval if interval is not None else settings.PENDING_POLL_SECONDS
        )
        # Chiquvchi Telegram so'rovlarining umumiy tezlik chegarasi.
        # Odatda `runner.py` dan beriladi (butun bot uchun bitta).
        self._limiter = limiter or SendRateLimiter()
        # token → guruhdagi xabar id (hali `sent` tasdiqlanmagan)
        self._posted: dict[str, int] = {}
        # token → oxirgi ko'rsatilgan javoblar soni. Faqat o'zgargan
        # xabar tahrirlanadi — Telegram tahrirlash chastotasini cheklaydi
        self._shown: dict[str, int] = {}
        self._bot_username = ""

    async def run(self, bot: Bot, bot_username: str) -> None:
        """Sessiya davomida aylanadi. Bekor qilinsa — jimgina chiqadi."""
        logger.info(
            "📮 So'rovnoma yuboruvchi ishga tushdi · tekshiruv: %.0fs",
            self._interval,
        )
        self._bot_username = bot_username
        while True:
            try:
                await self._tick(bot, bot_username)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("⚠️  Navbatni tekshirishda xato: %s", exc)
            await asyncio.sleep(self._interval)

    # ── Ichki ─────────────────────────────────────────────────

    async def _tick(self, bot: Bot, bot_username: str) -> None:
        # Avval jonli xabarlardagi hisoblagich — navbat bo'sh bo'lsa ham
        # bajariladi, chunki Mini App rejimida baholar botdan o'tmaydi
        await self._sync_counters(bot)

        # Muddati tugagan xabarlarni guruhdan olib tashlash
        await self._cleanup_expired(bot)

        items = await self._internal.pending_surveys()
        if not items:
            return
        total = len(items)
        logger.info(
            "📮 Navbatda %s ta so'rovnoma · tezlik chegarasi ~%.0f/s · "
            "taxminan %.0f s",
            total,
            self._limiter.rate,
            total / self._limiter.rate,
        )

        # Sozlama yuborishdan OLDIN yangilanadi: admin panelda Mini App
        # nomini to'ldirsa, keyingi xabar darhol yangi shaklda ketsin —
        # botni qayta ishga tushirish shart emas. Backend javob bermasa
        # `fetch()` keshni tegmasdan qoldiradi, ya'ni oxirgi ma'lum
        # shakl ishlatiladi.
        await self._config.fetch()
        miniapp_name = self._config.miniapp_name
        logger.info(
            "🧭 Xabar shakli: %s",
            f"Mini App havolasi (/{miniapp_name})"
            if miniapp_name
            else "guruhdagi 1–5 tugmalari (admin tanlovi yoki Mini App sozlanmagan)",
        )

        started = time.monotonic()
        sent = 0
        failed = 0
        every = max(1, settings.SEND_PROGRESS_EVERY)

        for index, item in enumerate(items, start=1):
            try:
                await self._post_one(bot, bot_username, item, miniapp_name)
                sent += 1
            except asyncio.CancelledError:
                # Sessiya yopilyapti — qayerda to'xtaganimiz ko'rinsin
                logger.info(
                    "⏹️  Yuborish to'xtatildi · %s/%s ta ketdi", sent, total
                )
                raise
            except Exception as exc:
                failed += 1
                logger.warning("⚠️  So'rovnoma yuborilmadi: %s", exc)

            # Jarayon loglarda ko'rinib tursin: 1000 ta guruhda bu
            # aylanish bir necha daqiqa davom etadi va admin «bot
            # qotib qoldimi?» degan savolga javob izlaydi.
            if index % every == 0 or index == total:
                elapsed = max(time.monotonic() - started, 1e-6)
                logger.info(
                    "📤 %s/%s · yuborildi=%s · xato=%s · %.1f xabar/s · %.0f s",
                    index,
                    total,
                    sent,
                    failed,
                    index / elapsed,
                    elapsed,
                )

        elapsed = max(time.monotonic() - started, 1e-6)
        logger.info(
            "✅ Navbat tugadi · %s/%s yuborildi · %.1f xabar/s · jami %.1f s",
            sent,
            total,
            total / elapsed,
            elapsed,
        )

    async def _sync_counters(self, bot: Bot) -> None:
        """Guruhdagi «N kishi baho berdi» yozuvini haqiqiy songa keltiradi.

        Mini App rejimida baho `POST /surveys/webapp/submit` orqali
        tushadi va bot bundan bexabar qoladi — hisoblagich «hali hech
        kim baho bermadi» bo'lib qotib qolardi. Bu ishtirokni pasaytiradi:
        odam hech kim javob bermagan so'rovnomaga javob bergisi kelmaydi.

        Faqat soni O'ZGARGAN xabar tahrirlanadi. Telegram tahrirlashni
        cheklaydi, har aylanishda barcha xabarlarni qayta yozish esa
        keraksiz va xavfli.
        """
        try:
            items = await self._internal.live_surveys()
        except Exception as exc:
            logger.debug("Hisoblagichni o'qib bo'lmadi: %s", exc)
            return

        for item in items:
            token = str(item.get("token") or "")
            count = int(item.get("response_count") or 0)
            if not token or self._shown.get(token) == count:
                continue

            # Xabar QAYSI shaklda yuborilgan bo'lsa, o'sha shaklda qayta
            # chiziladi. Tugmali xabarlarni bu yerda umuman tegmaymiz:
            # ularda baho bot orqali keladi va hisoblagichni `throttle.py`
            # allaqachon yangilaydi. Aks holda admin Mini App sozlamasini
            # yoqqan zahoti eski xabarlarning tugmalari yo'qolib, hali
            # ovoz bermaganlar baho bera olmay qolardi.
            known = await self._registry.lookup(token)
            if known is None or not known[2]:
                self._shown[token] = count
                continue

            try:
                # Tahrirlar ham xuddi yuborish kabi Telegram chegarasiga
                # kiradi — 1000 ta jonli so'rovnomada bu ham portlash.
                await self._limiter.send(
                    lambda: bot.edit_message_text(
                        chat_id=int(item["chat_id"]),
                        message_id=int(item["chat_message_id"]),
                        text=survey_text(count, self._config.miniapp_name),
                        reply_markup=survey_kb(
                            self._bot_username, token, self._config.miniapp_name
                        ),
                    ),
                    what="hisoblagich",
                )
                self._shown[token] = count
            except Exception as exc:
                # «message is not modified» va shunga o'xshashlar normal
                logger.debug("Hisoblagich yangilanmadi (%s): %s", token[:8], exc)
                self._shown[token] = count

    async def _cleanup_expired(self, bot: Bot) -> None:
        """Muddati tugagan so'rovnoma xabarini guruhdan o'chiradi.

        BOSHQA XABARLARGA TEGMASLIK KAFOLATI
          Bu yerda guruh tarixi umuman o'qilmaydi va hech narsa
          «so'rovnomaga o'xshaydi» deb taxmin qilinmaydi. O'chiriladigan
          `(chat_id, message_id)` juftliklari backenddan keladi va har
          biri — botning O'ZI yuborgan, `mark_sent` bilan bazaga
          yozilgan so'rovnoma xabari. Bir bot bir nechta dastur bilan
          ishlatilsa, boshqa dastur yuborgan xabar `surveys` jadvalida
          umuman yo'q, demak bu ro'yxatga ham tushmaydi.

        MUVAFFAQIYATSIZ URINISH — TERMINAL
          Telegram botga o'z xabarini 48 soatdan keyin o'chirishga
          ruxsat bermaydi. Bot uzoq o'chib turgan bo'lsa xabar
          o'chmaydi — shunda ham yozuv «tugadi» deb belgilanadi,
          aks holda navbat o'chirib bo'lmaydigan xabarlar bilan
          to'lib borardi. Sabab logda qoladi.
        """
        try:
            items = await self._internal.expired_survey_messages()
        except Exception as exc:
            logger.debug("Muddati o'tgan xabarlarni o'qib bo'lmadi: %s", exc)
            return

        if not items:
            return

        logger.info("🧹 Muddati tugagan %s ta so'rovnoma xabari", len(items))

        for item in items:
            token = str(item.get("token") or "")
            raw_chat = item.get("chat_id")
            raw_message = item.get("chat_message_id")
            if not token or raw_chat is None or raw_message is None:
                continue

            chat_id = int(raw_chat)
            message_id = int(raw_message)

            try:
                # O'chirish ham Telegram chegarasiga kiradi — 1000 ta
                # xabar bir zumda o'chirilsa 429 keladi.
                await self._limiter.send(
                    lambda: bot.delete_message(
                        chat_id=chat_id, message_id=message_id
                    ),
                    what=f"xabarni o'chirish (guruh {chat_id})",
                )
                logger.debug(
                    "🧹 Xabar o'chirildi · guruh=%s · xabar=%s", chat_id, message_id
                )
            except Exception as exc:
                # «message to delete not found» — xabar allaqachon yo'q
                # (admin qo'lda o'chirgan). Bu ham tugagan holat.
                logger.info(
                    "🧹 Xabar o'chirilmadi (guruh=%s, xabar=%s): %s — "
                    "yozuv baribir yopiladi",
                    chat_id,
                    message_id,
                    exc,
                )

            # Muvaffaqiyatli ham, muvaffaqiyatsiz ham — belgilaymiz.
            # Belgilanmasa yozuv keyingi aylanishda qaytib keladi.
            if not await self._internal.mark_message_deleted(token):
                logger.warning(
                    "⚠️  Xabar o'chirildi, lekin belgi yozilmadi (%s) — "
                    "keyingi aylanishda qayta urinamiz",
                    token[:8],
                )
                continue

            # Hisoblagich keshi ham tozalanadi: xabar endi yo'q
            self._shown.pop(token, None)

    async def _post_one(
        self,
        bot: Bot,
        bot_username: str,
        item: dict[str, Any],
        miniapp_name: str = "",
    ) -> None:
        token = str(item.get("token") or "").strip()
        raw_chat = item.get("chat_id")
        if not token or raw_chat is None:
            logger.warning("⚠️  Navbatdagi yozuv to'liq emas — o'tkazib yuborildi")
            return
        chat_id = int(raw_chat)

        message_id = self._posted.get(token)

        if message_id is None:
            # Tezlik chegarasi shu yerda: `send()` navbat kelguncha
            # kutadi va `TelegramRetryAfter` bo'lsa BUTUN navbatni
            # orqaga suradi (qarang: services/ratelimit.py).
            message = await self._limiter.send(
                lambda: bot.send_message(
                    chat_id,
                    survey_text(0, miniapp_name),
                    reply_markup=survey_kb(bot_username, token, miniapp_name),
                ),
                what=f"guruh {chat_id}",
            )
            message_id = message.message_id
            self._posted[token] = message_id

            # Bot bu tokenni O'ZI yuborganini eslab qoladi — shaxsiy
            # chatda `/start srv_<token>` kelganda qaysi oqim ekani
            # shundan aniqlanadi (qarang: services/registry.py).
            await self._registry.remember(
                token, chat_id, message_id, miniapp=bool(miniapp_name)
            )

            # Kamar ustiga tasma: yuborish ishlagan ekan, guruh haqiqatan
            # bor. Nomi va a'zolar soni o'zgargan bo'lishi mumkin —
            # panelda eskirib qolmasin deb har yuborishda yangilaymiz.
            await self._refresh_group(bot, chat_id, message.chat.title)

            # ATAYLAB `debug`: 1000 ta guruhda bu 1000 qator berardi va
            # jarayon xulosasini (`📤 N/M …`) ko'mib tashlardi. Bitta
            # guruhni qidirish kerak bo'lsa `DEBUG` yoqiladi.
            logger.debug(
                "📤 So'rovnoma yuborildi · guruh=%s · xabar=%s", chat_id, message_id
            )

        if await self._internal.mark_sent(token, message_id):
            self._posted.pop(token, None)
        else:
            logger.warning(
                "⚠️  `sent` tasdiqlanmadi (guruh=%s) — keyingi aylanishda qayta urinamiz",
                chat_id,
            )

    async def _refresh_group(self, bot: Bot, chat_id: int, title: str | None) -> None:
        await self._internal.register_group(
            chat_id=chat_id,
            title=(title or "").strip() or "Nomsiz guruh",
            member_count=await member_count_of(bot, chat_id),
            bot_status=await current_status(bot, chat_id),
        )
