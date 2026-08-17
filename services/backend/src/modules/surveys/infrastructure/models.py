"""So'rovnoma ORM modellari."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.modules.surveys.domain.entities import (
    Resolution,
    SurveyChannel,
    SurveyStatus,
)


class SurveyModel(Base, UUIDMixin, TimestampMixin):
    """Bitta so'rovnoma chaqirig'i.

    Ikki xil bo'ladi:
      • eski oqim — client × agent × davr (`client_id` to'la, `group_id` bo'sh)
      • guruh oqimi — guruh × agent × davr (`group_id` to'la, `client_id` bo'sh)

    Guruh oqimida bitta so'rovnomaga o'nlab odam javob beradi, shuning uchun
    `client_id` NULL bo'la oladi — guruhda kim o'tirganini bilmaymiz va
    bilishimiz ham kerak emas.
    """

    __tablename__ = "surveys"

    # Guruh so'rovnomasida client yo'q — shuning uchun nullable
    client_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )

    # ── Guruh oqimi ───────────────────────────────────────────
    group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("telegram_groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Guruhdagi xabar id — bot javob sonini yangilash uchun tahrirlaydi
    chat_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Keshlangan javoblar soni: xabar matnini har safar SANAB o'tirmaslik uchun
    response_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    # ── Xabarni guruhdan olib tashlash ────────────────────────
    #
    # Muddat tugagach bot `chat_message_id` bo'yicha AYNAN shu xabarni
    # o'chiradi. Bu ustun — «bu xabar bilan ish tugadi» belgisi: to'la
    # bo'lsa xabar boshqa navbatga tushmaydi va hisoblagichi ham
    # yangilanmaydi (o'chirilgan xabarni tahrirlab bo'lmaydi).
    #
    # Muvaffaqiyatsiz urinishda ham to'ldiriladi (masalan Telegram'ning
    # 48 soatlik chegarasi o'tib ketgan bo'lsa). Aks holda navbat
    # o'chirib bo'lmaydigan xabarlar bilan cheksiz to'lib borardi.
    # Nima bo'lganini log yozadi.
    message_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Hudud NUSXASI (arxiv uchun) ───────────────────────────
    #
    # ⚠️ Bu ATAYLAB takrorlangan ma'lumot. Hisobot hududni ilgari
    # `coalesce(telegram_groups.region, agents.region)` bilan, ya'ni
    # TIRIK qiymatdan hisoblardi. Natijada guruh boshqa hududga
    # ko'chirilsa yoki hudud arxivlanib guruhdan uzilsa, o'tgan
    # oylarning bahosi hisobotdan JIMGINA yo'qolardi — o'lchov
    # o'zgargani uchun tarix ham o'zgarardi.
    #
    # Endi so'rovnoma yaratilgan LAHZADAGI hudud shu yerga yoziladi va
    # keyin hech qachon o'zgarmaydi. Xuddi buyurtmaga narx yozib
    # qo'yilgani kabi: mahsulot narxi keyin oshsa ham eski buyurtma
    # o'z narxini saqlaydi.
    #
    # `NULL` — bu ustun paydo bo'lishidan oldingi eski yozuv; o'sha
    # holatda hisobot avvalgidek tirik qiymatga qaytadi.
    region: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    # Deep-link tokeni: t.me/<bot>?start=srv_<token>
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    channel: Mapped[SurveyChannel] = mapped_column(
        SAEnum(
            SurveyChannel,
            name="survey_channel",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=SurveyChannel.TELEGRAM_GROUP,
    )
    status: Mapped[SurveyStatus] = mapped_column(
        SAEnum(
            SurveyStatus,
            name="survey_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=SurveyStatus.PENDING,
        index=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SurveyResponseModel(Base, UUIDMixin, TimestampMixin):
    """Client javobi. Anonim — guruhda hech kim ko'rmaydi."""

    __tablename__ = "survey_responses"

    # ⚠️ `survey_id` da yakka UNIQUE YO'Q. Ilgari bor edi (bitta so'rovnoma =
    # bitta javob), lekin guruh oqimida bitta so'rovnomaga 30 ta mijoz javob
    # beradi. O'rniga birgalikdagi unique — pastdagi `__table_args__`.
    survey_id: Mapped[UUID] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), index=True
    )

    # ── Anonim dedup ──────────────────────────────────────────
    #
    # `sha256(survey.token + ":" + telegram_user_id)` — BOT hisoblaydi.
    # Backend Telegram identifikatorini umuman ko'rmaydi, shuning uchun uni
    # saqlab qo'yish ehtimoli ham yo'q. Har so'rovnomaning tokeni har xil,
    # demak bir odamning turli so'rovnomalardagi hash'lari bog'lanmaydi —
    # "shu odam o'tgan safar nima deb baholagan edi" degan savolga javob yo'q.
    respondent_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    csat: Mapped[int] = mapped_column(SmallInteger)  # 1..5
    resolution: Mapped[Resolution | None] = mapped_column(
        SAEnum(
            Resolution,
            name="survey_resolution",
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Belgilangan red flag kalitlari — `domain.entities.RED_FLAGS` dan
    red_flags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )

    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_time_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        # Bir odam bitta so'rovnomaga bir marta. `respondent_hash` NULL
        # bo'lgan eski (client) javoblarga ta'sir qilmaydi — PostgreSQL da
        # NULL lar unique tekshiruvida teng hisoblanmaydi. Eski oqimning
        # "bitta javob" qoidasi servis qatlamida tekshiriladi.
        UniqueConstraint(
            "survey_id", "respondent_hash", name="uq_response_per_respondent"
        ),
    )
