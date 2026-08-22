"""Savdo nazorati — ORM modellari (shartnomaning 3-bo'limi).

To'rt jadval:
  · `sale_partners` — SAP kontragentlar katalogi (kod → nom, telefon);
  · `sales`         — operatsiyalar registri (savdo, to'lov, qaytarish…);
  · `sale_reviews`  — rahbarning qarori (bazadagi YAGONA subyektiv narsa);
  · `sale_branches` — SAP filiali → bizning xodim.

⚠️ QOIDA NATIJASI («shubhali savdo») HECH QAYERDA SAQLANMAYDI. U har
safar qaytadan hisoblanadi: qo'ng'iroq savdodan KEYIN sinxronlanishi
mumkin va o'shanda bazaga yozib qo'yilgan «shubhali» belgisi yolg'onga
aylanardi — hech kim uni qayta hisoblashni eslamas edi.

⚠️ Yangi model `src/core/models.py` ga IMPORT QILINISHI SHART, aks holda
`bootstrap.py` dagi `create_all` bu jadvallarni ko'rmaydi va xato
faqat birinchi yozuvda — testda emas, ishlatuvchida — chiqadi.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class SalePartnerModel(Base, UUIDMixin, TimestampMixin):
    """Kontragent — SAP dagi `Код БП` bo'yicha yagona qator.

    Manba ikkita: asosiysi kontragentlar katalogi (wb3), qo'shimchasi
    balans hisoboti (wb1/wb2) — undan FAQAT yetishmagan telefon
    olinadi.

    Bu jadvalning butun ma'nosi — `phone_key`. Savdo faylida telefon
    YO'Q, ya'ni savdoni qo'ng'iroqlar bilan bog'lashning yagona yo'li
    shu: savdo → mijoz kodi → katalog → telefon → `calls`.
    """

    __tablename__ = "sale_partners"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    """`К02711` — SAP kodi. Idempotentlik kaliti: qayta yuklashda
    aynan shu ustun bo'yicha upsert bo'ladi."""

    name: Mapped[str] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    """`Клиенты`, `Поставщики импорт`… Nazorat FAQAT `Клиенты` ga
    qo'llanadi — yetkazib beruvchi bilan savdo qo'ng'irog'i bo'lmaydi."""

    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """XOM ko'rinish — ekranda ko'rsatish uchun. Solishtirish uchun
    emas: SAP da 10 xil format bor (`(+99890) 1234567`, `998901234567`,
    `(90) 123-45-67`…) va ba'zilarida umuman telegram nomi turadi."""

    phone_key: Mapped[str | None] = mapped_column(
        String(9), nullable=True, index=True
    )
    """Raqamning OXIRGI 9 tasi — `calls` bilan bog'lash kaliti.

    Tizimda hamma joyda shu kalit ishlatiladi
    (`moizvonki/application/ingest.py`, `clients/application/directory.py`).
    Kalit farq qilsa, bitta mijoz ikki bo'limda ikki xil ko'rinardi."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    telegram_link: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SaleModel(Base, UUIDMixin):
    """Bitta SAP operatsiyasi.

    ⚠️ `TimestampMixin` ATAYLAB ISHLATILMAGAN. Qator import bilan
    tug'iladi va faqat qayta import bilan o'zgaradi, ya'ni
    `created_at`/`updated_at` juftligi `imported_at` bilan bir xil
    ma'noni uch marta takrorlagan bo'lardi. Shartnomada ham bitta
    ustun ko'rsatilgan.
    """

    __tablename__ = "sales"

    external_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    """`Номер операции`. O'lchandi: 2384 qatorda 2383 noyob qiymat
    (bitta juft istisno), ya'ni idempotentlik uchun yetarli."""

    doc_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    op_type: Mapped[str] = mapped_column(String(32), index=True)
    """`SaleOpType` qiymatlari. `SAEnum` emas, oddiy matn: SAP ga yangi
    tur qo'shilsa PostgreSQL enum'ini ham o'zgartirish kerak bo'lardi,
    bu esa migratsiya talab qiladi."""

    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    """⚠️ FAQAT SANA, VAQTI YO'Q. SAP `Дата регистрации` da soat
    bermaydi. Shuning uchun qoidalar oynasi ham kun bilan o'lchanadi:
    «savdo kuni + oldingi N kun». Buni ekranda ochiq yozamiz —
    aks holda «soat 10 da savdo, soat 15 da qo'ng'iroq» degan holat
    noto'g'ri talqin qilinardi."""

    branch: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """`Направление` — ВЕЛО, МЕТАН… Mahsulot yo'nalishi."""

    partner_code: Mapped[str] = mapped_column(String(16), index=True)
    partner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Import paytidagi NUSXA. Katalogdagi nom keyin o'zgarsa ham,
    hisobotda savdo qaysi nom bilan o'tgani ko'rinib tursin."""

    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    """Hujjat valyutasidagi summa."""

    currency: Mapped[str] = mapped_column(String(8), default="USD")

    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    """AYNAN SHU summa dollarda.

    ⚠️ Shartnomada bu ustun yo'q edi, lekin fayl uni BEPUL beradi va u
    9-bo'limdagi ochiq savolga («valyuta kursi kerak bo'ladimi?»)
    javob beradi: KERAK EMAS. O'lchandi — `Хақдор ($)` ustuni hujjat
    valyutasidan qat'i nazar HAR DOIM dollar ekvivalentini saqlaydi
    (UZS hujjatda 8,333 $ ↔ 100 000,000 so'm; AED hujjatda
    136,240 $ ↔ 500,000 dirham). Busiz «10 000 dollardan katta savdo»
    degan chegara qo'yish uchun kurs jadvali kerak bo'lardi."""

    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    """`branch` orqali aniqlanadi (`sale_branches`).

    `SET NULL` — xodim o'chirilsa savdo qatori QOLISHI kerak: u SAP
    dagi fakt, bizning xodimlar ro'yxatimizga bog'liq emas."""

    phone_key: Mapped[str | None] = mapped_column(
        String(9), nullable=True, index=True
    )
    """Katalogdan ko'chirilgan nusxa — savdo faylida telefon yo'q.

    ⚠️ NEGA NUSXA, `JOIN` EMAS. Qoidalar `calls` bilan sana oynasi
    bo'yicha solishtiradi va bu so'rov millionlab qator ustidan
    ketadi; har safar `sale_partners` ga qo'shilish uni ikki barobar
    qimmatlashtirardi. Katalog yangilanganda nusxa
    `backfill_sale_links()` bilan qaytadan yoziladi."""

    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SaleReviewModel(Base, UUIDMixin):
    """Rahbarning qarori — bazadagi YAGONA subyektiv yozuv.

    Ro'yxat sukut bo'yicha faqat ko'rilmaganlarni ko'rsatadi, ya'ni
    bu jadvalda qatori bo'lgan savdo navbatdan chiqadi.
    """

    __tablename__ = "sale_reviews"

    sale_id: Mapped[UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    """`SaleReviewStatus`: `justified` yoki `confirmed`."""

    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """`SaleReviewReason` — faqat «oqlandi» uchun."""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    """⚠️ `NULL` bo'lishi mumkin. Shartnomada ustun majburiy ko'rsatilgan,
    lekin `ON DELETE SET NULL` busiz ishlamaydi — hisob o'chirilganda
    esa QAROR yo'qolmasligi kerak: statistika («qaysi xodimda oqlanmagan
    savdo ko'p») unga tayanadi."""

    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SaleBranchModel(Base, TimestampMixin):
    """SAP filiali → bizning xodim.

    Savdo faylida sotuvchi ismi YO'Q — bor-yo'g'i `Подразделение`
    (Бухоро, Мастона ёйма, Логистика…). Shuning uchun bog'lanish shu
    jadval orqali: import nom o'xshashligiga qarab avtomatik
    biriktiradi, qolganini rahbar qo'lda qo'yadi.

    ⚠️ `UUIDMixin` yo'q — birlamchi kalit filial NOMINING o'zi.
    Sun'iy `id` bu yerda ortiqcha bo'lardi: qatorlar SAP dagi nom
    bo'yicha izlanadi va boshqa hech qayerdan havola qilinmaydi.
    """

    __tablename__ = "sale_branches"

    branch: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_automatically: Mapped[bool] = mapped_column(Boolean, default=False)
    """`True` — nom o'xshashligiga qarab tizim topgan.

    ⚠️ Import MAVJUD qatorga TEGMAYDI (`ON CONFLICT DO NOTHING`).
    Sabab: rahbar qo'lda biriktirgan xodimni keyingi import jimgina
    almashtirib yuborishi mumkin emas. Ya'ni qo'lda qo'yilgan qaror
    har doim ustun turadi."""
