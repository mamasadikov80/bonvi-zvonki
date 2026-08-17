"""Telegram guruh ORM modeli."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.modules.groups.domain.entities import BotStatus


class TelegramGroupModel(Base, UUIDMixin, TimestampMixin):
    """Mijozlar o'tiradigan Telegram guruhi.

    Bot guruhga qo'shilganda o'zi ro'yxatdan o'tkazadi (`POST /groups/register`),
    keyin admin panelda unga savdo xodimi va hudud biriktiriladi.
    """

    __tablename__ = "telegram_groups"

    # Telegram guruh identifikatori — manfiy son (-100...).
    # `BigInteger`: supergroup id lari 32 bitga sig'maydi.
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))

    # Xodim o'chirilsa guruh yo'qolmasin — faqat bog'lanish uziladi
    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    region: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Telegramdan olingan taxminiy son — javob berish darajasi uchun mo'ljal
    member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Xodim ham, hudud ham to'lgan payt. `None` — guruh hali biriktirilmagan.
    bound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Oxirgi so'rovnoma vaqti — kadans va suppression shu bo'yicha hisoblanadi
    last_survey_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # member | administrator | left | kicked
    bot_status: Mapped[str] = mapped_column(
        String(16), default=BotStatus.MEMBER.value
    )

    # ── Avtomatik biriktirish ─────────────────────────────────

    # "auto" — avtomatika biriktirgan, "manual" — admin qo'lda.
    # ⚠️ `manual` bo'lgan guruhga avtomatika TEGMAYDI. Aks holda admin
    # tuzatgan narsani botning keyingi aylanishi jimgina buzib qo'yardi.
    bound_by: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
