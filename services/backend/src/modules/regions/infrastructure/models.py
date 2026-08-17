"""Hudud ORM modeli."""

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.modules.regions.domain.entities import REGION_NAME_MAX, REGION_NOTE_MAX


class RegionModel(Base, UUIDMixin, TimestampMixin):
    """Admin boshqaradigan hudud.

    Bu jadval — hududlar ro'yxatining YAGONA manbai. Xodim/mijoz/guruhdagi
    `region` ustunlari bu yerga FK bilan bog'lanmagan, ular nomning
    nusxasini saqlaydi — shuning uchun nom o'zgarganda kaskad yangilanish
    (`RegionService.update`) buzilmasligi kerak.
    """

    __tablename__ = "regions"

    name: Mapped[str] = mapped_column(
        String(REGION_NAME_MAX), unique=True, index=True
    )

    # Faol emas → yangi biriktirishda tanlovda ko'rinmaydi, lekin
    # allaqachon biriktirilgan yozuvlar tegilmaydi (o'chirish emas, arxiv).
    # `server_default`: boshlang'ich to'ldirish Core INSERT bilan ketadi,
    # unda ORM ning Python-tarafdagi `default` qiymati qo'llanmaydi.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True
    )

    # Ro'yxatdagi tartib — kichigi yuqorida
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )

    # Ixtiyoriy izoh, masalan «Samarqand viloyatining shimoliy tumanlari»
    note: Mapped[str | None] = mapped_column(String(REGION_NOTE_MAX), nullable=True)
