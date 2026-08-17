"""Savdo xodimi (agent) ORM modeli."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class AgentModel(Base, UUIDMixin, TimestampMixin):
    """Savdo xodimi.

    Diqqat: bu `users` dan alohida jadval. Sabab — savdo xodimining
    akkaunti bo'lmasligi ham mumkin (tizim baholarni baribir yozib boradi),
    va bitta agentga bir nechta hisob bog'lanishi mumkin.
    """

    __tablename__ = "agents"

    full_name: Mapped[str] = mapped_column(String(255), index=True)
    region: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # MoyZvonki'dagi xodim identifikatori (integratsiya uchun)
    external_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # ── Arxiv ─────────────────────────────────────────────────
    #
    # ⚠️ `is_active` BILAN ARALASHTIRMANG — ular boshqa savolga javob:
    #
    #   `is_active = false`  → «ishdan bo'shadi». Ro'yxatlarda ko'rinadi,
    #                          guruhlari bo'shatilgan, tarixi joyida.
    #   `archived_at != NULL` → «tizimdan olib tashlandi». Hech qayerda
    #                          ko'rinmaydi, lekin QATOR SAQLANADI.
    #
    # Nega qator saqlanadi: `calls.agent_id` da `ON DELETE CASCADE` bor.
    # Xodim qatori o'chsa, uning barcha qo'ng'iroqlari, transkriptlari
    # va BAHOLARI ham o'chib ketadi — oylar davomida yig'ilgan ish
    # natijasi. Shuning uchun ma'lumoti bor xodim HECH QACHON
    # o'chirilmaydi, faqat arxivga o'tadi: u ekranlardan yo'qoladi,
    # qo'ng'iroqlari esa kimga tegishli ekani bilinib turaveradi.
    #
    # Butunlay o'chirish faqat BO'SH xodimga qo'llanadi — o'shanda
    # yo'qoladigan narsaning o'zi yo'q.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # UI'da avatar rangi — rasm bo'lmasa bosh harflar shu fonda ko'rsatiladi
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")

    # Profil rasmi. Nisbiy yo'l: /media/avatars/<id>.webp
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Telegram ro'yxatdan o'tishi ───────────────────────────
    #
    # Bot guruh a'zosining telefon raqamini KO'RA OLMAYDI (Bot API dagi
    # `User` da `phone_number` maydoni yo'q). Shuning uchun xodim botga
    # shaxsiy chatda o'z kontaktini yuboradi, backend raqamni `phone`
    # bilan solishtiradi va shu yerga `telegram_user_id` ni yozadi.
    # Shundan keyin guruhlar avtomatik biriktiriladi: 1000 ta guruhni
    # qo'lda bog'lash imkonsiz.
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True, index=True
    )
    # Faqat ko'rsatish uchun (@aziz_bonvi). Identifikator EMAS —
    # username istalgan payt o'zgaradi, `telegram_user_id` esa hech qachon.
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrolled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
