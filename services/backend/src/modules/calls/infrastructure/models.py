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

    # ── Bizning liniyamiz (MoyZvonki `src_number`) ────────────
    #
    # Xodim QAYSI o'z raqamimizdan gaplashgani. Bu ustun ikki ish
    # qiladi va ikkinchisi muhimroq:
    #
    #   1. qo'ng'iroq qaysi SIM orqali ketganini ko'rsatadi;
    #   2. KOMPANIYA LINIYALARI RO'YXATINI o'zi to'ldiradi — barcha
    #      qatorlardagi turli qiymatlar yig'indisi aynan «bizning
    #      raqamlarimiz» degani. Suhbatdoshning raqami shu ro'yxatda
    #      bo'lsa, demak ikkala tomon ham xodim: `call_type = internal`.
    #
    # Ya'ni tur aniqlash uchun na LLM, na qo'lda kiritilgan ro'yxat
    # kerak — yangi xodim ishlay boshlashi bilan raqami o'zi tushadi.
    agent_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── Qo'ng'iroq turi ───────────────────────────────────────
    #
    # Ikkita qiymat bor: `sales` va `internal`.
    #
    # `internal` — suhbatdoshning raqami kompaniya liniyalari ro'yxatida
    # (yuqoridagi `agent_number` dan yig'iladi) yoki ATS ichki raqami.
    # Bunday suhbat TRANSKRIPT olinadi, lekin savdo rubrikasi bilan
    # baholanmaydi: hamkasb bilan gaplashgan xodimga «ehtiyojni
    # aniqladingmi» deb ball qo'yish ma'nosiz.
    #
    # `sales` — qolgan hammasi. Suhbat tashqariga chiqqan, ya'ni
    # kompaniyani mijoz oldida ifodalaydi va baholanadi.
    #
    # ⚠️ Ilgari bu ustunda yana `service`, `personal`, `unclear` bor edi
    # va ularni AI transkript MAZMUNIGA qarab qo'yardi. U yanglishardi:
    # eski mijoz ham «qoldiq qancha, narx qanaqa» deb qisqa gaplashadi
    # va bu hamkasb suhbatidan farq qilmaydi. O'lchandi — tasniflangan
    # 98 qo'ng'iroqdan 82 tasi «ichki», savdo esa 9 ta bo'lib chiqqan.
    #
    # `NULL` — hali aniqlanmagan (yangi qator yoki quvur yurmagan).
    call_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )
    call_type_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    """Qaror qanday chiqqani — bitta jumla, raqam bilan.

    Qo'lda tuzatish yo'q, shuning uchun qaror hech bo'lmasa
    TUSHUNTIRILGAN bo'lishi kerak: menejer sababni o'qib, raqam
    noto'g'ri ro'yxatga tushgan bo'lsa uni sozlamada tuzatadi."""

    call_type_confidence: Mapped[float | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    """Tur raqam bo'yicha aniqlanadi, ya'ni taxmin yo'q — qiymat 1.00.

    Ustun SAQLANIB QOLDI: eski qatorlarda AI qo'ygan qiymat bor va uni
    o'chirish tarixni yo'qotardi."""

    audio_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
