"""Bot sozlamalari.

Token ustuvorligi (backend'dagi `SettingsService` bilan bir xil mantiq):

    baza (dashboard → Sozlamalar)  >  .env  >  bo'sh

Ya'ni bu yerdagi `TELEGRAM_BOT_TOKEN` — faqat ZAXIRA. Asosiy manba —
backend'ning `GET /settings/bot-config` endpointi (qarang: `services/config_client.py`).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Zaxira qiymatlar (backend javob bermasa ishlatiladi) ──
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""

    API_BASE_URL: str = "http://backend:8000"
    REDIS_URL: str = "redis://redis:6379/1"

    # ── Backend bilan ichki aloqa ─────────────────────────────
    # Bot foydalanuvchi emas — JWT o'rniga umumiy maxfiy kalit.
    INTERNAL_API_TOKEN: str = ""

    # Backend ko'tarilishini kutish muddati (soniya). Shu vaqt ichida
    # javob bo'lmasa — .env dagi zaxira tokenga o'tamiz.
    CONFIG_STARTUP_TIMEOUT: float = 30.0
    # Token o'zgarganini payqash uchun davriy tekshiruv oralig'i.
    CONFIG_POLL_SECONDS: float = 30.0

    # ── Guruh so'rovnomalari ──────────────────────────────────
    # Navbatdagi so'rovnomalarni tekshirish oralig'i (soniya).
    PENDING_POLL_SECONDS: float = 60.0
    # Guruh xabaridagi hisoblagichni yangilash oralig'i (soniya).
    # Telegram `editMessageText` ni cheklaydi, shuning uchun javoblar
    # shu oraliqda bitta tahrirga siqiladi — qarang: `services/throttle.py`.
    COUNTER_EDIT_SECONDS: float = 5.0
    # Red flag ro'yxati keshi (soniya). Ro'yxat backend'da o'zgarsa
    # shu muddatdan keyin o'zi yangilanadi — bot qayta yig'ilmaydi.
    RED_FLAGS_TTL_SECONDS: float = 600.0
    # Bot yuborgan guruh so'rovnomasi belgisi Redis'da qancha yashaydi (kun).
    SURVEY_MARK_TTL_DAYS: int = 30

    # ── Ommaviy yuborish tezligi ──────────────────────────────
    # Telegram global chegarasi ~30 xabar/s. 20 — ataylab pastroq:
    # hisoblagich tahrirlari va boshqa so'rovlar ham shu chegaraga
    # kiradi, chetiga tegib turish esa 429 ga olib keladi va butun
    # navbat to'xtab qoladi. Qarang: `services/ratelimit.py`.
    SEND_RATE_PER_SECOND: float = 20.0
    # Loglarda «qayerdaman» ko'rinib tursin — har necha xabarda bir marta.
    SEND_PROGRESS_EVERY: int = 25

    # ── Avtomatik biriktirish keshi ───────────────────────────
    # Hal bo'lmagan guruh belgisi (soat): xodim keyinroq ro'yxatdan
    # o'tishi mumkin, shuning uchun oyna tugagach guruh qayta ko'riladi.
    AUTOBIND_TTL_HOURS: float = 6.0
    # Biriktirilgan guruh belgisi (kun) — bunga deyarli qaytilmaydi.
    AUTOBIND_DONE_TTL_DAYS: int = 7
    # Backend javob bermagan holat (daqiqa) — tez qayta urinish uchun.
    AUTOBIND_RETRY_MINUTES: float = 15.0

    DEBUG: bool = True

    @property
    def is_configured(self) -> bool:
        """.env da zaxira token bormi?"""
        return bool(self.TELEGRAM_BOT_TOKEN.strip())


@lru_cache
def get_settings() -> BotSettings:
    return BotSettings()


settings = get_settings()


def mask_secret(value: str | None) -> str:
    """Logga yozish uchun xavfsiz ko'rinish: faqat oxirgi 4 belgi.

    Token loglarga TO'LIQ tushmasligi kerak — loglar ko'pincha
    boshqa joyga uzatiladi va uzoq saqlanadi.
    """
    value = (value or "").strip()
    if not value:
        return "—"
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"
