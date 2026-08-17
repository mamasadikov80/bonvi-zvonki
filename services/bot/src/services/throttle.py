"""Guruh xabaridagi hisoblagichni siqib yangilash.

MUAMMO
  Har javobdan keyin "✅ N kishi baho berdi" ni yangilash uchun
  `editMessageText` chaqirilsa, 30 kishilik guruh bir daqiqada 30 ta
  tahrir so'rovi yuboradi. Telegram bir chatga sekundiga ~1 xabar /
  daqiqasiga ~20 xabar chegarasini qo'yadi va ortiqchasiga 429
  (`retry_after`) beradi — bir necha soniyaga chat butunlay bloklanadi.
  Bundan tashqari ketma-ket ikki tahrir bir xil matn bersa Telegram
  "message is not modified" xatosini qaytaradi.

YECHIM — "oxirgi qiymat yutadi" (last-write-wins) siqish
  Har xabar uchun bitta uyacha (`_Slot`) saqlanadi. Yangi javob kelganda
  uyachadagi son yangilanadi va AGAR navbatda tahrir turgan bo'lsa,
  boshqa hech narsa qilinmaydi. Navbat bo'sh bo'lsa — oxirgi tahrirdan
  beri `interval` o'tguncha kutadigan bitta vazifa qo'yiladi.

  Natijada bir xabar uchun `interval` (sukut bo'yicha 5 s) ichida ENG
  KO'PI BILAN BITTA tahrir ketadi, va u har doim ENG SO'NGGI sonni
  ko'rsatadi — oraliq qiymatlar shunchaki tashlab yuboriladi.

30 KISHI 2 SONIYADA BOSSA NIMA BO'LADI?
  1-javob: navbat bo'sh, oxirgi tahrir yo'q → vazifa 0 s kutib darhol
  tahrirlaydi ("1 kishi").
  2–30-javoblar: vazifa hali tugamagan yoki 5 s to'lmagan → faqat
  uyachadagi son 30 gacha o'sadi, YANGI so'rov QO'YILMAYDI.
  ~5-soniyada bitta vazifa uyg'onadi va "30 kishi baho berdi" deb bir
  marta tahrirlaydi.
  Jami: 30 ta emas, 2 ta `editMessageText`. Har bir bosgan odam esa
  javobni darhol `show_alert` oynasida ko'radi — kutish sezilmaydi.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from src.core.config import settings
from src.views.groups import survey_kb, survey_text

logger = logging.getLogger(__name__)

# Uzoq tegilmagan uyachalar shu muddatdan keyin tozalanadi (soniya).
# Bot oylab ishlaganda dict cheksiz o'smasin.
SLOT_TTL = 6 * 3600.0


@dataclass
class _Slot:
    """Bitta guruh xabari uchun kutayotgan holat."""

    token: str
    bot_username: str
    count: int
    # Oxirgi muvaffaqiyatli tahrir vaqti (monotonic). -inf = hali tahrir yo'q.
    last_edit: float = float("-inf")
    # Oxirgi tegilgan vaqt — tozalash uchun
    touched: float = field(default_factory=time.monotonic)
    task: asyncio.Task[None] | None = None
    # Telegram'ga yozilgan oxirgi son — bir xil bo'lsa umuman so'rov ketmaydi
    shown: int | None = None


class CounterThrottle:
    """Xabar hisoblagichini cheklangan tezlikda yangilovchi."""

    def __init__(self, interval: float | None = None) -> None:
        self._interval = (
            interval if interval is not None else settings.COUNTER_EDIT_SECONDS
        )
        self._slots: dict[tuple[int, int], _Slot] = {}
        self._lock = asyncio.Lock()

    async def push(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        token: str,
        bot_username: str,
        count: int,
    ) -> None:
        """Yangi javob soni keldi — kerak bo'lsa tahrirni rejalashtiradi."""
        key = (chat_id, message_id)
        now = time.monotonic()

        async with self._lock:
            self._prune(now)
            slot = self._slots.get(key)
            if slot is None:
                slot = _Slot(token=token, bot_username=bot_username, count=count)
                self._slots[key] = slot
            else:
                # Kechikkan so'rov eski sonni yozib yubormasin
                slot.count = max(slot.count, count)
                slot.token = token
                slot.bot_username = bot_username
            slot.touched = now

            if slot.task is not None and not slot.task.done():
                # Navbatda tahrir bor — u uyg'onganda eng so'nggi sonni oladi
                return

            delay = max(0.0, self._interval - (now - slot.last_edit))
            slot.task = asyncio.create_task(
                self._flush(bot, key, delay), name="counter-edit"
            )

    async def close(self) -> None:
        """Kutayotgan barcha tahrirlarni bekor qiladi (sessiya yopilganda)."""
        async with self._lock:
            tasks = [s.task for s in self._slots.values() if s.task is not None]
            self._slots.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Ichki ─────────────────────────────────────────────────

    async def _flush(self, bot: Bot, key: tuple[int, int], delay: float) -> None:
        """Kutadi va uyachadagi ENG SO'NGGI sonni yozadi."""
        if delay > 0:
            await asyncio.sleep(delay)

        async with self._lock:
            slot = self._slots.get(key)
            if slot is None:
                return
            count, token, username = slot.count, slot.token, slot.bot_username
            if slot.shown == count:
                # Hech narsa o'zgarmagan — bekorga so'rov yubormaymiz
                slot.last_edit = time.monotonic()
                return

        chat_id, message_id = key
        ok = await self._edit(bot, chat_id, message_id, token, username, count)

        async with self._lock:
            slot = self._slots.get(key)
            if slot is None:
                return
            slot.last_edit = time.monotonic()
            if ok:
                slot.shown = count

    async def _edit(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        token: str,
        bot_username: str,
        count: int,
    ) -> bool:
        """Bitta `editMessageText`. Xatolar yutiladi — bot to'xtamasin."""
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=survey_text(count),
                # Tugmalar HAR SAFAR qayta beriladi: `reply_markup` siz
                # tahrir klaviaturani butunlay o'chirib yuboradi.
                #
                # Qisqa nom ATAYLAB berilmaydi (ya'ni eski, 1–5 li
                # shakl chiziladi): bu yerga faqat `rate:` callback'i
                # olib keladi, u esa faqat ESKI xabarda bo'ladi.
                # Mini App nomini qo'shsak, tahrir o'sha eski xabarning
                # tugmalarini olib tashlab, hali baho bermaganlarning
                # yo'lini kesib qo'yardi.
                reply_markup=survey_kb(bot_username, token),
            )
            return True

        except TelegramRetryAfter as exc:
            # Telegram aniq necha soniya kutishni aytadi — quloq solamiz.
            logger.warning(
                "⏳ Telegram tahrirni chekladi, %s s kutamiz (chat %s)",
                exc.retry_after,
                chat_id,
            )
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            return False

        except TelegramBadRequest as exc:
            text = str(exc).lower()
            if "not modified" in text:
                # Normal holat: son o'zgarmagan. Xato emas.
                logger.debug("Xabar o'zgarmadi (chat %s)", chat_id)
                return True
            if "message to edit not found" in text or "message can't be edited" in text:
                logger.warning("Xabar tahrirlanmadi (chat %s): %s", chat_id, exc)
                return False
            logger.warning("Tahrir xatosi (chat %s): %s", chat_id, exc)
            return False

        except TelegramForbiddenError:
            logger.warning("Bot guruhdan chiqarilgan (chat %s) — tahrir yo'q", chat_id)
            return False

        except Exception as exc:  # tarmoq va boshqa kutilmagan holatlar
            logger.warning("Tahrir yuborilmadi (chat %s): %s", chat_id, exc)
            return False

    def _prune(self, now: float) -> None:
        """Eskirgan uyachalarni tozalaydi (xotira o'smasin)."""
        if len(self._slots) < 64:
            return
        stale = [
            key
            for key, slot in self._slots.items()
            if now - slot.touched > SLOT_TTL
            and (slot.task is None or slot.task.done())
        ]
        for key in stale:
            self._slots.pop(key, None)
