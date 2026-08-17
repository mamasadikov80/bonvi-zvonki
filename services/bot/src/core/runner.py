"""Bot supervisori — token hayotiy siklini boshqaradi.

Nima uchun alohida sinf kerak?
`main()` da bitta `Bot` yaratib polling'ni ishga tushirish yetarli emas:
token endi `.env` da emas, BAZADA turadi va admin uni istalgan payt
dashboard'dan o'zgartirishi mumkin. Shuning uchun kimdir tokenni
kuzatib turishi, o'zgarganda eski sessiyani yopib, yangisini ochishi kerak.
`BotRunner` — o'sha "kimdir".

Sikl:

    1. Tokenni topish        →  backend (baza > .env) , javob bo'lmasa .env
    2. Sessiya               →  Bot + Dispatcher + get_me() + polling
    3. Kuzatuv               →  har CONFIG_POLL_SECONDS da backend so'raladi
    4. Token o'zgardi        →  polling to'xtaydi, sessiya yopiladi → 1-qadam

Muhim: bot HECH QACHON crash-loop ga tushmasligi kerak. Token yo'q bo'lsa
ham, noto'g'ri bo'lsa ham, backend o'lgan bo'lsa ham — jarayon tirik qoladi
va tekshirishda davom etadi. Aks holda konteyner qayta-qayta o'chib yonadi
va admin panelga token kiritishning imkoni bo'lmaydi.
"""

import asyncio
import logging
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.token import TokenValidationError

from src.core.config import mask_secret, settings
from src.handlers import autobind, enroll, errors, groups, survey
from src.middlewares.api import ApiMiddleware
from src.services.api import ApiClient
from src.services.binding import AgentBinder, AutobindCache
from src.services.config_client import ConfigClient
from src.services.internal_api import InternalApiClient
from src.services.ratelimit import SendRateLimiter
from src.services.registry import GroupSurveyRegistry
from src.services.throttle import CounterThrottle
from src.tasks.pending import PendingSurveyPoster

logger = logging.getLogger("bot.runner")

# Telegram/tarmoq xatosidan keyingi qisqa pauza — tez aylanib
# ketmaslik uchun (soniya)
NETWORK_RETRY_SECONDS = 10.0


class BotRunner:
    """Token o'zgarishiga qarab bot sessiyalarini boshqaruvchi supervisor."""

    def __init__(self) -> None:
        self._api = ApiClient()
        self._config = ConfigClient()
        # Guruh oqimi uchun ichki klient (`X-Internal-Token`)
        self._internal = InternalApiClient()
        # Bot yuborgan guruh so'rovnomalari reyestri (Redis)
        self._registry = GroupSurveyRegistry()
        # Guruh xabaridagi hisoblagichni siqib yangilovchi
        self._throttle = CounterThrottle()
        # Guruhga savdo xodimini avtomatik biriktiruvchi + uning keshi.
        # Kesh Redis'da: bot qayta ishga tushganda 1000 ta guruh
        # backend'ga qaytadan yopirilib ketmasin.
        self._autobind_cache = AutobindCache()
        self._binder = AgentBinder(self._internal, self._autobind_cache)
        # Chiquvchi Telegram so'rovlarining UMUMIY tezlik chegarasi.
        # So'rovnoma yuborish ham, hisoblagich tahriri ham shu bittasi
        # orqali o'tadi — Telegram chegarasi ham bitta va umumiy.
        self._limiter = SendRateLimiter()
        # Navbatdagi so'rovnomalarni guruhlarga yuboruvchi fon vazifasi.
        # `ConfigClient` ham beriladi: xabar shakli (Mini App havolasimi
        # yoki 1–5 tugmalarimi) admin paneldagi `survey.mode` tanloviga
        # (va Mini App qisqa nomiga) bog'liq — ikkalasi ham ish davomida
        # o'zgarishi mumkin.
        self._poster = PendingSurveyPoster(
            self._internal, self._registry, self._config, limiter=self._limiter
        )
        # FSM saqlagichi butun jarayon davomida bitta — sessiya qayta
        # ishga tushganda Redis ulanishlari qayta ochilmaydi.
        self._storage = RedisStorage.from_url(settings.REDIS_URL)
        # Dispatcher ham bitta va u BOTGA BOG'LIQ EMAS: aiogram 3 da bot
        # `start_polling(bot)` ga uzatiladi. Har sessiyada yangisini
        # yaratib bo'lmaydi — `Router` obyektlari modul darajasida bitta
        # nusxada va ikkinchi Dispatcher'ga ulanmaydi
        # ("Router is already attached to ...").
        self._dispatcher = self._build_dispatcher()
        self._idle_warned = False

    # ── Asosiy sikl ───────────────────────────────────────────

    async def run(self) -> None:
        logger.info(
            "🚀 Runner ishga tushdi · backend: %s · ichki kalit: %s · tekshiruv: %.0fs",
            settings.API_BASE_URL,
            self._config.describe_auth(),
            settings.CONFIG_POLL_SECONDS,
        )
        try:
            while True:
                token = await self._resolve_token()
                await self._run_session(token)
        finally:
            await self._throttle.close()
            await self._api.close()
            await self._config.close()
            await self._internal.close()
            await self._registry.close()
            await self._autobind_cache.close()
            await self._storage.close()

    # ── 1. Tokenni topish ─────────────────────────────────────

    async def _resolve_token(self) -> str:
        """Ishlatiladigan tokenni qaytaradi (kerak bo'lsa kutib turadi).

        Backend hali ko'tarilmagan bo'lishi mumkin — shuning uchun birinchi
        ~30 soniya davomida qisqa backoff bilan qayta-qayta so'raladi.
        Shundan keyin ham javob bo'lmasa `.env` dagi zaxiraga o'tiladi.
        """
        deadline = time.monotonic() + settings.CONFIG_STARTUP_TIMEOUT
        delay = 2.0

        while True:
            remote = await self._config.fetch()

            if remote is not None:
                if remote.has_token:
                    self._idle_warned = False
                    logger.info(
                        "🔑 Token backend'dan olindi (baza > .env): %s",
                        mask_secret(remote.token),
                    )
                    return remote.token
                # Backend javob berdi, lekin token hech qayerda yo'q
                self._warn_no_token()
                await asyncio.sleep(settings.CONFIG_POLL_SECONDS)
                continue

            # Backend javob bermadi — boshida biroz kutamiz
            if time.monotonic() < deadline:
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 5.0)
                continue

            env_token = settings.TELEGRAM_BOT_TOKEN.strip()
            if env_token:
                logger.warning(
                    "⚠️  Backend javob bermadi — .env dagi zaxira token ishlatiladi: %s",
                    mask_secret(env_token),
                )
                return env_token

            self._warn_no_token()
            await asyncio.sleep(settings.CONFIG_POLL_SECONDS)

    def _warn_no_token(self) -> None:
        """Token yo'qligi haqida ogohlantirish — takrorlanmasin."""
        if self._idle_warned:
            return
        self._idle_warned = True
        logger.warning(
            "\n"
            "  ⚠️  Telegram bot tokeni ko'rsatilmagan.\n"
            "     Bot kutish rejimida — har %.0f soniyada qayta tekshiradi.\n"
            "     Tokenni dashboard → Sozlamalar → «Telegram bot» bo'limiga kiriting\n"
            "     (yoki .env dagi TELEGRAM_BOT_TOKEN ga). Qayta ishga tushirish shart emas.\n",
            settings.CONFIG_POLL_SECONDS,
        )

    # ── 2. Sessiya ────────────────────────────────────────────

    def _build_dispatcher(self) -> Dispatcher:
        dispatcher = Dispatcher(storage=self._storage)
        dispatcher.update.middleware(
            ApiMiddleware(
                self._api,
                self._internal,
                self._registry,
                self._throttle,
                self._binder,
            )
        )
        # TARTIB MUHIM — aiogram birinchi mos kelgan handler'da to'xtaydi:
        #
        #   groups    guruhdagi aniq buyruqlar (`/bind`) va tugmalar
        #   enroll    shaxsiy chatdagi kontakt kartasi
        #   survey    `srv_` deep-link va eski client oqimi
        #   autobind  guruhdagi HAR QANDAY xabar — shuning uchun eng
        #             oxirida: oldinda tursa qolganini bosib ketardi
        #   errors    faqat istisno chiqqanda ishlaydi
        dispatcher.include_router(groups.router)
        dispatcher.include_router(enroll.router)
        dispatcher.include_router(survey.router)
        dispatcher.include_router(autobind.router)
        dispatcher.include_router(errors.router)
        return dispatcher

    async def _run_session(self, token: str) -> None:
        """Bitta token bilan ishlaydigan sessiya. Token o'zgarsa qaytadi."""
        try:
            bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
        except TokenValidationError as exc:
            logger.error(
                "❌ Token formati noto'g'ri (%s): %s", mask_secret(token), exc
            )
            await self._wait_for_new_token(token)
            return

        # Bu yerdan keyin har qanday yo'l bilan chiqilsa ham HTTP sessiya
        # yopilishi shart — aks holda aiohttp ulanishlari to'planib qoladi.
        try:
            await self._serve(bot, token)
        finally:
            await bot.session.close()
            logger.info("🔻 Sessiya yopildi (%s)", mask_secret(token))

    async def _serve(self, bot: Bot, token: str) -> None:
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError:
            logger.error(
                "❌ Telegram tokenni rad etdi (%s) — 401 Unauthorized.\n"
                "     Sozlamalar → «Telegram bot» bo'limidan tokenni tekshiring.\n"
                "     Bot o'chmaydi — to'g'ri token kiritilishini kutadi.",
                mask_secret(token),
            )
            await self._wait_for_new_token(token)
            return
        except (TelegramAPIError, OSError) as exc:
            logger.error(
                "❌ Telegram bilan aloqa yo'q (%s): %s — %.0fs dan keyin qayta urinamiz",
                mask_secret(token),
                exc,
                NETWORK_RETRY_SECONDS,
            )
            await asyncio.sleep(NETWORK_RETRY_SECONDS)
            return

        logger.info("✅ Bot ishga tushdi: @%s", me.username)
        # Deep-link uchun username admin panelida ko'rinsin
        await self._config.report_identity(me.username)

        dispatcher = self._dispatcher
        watcher = asyncio.create_task(self._watch_token(token), name="token-watcher")
        # Fon vazifasi — polling'dan mustaqil: so'rovnomalarni guruhlarga
        # yuboradi. Supervisor uni ham sessiya bilan birga boshlaydi va
        # to'xtatadi, chunki u `bot` obyektiga bog'liq.
        poster = asyncio.create_task(
            self._poster.run(bot, me.username or ""), name="survey-poster"
        )
        polling: asyncio.Task[None] | None = None

        try:
            await bot.delete_webhook(drop_pending_updates=True)
            polling = asyncio.create_task(
                dispatcher.start_polling(bot, handle_signals=False), name="polling"
            )

            done, _ = await asyncio.wait(
                {polling, watcher}, return_when=asyncio.FIRST_COMPLETED
            )

            if watcher in done and not watcher.cancelled():
                new_token = watcher.result()
                logger.warning(
                    "🔄 Token o'zgardi (%s → %s) — bot qayta ishga tushirilmoqda...",
                    mask_secret(token),
                    mask_secret(new_token),
                )
                await self._stop_polling(dispatcher, polling)
            elif polling in done:
                exc = polling.exception()
                if exc is not None:
                    logger.error("❌ Polling to'xtadi: %s", exc)
                    await asyncio.sleep(NETWORK_RETRY_SECONDS)
        finally:
            watcher.cancel()
            poster.cancel()
            await asyncio.gather(poster, return_exceptions=True)
            # Kutayotgan hisoblagich tahrirlari eski `bot` bilan
            # ketmasin — sessiya bilan birga bekor qilinadi.
            await self._throttle.close()
            if polling is not None and not polling.done():
                await self._stop_polling(dispatcher, polling)

    @staticmethod
    async def _stop_polling(
        dispatcher: Dispatcher, polling: asyncio.Task[None]
    ) -> None:
        """Polling'ni muloyim to'xtatadi (kutilayotgan `getUpdates` tugaydi)."""
        try:
            await dispatcher.stop_polling()
        except RuntimeError:
            # Polling hali boshlanmagan bo'lsa — shunchaki bekor qilamiz
            polling.cancel()
        await asyncio.gather(polling, return_exceptions=True)

    # ── 3. Kuzatuv ────────────────────────────────────────────

    async def _watch_token(self, current: str) -> str:
        """Fon vazifasi: token o'zgarishini kutadi va yangisini qaytaradi.

        Backend javob bermasa — hozirgi token bilan ishlashda davom etamiz
        (vaqtinchalik uzilish sabab botni to'xtatish mantiqsiz).
        """
        while True:
            await asyncio.sleep(settings.CONFIG_POLL_SECONDS)
            remote = await self._config.fetch()
            if remote is None or not remote.has_token:
                continue
            if remote.token != current:
                return remote.token

    async def _wait_for_new_token(self, bad_token: str) -> None:
        """Token yaroqsiz bo'lganda — yangisi kiritilishini kutadi.

        Aynan shu joy botni crash-loop dan saqlaydi: noto'g'ri token bilan
        qayta-qayta urinmaymiz, admin panelda tuzatishini kutamiz.
        """
        logger.info(
            "⏳ Yangi token kutilmoqda — har %.0f soniyada tekshiriladi.",
            settings.CONFIG_POLL_SECONDS,
        )
        while True:
            await asyncio.sleep(settings.CONFIG_POLL_SECONDS)

            remote = await self._config.fetch()
            if remote is not None:
                if remote.has_token and remote.token != bad_token:
                    logger.info(
                        "🔄 Yangi token topildi: %s", mask_secret(remote.token)
                    )
                    return
                continue

            # Backend yo'q — .env dagi zaxira boshqa bo'lsa, o'shani sinaymiz
            env_token = settings.TELEGRAM_BOT_TOKEN.strip()
            if env_token and env_token != bad_token:
                logger.info(
                    "🔄 .env dagi zaxira token sinab ko'riladi: %s",
                    mask_secret(env_token),
                )
                return
