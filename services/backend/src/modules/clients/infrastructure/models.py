"""Client ORM modeli."""

from uuid import UUID

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class ClientModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), index=True)
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Telegram — so'rovnoma yuborish uchun
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True
    )
    telegram_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Biriktirilgan savdo xodimi
    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Baholash bias'i — client qat'iyligini normallashtirish uchun
    # (2.6-bo'lim: adjusted = raw − client_bias)
    bias: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
