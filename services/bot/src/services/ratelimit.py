"""Ommaviy yuborish tezligini cheklovchi (global pacer).

MUAMMO
  Broadcast 1000 ta guruh uchun 1000 ta so'rovnoma yaratadi. Ular
  navbatga tushadi va bot ularni ketma-ket yuborishga urinadi.
  Telegram global chegarasi — sekundiga ~30 xabar. Sikl to'liq tezlikda
  aylansa (aiohttp uchun 1000 ta `sendMessage` — bir necha soniya)
  chegarani ilk soniyadayoq buzadi. Undan keyin Telegram 429 beradi va
  `retry_after` bilan botni bir necha soniyaga (og'ir holatda
  daqiqalarga) to'xtatib qo'yadi — natijada butun yuborish uzoq
  vaqtga qotib qoladi va navbat orqada qoladi.

YECHIM — bir tekis oraliq
  Har yuborishdan oldin `acquire()` chaqiriladi. U navbatdagi
  yuborishlarni `1/tezlik` soniya oralig'ida BIR TEKIS taqsimlaydi
  (20/s → 50 ms). Portlash yo'q: Telegram bir soniyada 20 tadan
  ortiq ko'rmaydi.

  Bu «to'kilayotgan chelak» (leaky bucket): bitta `_next_at` vaqti
  saqlanadi va har navbat undan 50 ms oldinga suriladi. Qulf ushlab
  turilgani bilan uxlanadi — shuning uchun bir vaqtda kelgan bir
  necha yuboruvchi ham navbatga tizilib, bir-birini bosib o'tmaydi.

TELEGRAM BARIBIR «SEKINROQ» DESA
  `TelegramRetryAfter` — chegara buzilganining aniq belgisi va unda
  necha soniya kutish kerakligi yozilgan. Shunda `_next_at` o'sha
  vaqtga suriladi: JAZO BITTA XABARGA EMAS, BUTUN NAVBATGA tegadi.
  Aks holda keyingi xabar darhol yana urinib, jarimani uzaytirardi.
  O'sha xabarning o'zi bir necha marta qayta urinib ko'riladi.

Bu modul aiogram'dan faqat `TelegramRetryAfter` ni biladi — hisoblagich
tahrirlari ham, so'rovnoma yuborish ham shu bitta pacer orqali o'tadi,
chunki Telegram chegarasi ham bitta va umumiy.
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramRetryAfter

from src.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# `retry_after` ustiga qo'shiladigan zaxira (soniya). Telegram vaqti
# bilan bizning soatimiz aynan bir xil emas — chetiga tegib turmaymiz.
RETRY_MARGIN = 0.5


class SendRateLimiter:
    """Chiquvchi Telegram so'rovlarini bir tekis taqsimlovchi."""

    def __init__(self, rate_per_second: float | None = None) -> None:
        rate = (
            rate_per_second
            if rate_per_second is not None
            else settings.SEND_RATE_PER_SECOND
        )
        self._rate = max(rate, 0.1)
        self._interval = 1.0 / self._rate
        self._next_at = 0.0  # monotonic
        self._lock = asyncio.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    async def acquire(self) -> None:
        """Navbat kelguncha kutadi va o'z uyachasini band qiladi."""
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_at = max(now, self._next_at) + self._interval

    async def penalize(self, seconds: float) -> None:
        """Butun navbatni `seconds` soniyaga orqaga suradi."""
        async with self._lock:
            self._next_at = max(self._next_at, time.monotonic() + seconds)

    async def send(
        self,
        action: Callable[[], Awaitable[T]],
        *,
        what: str = "xabar",
        attempts: int = 3,
    ) -> T:
        """Bitta Telegram so'rovini tezlik chegarasiga bo'ysundirib bajaradi.

        `TelegramRetryAfter` dan boshqa xatolar CHAQIRUVCHIGA
        uzatiladi: guruh o'chirilgan yoki bot chiqarilgan bo'lsa,
        qayta urinishning ma'nosi yo'q.
        """
        last: TelegramRetryAfter | None = None

        for attempt in range(1, attempts + 1):
            await self.acquire()
            try:
                return await action()
            except TelegramRetryAfter as exc:
                last = exc
                delay = float(exc.retry_after) + RETRY_MARGIN
                logger.warning(
                    "⏳ Telegram chekladi (%s): %.1f s kutamiz · urinish %s/%s",
                    what,
                    delay,
                    attempt,
                    attempts,
                )
                # Jazo umumiy: keyingi `acquire()` shu kutishni bajaradi
                await self.penalize(delay)

        assert last is not None  # sikl faqat shu xato bilan tugaydi
        raise last
