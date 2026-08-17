"""Bot o'zi yuborgan guruh so'rovnomalari reyestri (Redis).

NEGA KERAK?
  Deep-link ikkala oqim uchun bir xil: `?start=srv_<token>`. Shaxsiy
  chatda `/start` kelganda bot bilishi kerak — bu ESKI, client uchun
  qo'yilgan so'rovnomami (u yerda ball ham shaxsiy chatda qo'yiladi),
  yoki YANGI guruh so'rovnomasimi (ball allaqachon guruhda qo'yilgan,
  bu yerda faqat izoh va sabab so'raladi).

  Eng ishonchli manba — botning o'zi: guruh so'rovnomasini guruhga
  AYNAN BOT yuboradi. Yuborayotganda tokenni shu reyestrga belgilab
  qo'yadi va keyin `/start` kelganda bir so'rovsiz taniydi.

  Redis ishlatiladi (RAM emas), chunki bot token almashganda yoki
  konteyner qayta ishga tushganda belgi yo'qolmasligi kerak.

  Belgi bilan birga guruh xabarining manzili ham saqlanadi — kelajakda
  "guruhga qayting" xabarida ishlatish uchun.
"""

import logging

from redis.asyncio import Redis

from src.core.config import settings

logger = logging.getLogger(__name__)

KEY_TEMPLATE = "zvonki:bot:group-survey:{token}"


class GroupSurveyRegistry:
    """`token → (chat_id, message_id)` — bot yuborgan guruh so'rovnomalari."""

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis or Redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        self._ttl = settings.SURVEY_MARK_TTL_DAYS * 24 * 3600
        # Redis yo'q bo'lsa ham bot ishlashda davom etsin — zaxira
        # sifatida jarayon ichidagi oddiy dict.
        self._fallback: dict[str, tuple[int, int, bool]] = {}

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception as exc:  # yopilishdagi xato hech narsani buzmasin
            logger.debug("registry yopilmadi: %s", exc)

    async def remember(
        self,
        token: str,
        chat_id: int,
        message_id: int,
        miniapp: bool = False,
    ) -> None:
        """So'rovnoma guruhga yuborilgani belgilanadi.

        `miniapp` — xabar Mini App havolasi bilan ketdimi. Hisoblagichni
        yangilashda shu shakl qayta ishlatiladi.
        """
        self._fallback[token] = (chat_id, message_id, miniapp)
        try:
            await self._redis.set(
                KEY_TEMPLATE.format(token=token),
                f"{chat_id}:{message_id}:{'mini' if miniapp else 'legacy'}",
                ex=self._ttl,
            )
        except Exception as exc:
            logger.warning("⚠️  Reyestrga yozilmadi (Redis): %s", exc)

    async def lookup(self, token: str) -> tuple[int, int, bool] | None:
        """Guruh so'rovnomasimi? Ha bo'lsa (chat_id, message_id, miniapp)."""
        cached = self._fallback.get(token)
        if cached is not None:
            return cached
        try:
            raw = await self._redis.get(KEY_TEMPLATE.format(token=token))
        except Exception as exc:
            logger.warning("⚠️  Reyestr o'qilmadi (Redis): %s", exc)
            return None
        if not raw:
            return None
        try:
            # Eski yozuvlarda shakl yo'q — ular tugmali xabarlar
            parts = raw.split(":")
            chat_id, message_id = int(parts[0]), int(parts[1])
            miniapp = len(parts) > 2 and parts[2] == "mini"
            return chat_id, message_id, miniapp
        except (ValueError, IndexError):
            return None

    async def is_group_survey(self, token: str) -> bool:
        return await self.lookup(token) is not None
