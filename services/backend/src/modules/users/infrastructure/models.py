"""Foydalanuvchi ORM modeli."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.modules.users.domain.entities import Role


class UserModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="user_role", values_callable=lambda e: [i.value for i in e]),
        default=Role.VIEWER,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # SALES roli uchun — foydalanuvchi qaysi savdo xodimiga bog'langan
    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
