"""Baholash ORM modeli."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class CallScoreModel(Base, UUIDMixin, TimestampMixin):
    """AI tomonidan qo'yilgan baho.

    `blocks` va `red_flags` JSONB — chunki rubrika versiyalari
    o'rtasida struktura o'zgaradi va migratsiya talab qilmasligi kerak.
    """

    __tablename__ = "call_scores"

    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, index=True
    )

    model: Mapped[str] = mapped_column(String(64))
    rubric_version: Mapped[str] = mapped_column(String(16), default="v1")

    overall_score: Mapped[int] = mapped_column(Integer, index=True)

    # {"script": 20, "communication": 18, ...} — TEKIS son, boshqa emas.
    # Analitika razrezi va qo'ng'iroq tafsiloti sahifasi qiymatni son deb
    # o'qiydi; ichma-ich obyekt kelsa ikkalasi ham quladi.
    blocks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Ball ORTIDAGI dalillar — `blocks` tekis qolishi uchun alohida ustun:
    # {"blocks": {"script": {"score": 20, "max": 25, "label": ...,
    #                        "criteria": [{"id": "A1", "evidence": ...}]}},
    #  "meta": {"blocks_total": .., "penalty_total": .., ...}}
    block_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    # [{"type": "shouting", "severity": "high", "timestamp": "07:42", ...}]
    red_flags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # {"type": "order_agreed", "products": [...], "confidence": 0.72}
    outcome_signal: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    coaching_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # [{"code": "low_confidence", "message": "AI ishonchi past (0.52 < 0.70)"}]
    # Bayroqning SABABI — menejer navbatni ochganda nega bu qo'ng'iroq
    # shu yerda ekanini ko'radi. Bo'sh ro'yxat = tekshiruv kerak emas.
    review_reasons: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )

    scored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
