"""Ilova sozlamalari — muhit o'zgaruvchilaridan o'qiladi.

AI provayderlari uchun bu yerdagi qiymatlar FALLBACK hisoblanadi:
ish vaqtida `modules/settings` bazadagi qiymatni ustun qo'yadi.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Umumiy ────────────────────────────────────────────────
    APP_NAME: str = "Bonvi Sales Analytics"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-change-me"

    # ── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:5180",
        "http://127.0.0.1:5180",
    ]

    # ── Panel manzili (tashqi xabarlardagi havola uchun) ──────
    #
    # Backend odatda o'z manzilini bilmaydi — brauzer unga o'zi
    # murojaat qiladi. Lekin Telegram xabaridagi «Panelda ochish»
    # havolasini kimdir yozib berishi kerak.
    #
    # Bo'sh qoldirilsa havola xabarga umuman QO'SHILMAYDI. Bu ataylab:
    # ishlamaydigan `http://localhost:5180` havolasi rahbar telefonida
    # xatolik sahifasini ochardi va butun xabarga ishonchni tushirardi.
    PUBLIC_WEB_URL: str = ""

    # ── Ma'lumotlar bazasi ────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://zvonki:zvonki_dev_password@postgres:5432/zvonki"
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Auth ──────────────────────────────────────────────────
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Ichki xizmatlar (bot ↔ backend) ───────────────────────
    # Bot'ning foydalanuvchi hisobi yo'q — JWT o'rniga umumiy maxfiy
    # kalit. Bo'sh qolsa ichki endpointlar butunlay yopiladi.
    INTERNAL_API_TOKEN: str = ""

    # ── Seed ──────────────────────────────────────────────────
    FIRST_ADMIN_EMAIL: str = "admin@zvonki.uz"
    FIRST_ADMIN_PASSWORD: str = "admin12345"
    SEED_DEMO_DATA: bool = True

    # ── AI ────────────────────────────────────────────────────
    #
    # ⚠️ BU YERDA AI MAYDONLARI YO'Q — ataylab.
    #
    # Provayder, model va kalitlar FAQAT admin panelda (bazada)
    # turadi. Ilgari ular shu yerda ham bor edi va sozlamalar
    # ustuvorligi «baza > .env > standart» bo'lgani uchun admin
    # qiymatni o'chirsa tizim jimgina `.env` dagi eskisiga qaytardi:
    # ekranda «Gemini» ko'rinar, quvur esa boshqa provayderda
    # ishlayverardi. Yagona haqiqat manbai — Sozlamalar sahifasi.

    # ── Telegram ──────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""

    # ── MoyZvonki ─────────────────────────────────────────────
    MOIZVONKI_DOMAIN: str = ""
    MOIZVONKI_USER: str = ""
    MOIZVONKI_API_KEY: str = ""

    # ── Eskiz SMS ─────────────────────────────────────────────
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""

    # ── Storage ───────────────────────────────────────────────
    STORAGE_PROVIDER: str = "minio"
    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = "zvonki-audio"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
