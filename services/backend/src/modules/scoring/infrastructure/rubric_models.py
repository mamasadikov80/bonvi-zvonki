"""Rubrika ORM modeli.

Rubrika VERSIYALANADI: o'zgargan rubrika bilan eski ballarni
solishtirib bo'lmaydi, shuning uchun har tahrir yangi versiya yaratadi
va eski baholar o'z versiyasiga bog'liq qoladi.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class RubricModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rubrics"

    # «Faqat bitta faol rubrika» qoidasini BAZANING O'ZI ushlab turadi.
    # Oddiy indeks yetarli emas edi: ikkita so'rov parallel kelsa yoki
    # kimdir SQL bilan qo'lda yozsa, ikkita `is_active = true` qatori
    # qolardi va `RubricService.get_active()` dagi `scalar_one_or_none()`
    # `MultipleResultsFound` bilan BUTUN baholashni to'xtatardi (500).
    # Qisman unikal indeks — faqat `true` qatorlarni qamraydi, `false`
    # tarixiy versiyalar esa istagancha ko'p bo'lishi mumkin.
    __table_args__ = (
        Index(
            "ix_rubrics_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    version: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Faqat bitta rubrika faol bo'ladi — yangi baholar shuni ishlatadi
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # [{ key, label, max, criteria: [{ id, label, points, description }] }]
    blocks: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    # [{ type, label, penalty, description, zeroes_score }]
    red_flags: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    # Adminning qo'lda yozgan qo'shimcha ko'rsatmalari — promptga
    # alohida bo'lim bo'lib tushadi.
    #
    # NEGA RUBRIKA ICHIDA. Uni `app_settings` ga qo'yish oson edi, lekin
    # o'shanda VERSIYALANMASDI: matn o'zgargach eski baholar qanday
    # ko'rsatma bilan qo'yilganini bilib bo'lmasdi va noto'g'ri tahrirni
    # qaytarish yo'li ham bo'lmasdi. Rubrika ichida u `rubric_version`
    # bilan birga yuradi — har baho o'zini qaysi matn baholaganini
    # ko'rsatadi va «Eski versiyaga qaytish» tugmasi matnni ham
    # qaytaradi.
    extra_rules: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
