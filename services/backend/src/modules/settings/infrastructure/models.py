"""Sozlamalar ORM modeli."""

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class SettingModel(Base, UUIDMixin, TimestampMixin):
    """Kalit-qiymat juftligi.

    Qiymat JSONB'da saqlanadi — turi (string/number/boolean) reyestrda
    belgilanadi, shuning uchun bu yerda universal saqlash yetarli.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)

    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
