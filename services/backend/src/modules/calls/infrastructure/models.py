"""Qo'ng'iroq ORM modeli."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.modules.calls.domain.entities import CallDirection, CallStatus


class CallModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "calls"

    external_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── MoyZvonki'dagi mijoz (NUSXA) ──────────────────────────
    #
    # `client_id` faqat raqam bizning `clients` katalogimizda topilganda
    # to'ladi — amalda bu kamdan-kam. Ilgari qolgan hamma qo'ng'iroqda
    # mijoz ustuni «—» bo'lib turardi, holbuki MoyZvonki nomni ham,
    # raqamni ham bergan edi.
    #
    # Bu maydonlar ATAYLAB `clients` ga yozilmaydi: u yerda hudud
    # majburiy va katalog so'rovnoma yuborish uchun ishlatiladi —
    # har bir notanish raqamdan «mijoz» yasash uni ifloslantirardi.
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )

    direction: Mapped[CallDirection] = mapped_column(
        SAEnum(
            CallDirection,
            name="call_direction",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=CallDirection.OUTBOUND,
    )
    status: Mapped[CallStatus] = mapped_column(
        SAEnum(
            CallStatus,
            name="call_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=CallStatus.PENDING,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)

    # ── Javob berilganmi ──────────────────────────────────────
    #
    # MoyZvonki'dagi `answered` — TELEFONIYA FAKTI, bizning ishlov
    # holatimiz emas (u `status` da). Ikkisini aralashtirmaslik kerak:
    # `status = SKIPPED` «baholanmadi» degani, `answered = false` esa
    # «gaplashilmagan» degani va bu butunlay boshqa ma'no.
    #
    # NEGA ALOHIDA USTUN KERAK. Javobsiz qo'ng'iroqda audio HECH QACHON
    # bo'lmaydi (o'lchandi: 2030 javobsizdan 0 tasida yozuv bor), ya'ni
    # «audiosi yo'q» degan belgi javobsizlikni ANIQLAMAYDI — javob
    # berilgan qo'ng'iroqlarning ham bir qismida yozuv yo'q (260/3847).
    # Faollik hisobotining butun mantig'i shu farqqa tayanadi.
    #
    # `NULL` — bu ustun paydo bo'lishidan OLDIN yozilgan qatorlar.
    # Ularni `true` deb to'ldirish yolg'on bo'lardi: audiosiz eski
    # qatorlar javobsiz ham, yozuvsiz javobli ham bo'lishi mumkin.
    # Hisobotlar `NULL` ni sanamaydi; qayta sinxronizatsiya to'ldiradi.
    answered: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, index=True
    )

    # ── Qo'ng'iroq turi ───────────────────────────────────────
    #
    # Baholash FAQAT `sales` turiga qo'llanadi. Ish telefonlari orqali
    # xodimlar sklad, buxgalteriya va hamkasblar bilan ham gaplashadi;
    # savdo rubrikasi bunday suhbatga nol beradi va xodimning
    # o'rtachasini asossiz pasaytiradi. Haqiqiy ma'lumotda o'lchandi:
    # baholangan qo'ng'iroqlarning 20% i ichki suhbat edi.
    #
    # `NULL` — hali tasniflanmagan (eski qatorlar yoki transkripti yo'q).
    call_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )
    call_type_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    """AI nega shu turni tanlagani — bitta jumla.

    Qo'lda tuzatish yo'q, shuning uchun qaror hech bo'lmasa
    TUSHUNTIRILGAN bo'lishi kerak: menejer sababni o'qib, xato
    bo'lsa «Qayta baholash» bilan qaytadan yuboradi."""

    call_type_confidence: Mapped[float | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )

    audio_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
