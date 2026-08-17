"""Guruhga savdo xodimini AVTOMATIK biriktirish.

MUAMMO
  Har mijoz uchun alohida guruh ochilgan — jami ~1000 ta. Ularni qo'lda
  xodimga biriktirish imkonsiz. Bot guruhdagi savdo xodimini o'zi
  topishi kerak.

  Telefon raqami orqali topib bo'lmaydi: bot API guruh a'zosining
  raqamini KO'RSATMAYDI (qarang: `handlers/enroll.py`). Shuning uchun
  xodim bir marta shaxsiy chatda ro'yxatdan o'tadi va uning
  `telegram_user_id` si backend'da saqlanadi. Undan keyin guruhni
  aniqlash — guruhdagi id larni backend'ga aytishdan iborat.

UCH YO'L, ARZONIDAN QIMMATIGA
  1. Botni kim qo'shgan   — `my_chat_member.from_user` (bepul, o'zi keladi)
  2. Guruh adminlari      — `getChatAdministrators` (bitta API so'rovi)
  3. Guruhda yozganlar    — oddiy xabar egasi (bepul, lekin ko'p keladi)

  Birinchi mos kelgani yetadi. Amalda uchinchisi eng muhim: 1000 ta
  guruhda xodim ko'pincha admin ham emas, botni ham u qo'shmagan.

KESHLASH QOIDASI — nega bu shart
  Uchinchi yo'l HAR XABARDA ishga tushadi. Gavjum guruh bir kunda
  yuzlab xabar beradi, 1000 ta guruh esa — o'n minglab. Ularning
  har birida backend'ga so'rov yuborish ma'nosiz: javob bir xil
  bo'ladi. Shuning uchun HAR GURUH uchun Redis'da bitta to'plam
  saqlanadi:

      zvonki:bot:autobind:{chat_id}   (Redis SET)
        "done"        — guruh hal bo'ldi (biriktirildi yoki admin qo'lda
                        biriktirgan) → bu guruh uchun boshqa so'rov yo'q
        "admins"      — adminlar ro'yxati allaqachon so'ralgan
        "c:<digest>"  — shu nomzod allaqachon backend'ga aytilgan

  Qoida bitta jumlada: **backend'ga faqat SHU GURUHDA HALI
  AYTILMAGAN nomzod uchun murojaat qilinadi.** Bir odam ming marta
  yozsa ham bitta so'rov ketadi; guruh biriktirilgach umuman ketmaydi.

  Belgilar MUDDATLI:
    • hal bo'lgan guruh — 7 kun (guruh yoki xodim o'zgarsa qayta ko'riladi)
    • hal bo'lmagan     — 6 soat (xodim keyinroq ro'yxatdan o'tishi mumkin)
    • backend javob bermagan — 15 daqiqa (tez qayta urinish uchun)

  Nomzod XOM ID bilan emas, qisqartirilgan hash bilan eslab qolinadi.
  Keshga faqat «bu nomzodni aytdikmi?» degan savol beriladi, ya'ni
  xom id ni saqlashning hojati yo'q — saqlanmasa esa Redis dump'iga
  ham, kesh ko'rgan odamga ham hech narsa oshkor bo'lmaydi.

NIMANI BOT HAL QILMAYDI
  Guruh «ishchi» yoki «keraksiz» ekanini bot ANIQLAMAYDI. A'zolar soni
  bilan taxmin qilish noto'g'ri: bir necha kishi bo'lgan guruhda ham
  mijoz bo'lmasligi mumkin. Bot faqat `member_count` ni panelda
  ko'rinsin deb yuboradi, xulosani admin hudud biriktirish orqali
  chiqaradi.
"""

import hashlib
import logging
from dataclasses import dataclass

from aiogram import Bot
from redis.asyncio import Redis

from src.core.config import settings
from src.services.chat_info import administrator_ids, member_count_of
from src.services.internal_api import AutobindResult, InternalApiClient

logger = logging.getLogger(__name__)

KEY_TEMPLATE = "zvonki:bot:autobind:{chat_id}"

DONE = "done"
ADMINS = "admins"

# Bitta guruh uchun eslab qolinadigan nomzodlar chegarasi. Katta guruhda
# yozganlar ko'p bo'lishi mumkin — to'plam cheksiz o'smasin, va shu
# chegaradan keyin guruh o'sha oyna davomida tinch qoldiriladi.
MAX_CANDIDATES = 12


def _mark(chat_id: int, user_id: int) -> str:
    """Nomzod belgisi — xom id emas, qisqartirilgan hash.

    Guruh id si ham hash ichida: bir odam turli guruhlarda turli
    belgiga ega bo'ladi, ya'ni kesh ko'rgan odam «shu odam mana bu
    guruhlarda bor» degan xulosa ham chiqara olmaydi.
    """
    raw = f"{chat_id}:{user_id}".encode()
    return "c:" + hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class _Ttl:
    """Belgilar qancha yashaydi (soniya)."""

    done: int
    pending: int
    retry: int


class AutobindCache:
    """`chat_id → aytilgan nomzodlar` (Redis, `registry.py` naqshida).

    Redis yiqilsa bot to'xtamaydi: jarayon ichidagi oddiy `dict`
    zaxira sifatida ishlaydi. Zaxira faqat Redis javob bermaganda
    O'QILADI, lekin har doim YOZILADI — shunda uzilish paytida ham
    guruh backend'ni bombardimon qilmaydi.
    """

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis or Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        self._ttl = _Ttl(
            done=settings.AUTOBIND_DONE_TTL_DAYS * 24 * 3600,
            pending=int(settings.AUTOBIND_TTL_HOURS * 3600),
            retry=int(settings.AUTOBIND_RETRY_MINUTES * 60),
        )
        self._fallback: dict[int, set[str]] = {}

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception as exc:  # yopilishdagi xato hech narsani buzmasin
            logger.debug("autobind keshi yopilmadi: %s", exc)

    async def marks(self, chat_id: int) -> set[str]:
        """Shu guruh uchun allaqachon qo'yilgan belgilar."""
        try:
            members = await self._redis.smembers(
                KEY_TEMPLATE.format(chat_id=chat_id)
            )
        except Exception as exc:
            logger.warning("⚠️  Autobind keshi o'qilmadi (Redis): %s", exc)
            return set(self._fallback.get(chat_id, set()))
        return set(members or ())

    async def remember(
        self, chat_id: int, marks: set[str], *, done: bool, answered: bool
    ) -> None:
        """Belgilarni qo'yadi va to'plam muddatini yangilaydi.

        `answered=False` (backend javob bermadi) — belgi baribir
        qo'yiladi, aks holda gavjum guruhdagi har xabar yiqilgan
        backend'ga urinardi. Faqat muddati qisqa: uzilish tugagach
        guruh tez orada qayta ko'riladi.
        """
        if not marks and not done:
            return
        if done:
            marks = marks | {DONE}

        self._fallback.setdefault(chat_id, set()).update(marks)

        ttl = self._ttl.done if done else (
            self._ttl.pending if answered else self._ttl.retry
        )
        key = KEY_TEMPLATE.format(chat_id=chat_id)
        try:
            pipe = self._redis.pipeline()
            pipe.sadd(key, *marks)
            pipe.expire(key, ttl)
            await pipe.execute()
        except Exception as exc:
            logger.warning("⚠️  Autobind keshiga yozilmadi (Redis): %s", exc)


class AgentBinder:
    """Guruhdagi savdo xodimini topib backend'ga aytuvchi.

    Handler'lar bu sinfning YAGONA metodini chaqiradi — `discover()`.
    Qaysi yo'l bilan kelgani (bot qo'shildi / xabar keldi) argumentlar
    orqali bilinadi, tartib esa shu yerda, bitta joyda saqlanadi.
    """

    def __init__(self, internal: InternalApiClient, cache: AutobindCache) -> None:
        self._internal = internal
        self._cache = cache

    async def discover(
        self,
        bot: Bot,
        chat_id: int,
        title: str | None,
        *,
        bot_status: str = "member",
        adder_id: int | None = None,
        sender_id: int | None = None,
        with_admins: bool = True,
    ) -> None:
        """Uch yo'lni arzonidan boshlab sinaydi, birinchi mos kelganda to'xtaydi."""
        marks = await self._cache.marks(chat_id)
        if DONE in marks:
            # Guruh biriktirilgan yoki admin qo'lda biriktirgan — tegmaymiz
            return

        fresh: set[str] = set()
        bound = False
        answered = False
        # A'zolar soni FAQAT backend'ga so'rov ketadigan bo'lsa olinadi:
        # aks holda har xabarda ortiqcha Telegram so'rovi ketardi.
        member_count: int | None = None
        counted = False

        async def attempt(user_ids: list[int], source: str) -> bool:
            nonlocal answered, member_count, counted

            wanted: list[int] = []
            seen: set[str] = set()
            for uid in user_ids:
                mark = _mark(chat_id, uid)
                if mark in marks or mark in fresh or mark in seen:
                    continue
                seen.add(mark)
                wanted.append(uid)

            if not wanted:
                return False
            if len(marks) + len(fresh) >= MAX_CANDIDATES:
                logger.debug(
                    "guruh %s: nomzodlar chegarasi to'ldi, oyna tugashini kutamiz",
                    chat_id,
                )
                return False

            if not counted:
                member_count = await member_count_of(bot, chat_id)
                counted = True

            result = await self._internal.autobind_group(
                chat_id=chat_id,
                title=(title or "").strip() or "Nomsiz guruh",
                member_count=member_count,
                bot_status=bot_status,
                candidate_user_ids=wanted,
            )
            fresh.update(seen)

            if result is None:
                logger.debug("guruh %s: biriktirish javobsiz qoldi", chat_id)
                return False

            answered = True
            self._log(chat_id, source, len(wanted), result)
            # `manual` — admin qo'lda biriktirgan: avtomatika tegmaydi
            return result.bound or result.reason == "manual"

        try:
            # ── 1. Botni kim qo'shgan ─────────────────────────────
            if adder_id is not None:
                bound = await attempt([adder_id], "qo'shgan")

            # ── 3. Guruhda yozgan odam ────────────────────────────
            # Tartibda uchinchi bo'lsa ham, adminlar ro'yxatidan OLDIN
            # sinaladi: xabar egasi bepul keldi, `getChatAdministrators`
            # esa alohida API so'rovi. «Arzonidan qimmatiga» qoidasi
            # aynan shuni anglatadi.
            if not bound and sender_id is not None:
                bound = await attempt([sender_id], "xabar")

            # ── 2. Guruh adminlari ────────────────────────────────
            # Har guruh uchun BIR MARTA (`ADMINS` belgisi): bu API
            # so'rovi, adminlar ro'yxati esa kamdan-kam o'zgaradi.
            # Botni ancha oldin qo'shilgan guruhlarda `my_chat_member`
            # hech qachon kelmaydi — o'sha guruhlar uchun bu yo'l
            # birinchi xabar bilan birga ochiladi.
            if not bound and with_admins and ADMINS not in marks:
                fresh.add(ADMINS)
                admins = await administrator_ids(bot, chat_id)
                if admins:
                    bound = await attempt(admins, "admin")
        finally:
            await self._cache.remember(
                chat_id, fresh, done=bound, answered=answered
            )

    @staticmethod
    def _log(chat_id: int, source: str, count: int, result: AutobindResult) -> None:
        """Natija logi.

        Logda XOM TELEGRAM ID YO'Q — na nomzodniki, na xodimniki.
        Faqat guruh, nechta nomzod aytilgani va backend qarori.
        """
        if result.bound:
            logger.info(
                "🔗 Guruh biriktirildi · guruh=%s · yo'l=%s · xodim=%s · hudud=%s",
                chat_id,
                source,
                result.agent_name or "—",
                result.region or "— (admin tayinlaydi)",
            )
            return
        logger.info(
            "🔍 Guruh biriktirilmadi · guruh=%s · yo'l=%s · nomzod=%s · sabab=%s",
            chat_id,
            source,
            count,
            result.reason or "—",
        )
