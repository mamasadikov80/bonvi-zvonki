"""Chegaralar: parallellik, so'rov tezligi, qulf va 429 dan chekinish.

Uch xil himoya, uchtasi ham kerak:

1. **Parallellik** (`asyncio.Semaphore`) — bitta jarayonda nechta
   qo'ng'iroq bir vaqtda ishlanadi. Busiz 5000 ta vazifa bir zumda
   ochilib, ASR provayderini ham, bazani ham bo'g'ib qo'yadi.
2. **Tezlik** (Redis oynali hisoblagich) — daqiqadagi so'rov soni
   BARCHA workerlar bo'ylab. Semaphore bitta jarayonni tiyadi,
   bu — butun parkni.
3. **Chekinish** (`with_backoff`) — vendor baribir 429 qaytarsa,
   eksponensial kutish + jitter. Jitter shart: usiz hamma worker bir
   vaqtda uyg'onib, yana 429 oladi.

Redis yo'q bo'lsa tizim TO'XTAMAYDI — chegaralar o'chadi va bu bir
marta ogohlantirish sifatida logga tushadi.
"""

import asyncio
import random
import time
from typing import Any

import structlog

from src.core.config import settings
from src.modules.ai.domain.errors import (
    AIError,
    AINetworkError,
    AIRateLimitError,
    AIUnavailableError,
)

log = structlog.get_logger(__name__)

_redis: Any | None = None
_redis_failed = False


async def get_redis() -> Any | None:
    """Umumiy Redis klienti. Ulanib bo'lmasa — `None` va bir marta log."""
    global _redis, _redis_failed
    if _redis is not None:
        return _redis
    if _redis_failed:
        return None
    try:
        from redis.asyncio import from_url

        client = from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
    except Exception as exc:  # noqa: BLE001 — sabab muhim emas, natija muhim
        _redis_failed = True
        log.warning("pipeline.redis_unavailable", error=str(exc))
        return None
    _redis = client
    return client


async def reset_redis() -> None:
    """Testlar orasida ulanishni tozalash uchun."""
    global _redis, _redis_failed
    if _redis is not None:
        await _redis.aclose()
    _redis = None
    _redis_failed = False


# ── Tezlik chegarasi ──────────────────────────────────────────


class RateLimiter:
    """Daqiqalik oynali hisoblagich (barcha workerlar uchun umumiy).

    Aniq token-bucket emas — ataylab: bitta `INCR` + `EXPIRE` Lua'siz
    ishlaydi, oyna chegarasidagi 2× portlash esa vendor uchun sezilarsiz.
    """

    def __init__(self, name: str, per_minute: int) -> None:
        self.name = name
        self.per_minute = max(0, per_minute)
        self.waits = 0
        self.waited_sec = 0.0

    async def acquire(self) -> None:
        if self.per_minute <= 0:
            return
        client = await get_redis()
        if client is None:
            return

        while True:
            window = int(time.time() // 60)
            key = f"zvonki:pipeline:rate:{self.name}:{window}"
            try:
                used = await client.incr(key)
                if used == 1:
                    await client.expire(key, 120)
            except Exception as exc:  # noqa: BLE001
                log.warning("pipeline.rate_limit_skipped", error=str(exc))
                return

            if used <= self.per_minute:
                return

            sleep_for = 60 - (time.time() % 60) + random.uniform(0, 0.5)
            self.waits += 1
            self.waited_sec += sleep_for
            log.info(
                "pipeline.rate_limited",
                limiter=self.name,
                per_minute=self.per_minute,
                used=used,
                sleep_sec=round(sleep_for, 2),
            )
            await asyncio.sleep(sleep_for)


# ── Qo'ng'iroq qulfi ──────────────────────────────────────────


class CallLock:
    """Bitta qo'ng'iroqni bir vaqtda faqat bitta worker ishlaydi.

    Busiz ikki worker bir call'ni bir vaqtda olsa — ikkita ASR
    chaqiruvi, ikki marta pul. `SET NX EX` shuni to'xtatadi.
    """

    def __init__(self, call_id: Any, ttl_sec: int) -> None:
        self.key = f"zvonki:pipeline:lock:{call_id}"
        self.ttl = ttl_sec
        self.token = f"{time.time()}:{random.random()}"
        self._client: Any | None = None
        self.acquired = False

    async def __aenter__(self) -> "CallLock":
        self._client = await get_redis()
        if self._client is None:
            # Redis yo'q — qulfsiz davom etamiz (yakka jarayonli rejim)
            self.acquired = True
            return self
        try:
            self.acquired = bool(
                await self._client.set(self.key, self.token, nx=True, ex=self.ttl)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline.lock_failed", error=str(exc))
            self.acquired = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is None or not self.acquired:
            return
        try:
            if await self._client.get(self.key) == self.token:
                await self._client.delete(self.key)
        except Exception:  # noqa: BLE001, S110 — qulf o'zi TTL bilan ochiladi
            pass


# ── Vaqtinchalik nosozlikdan chekinish ────────────────────────


def _status_of(exc: BaseException) -> int | None:
    """Begona (SDK) xatosidagi HTTP holati.

    ⚠️ FAQAT `AIError` bo'lmagan xatolar uchun. Bizning turlarimizda
    `status_code` — PROVAYDERNIKI emas, o'z API javobimizning kodi
    (`AIError.status_code = 502`, `AIDependencyError = 503`). Uni
    provayder holati deb o'qish «SDK o'rnatilmagan» degan tuzatib
    bo'lmaydigan xatoni ham «server band» deb qayta urintirardi.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def is_rate_limited(exc: BaseException) -> bool:
    if isinstance(exc, AIError):
        # Turi bo'yicha — tarjima qilingan xatoda holat allaqachon
        # aniqlangan (`ai/domain/errors.py: translate()`)
        return isinstance(exc, AIRateLimitError)
    return _status_of(exc) == 429


def is_retryable(exc: BaseException) -> bool:
    """Qayta urinish MA'NOLI bo'lgan nosozliklar.

    Uch turkum, uchalasi ham «provayder tomonidagi o'tkinchi holat»:

      · 429 — so'rovlar chegarasi;
      · 5xx — «model hozir band» (Gemini buni juda tez-tez qaytaradi);
      · tarmoq — ulanish uzildi yoki vaqt tugadi.

    ⚠️ NEGA 5xx QO'SHILDI. Ilgari faqat 429 qayta urinilardi. Amalda esa
    Gemini o'rtacha yuklamada ham 503 «high demand» qaytaradi va bitta
    shunday javob qo'ng'iroqni BUTUNLAY `failed` qilib qo'yardi: uni
    qayta baholash uchun odam kelib tugmani bosishi kerak edi. Yuzta
    qo'ng'iroqli navbatda bu o'nlab «yiqilgan» qatorni anglatadi —
    holbuki hech qanday haqiqiy xato yo'q, model bir necha soniya band
    bo'lgan xolos.

    Mijoz xatolari (400, 401, 404 — noto'g'ri kalit, noto'g'ri model)
    ATAYLAB kirmaydi: ular qayta urinishdan tuzalmaydi, faqat pul va
    vaqt yeydi.
    """
    if isinstance(exc, AIError):
        # Tarjima qilingan xato — holat TURIDA, `status_code` da emas
        return isinstance(exc, (AIRateLimitError, AIUnavailableError, AINetworkError))
    status = _status_of(exc)
    return status == 429 or (status is not None and status >= 500)


async def with_backoff(
    action: Any,
    *,
    max_retries: int,
    base_sec: float,
    max_sec: float,
    label: str,
    call_id: Any = None,
) -> Any:
    """`action()` ni chaqiradi; o'tkinchi nosozlikda kutib qayta uradi.

    Kutish: base·2^(n−1) + 0..1 s jitter, `max_sec` bilan cheklangan.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await action()
        except Exception as exc:  # noqa: BLE001 — tur emas, holat muhim
            if not is_retryable(exc) or attempt > max_retries:
                raise
            delay = min(base_sec * (2 ** (attempt - 1)), max_sec)
            delay += random.uniform(0, min(1.0, base_sec))
            log.warning(
                "pipeline.backoff",
                stage=label,
                call_id=str(call_id) if call_id else None,
                attempt=attempt,
                max_retries=max_retries,
                sleep_sec=round(delay, 2),
                reason=getattr(exc, "message", str(exc)),
            )
            await asyncio.sleep(delay)
