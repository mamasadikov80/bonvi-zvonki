"""Quvur holati — har qo'ng'iroq uchun bitta qator.

Nega alohida jadval, `calls` ga ustun emas:
`calls` boshqa modulniki va uni sinxronizatsiya (`moizvonki.ingest`)
yozadi. Qayta ishlash tafsilotlari (necha marta urinildi, qaysi model,
qanday xato) — quvurning ishi. Jadval ajratilgani `calls` ni ham
tozalab turadi, ham FK `ON DELETE CASCADE` bilan qo'ng'iroq o'chsa
holat ham o'chadi.

⚠️ Bu yerda ham audio YO'Q. Faqat necha bayt oqib o'tgani — o'lchov.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class CallPipelineStateModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "call_pipeline_state"

    call_id: Mapped[UUID] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, index=True
    )

    #: queued | transcribing | scoring | completed | failed
    stage: Mapped[str] = mapped_column(String(16), default="queued", index=True)

    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    #: Pul turgan chaqiruvlar — takroriy yurishda o'smasligi kerak
    asr_calls: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    llm_calls: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    transcribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # ── Xatoni KO'RSATISH uchun ───────────────────────────────
    # Bo'sh baho va sababsiz qo'ng'iroq — tuzatib bo'lmaydigan holat.
    # Admin «ASR kaliti noto'g'ri» ni ko'rishi kerak.
    error_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── O'lchovlar ────────────────────────────────────────────
    asr_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    asr_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    audio_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transcript_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
