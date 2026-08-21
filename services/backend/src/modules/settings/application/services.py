"""Sozlamalar servisi.

Qiymat olish ustuvorligi:  baza  >  .env  >  reyestrdagi standart qiymat
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as env_settings
from src.core.exceptions import NotFoundError, ValidationError
from src.modules.settings.domain.entities import (
    CATEGORY_LABEL_UZ,
    SECRET_MASK,
    SETTINGS_BY_KEY,
    SETTINGS_REGISTRY,
    SettingSpec,
)
from src.modules.settings.infrastructure.models import SettingModel


#: Ichki raqamlar sozlamasi — o'zgarganda kesh bo'shatiladi.
INTERNAL_NUMBERS_KEY = "moizvonki.internal_numbers"


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── O'qish ────────────────────────────────────────────────

    async def _db_values(self) -> dict[str, Any]:
        rows = (await self._session.execute(select(SettingModel))).scalars().all()
        return {row.key: row.value.get("v") for row in rows}

    @staticmethod
    def _env_value(spec: SettingSpec) -> Any:
        if not spec.env_var:
            return None
        value = getattr(env_settings, spec.env_var, None)
        return value if value not in ("", None) else None

    async def get_value(self, key: str) -> Any:
        """Bitta sozlamaning haqiqiy qiymati (ichki foydalanish uchun — maskasiz)."""
        spec = SETTINGS_BY_KEY.get(key)
        if spec is None:
            raise NotFoundError(f"Noma'lum sozlama: {key}")

        db = await self._db_values()
        if key in db and db[key] not in ("", None):
            return db[key]

        env = self._env_value(spec)
        if env is not None:
            return env

        return spec.default

    async def get_all_values(self) -> dict[str, Any]:
        """Barcha sozlamalar — ichki foydalanish uchun (maskasiz)."""
        db = await self._db_values()
        result: dict[str, Any] = {}
        for spec in SETTINGS_REGISTRY:
            if spec.key in db and db[spec.key] not in ("", None):
                result[spec.key] = db[spec.key]
                continue
            env = self._env_value(spec)
            result[spec.key] = env if env is not None else spec.default
        return result

    async def access_values(self) -> dict[str, Any]:
        """Faqat `access.*` sozlamalari — ruxsatlarni hisoblash uchun."""
        values = await self.get_all_values()
        return {k: v for k, v in values.items() if k.startswith("access.")}

    async def list_for_ui(self) -> list[dict[str, Any]]:
        """UI uchun kategoriyalarga bo'lingan ro'yxat.

        Maxfiy qiymatlar HECH QACHON qaytarilmaydi — faqat
        "to'ldirilgan / to'ldirilmagan" holati ko'rsatiladi.
        """
        values = await self.get_all_values()
        db = await self._db_values()

        by_category: dict[str, dict[str, Any]] = {}
        for spec in SETTINGS_REGISTRY:
            bucket = by_category.setdefault(
                spec.category.value,
                {
                    "category": spec.category.value,
                    "label": CATEGORY_LABEL_UZ[spec.category],
                    "fields": [],
                },
            )

            raw = values.get(spec.key)
            is_set = raw not in ("", None)

            bucket["fields"].append(
                {
                    "key": spec.key,
                    "label": spec.label_uz,
                    "type": spec.type,
                    "options": spec.options,
                    "hint": spec.hint_uz,
                    "value": SECRET_MASK if (spec.is_secret and is_set) else (None if spec.is_secret else raw),
                    "is_set": is_set,
                    # Qiymat qayerdan kelayotgani — diagnostika uchun foydali
                    "source": "database" if spec.key in db else ("env" if self._env_value(spec) is not None else "default"),
                }
            )

        order = [c.value for c in CATEGORY_LABEL_UZ]
        return sorted(by_category.values(), key=lambda b: order.index(b["category"]))

    # ── Yozish ────────────────────────────────────────────────

    @staticmethod
    def _validate(spec: SettingSpec, value: Any) -> Any:
        """Qiymatni sozlama TURIGA tekshiradi va keltiradi.

        ⚠️ NEGA KERAK. Ilgari bu yerda hech qanday tekshiruv yo'q edi:
        reyestrda `select` deb e'lon qilingan sozlamaga ro'yxatdan
        tashqari qiymat, `number` ga esa matn bemalol saqlanardi.

        Ikkalasi ham JIMGINA buziladigan turdagi xato:
          · `survey.mode = "telepatiya"` — bot tushunmaydigan qiymat
            oladi va so'rovnoma kutilmagan shaklda ketadi;
          · `survey.period_days = "juda ko'p"` — o'quvchi
            (`_resolve_positive_int`) jimgina standart qiymatga
            qaytadi, admin esa o'zgartirgan sozlamasi nega ishlamayotganini
            tushunmaydi.

        Xatoni saqlash paytida aytish — yagona to'g'ri joy.
        """
        if value is None:
            return value

        if spec.type == "select":
            allowed = [option["value"] for option in spec.options]
            if allowed and str(value) not in allowed:
                raise ValidationError(
                    f"«{spec.label_uz}» uchun yaroqsiz qiymat: {value!r}. "
                    f"Mumkin: {', '.join(allowed)}"
                )
            return str(value)

        if spec.type == "number":
            if isinstance(value, bool):
                raise ValidationError(f"«{spec.label_uz}» son bo'lishi kerak")
            try:
                # Butun songa keltirsa bo'ladigan kasrni yo'qotmaymiz:
                # `0.7` (ishonch chegarasi) ham shu turdan o'tadi
                number = float(value)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"«{spec.label_uz}» son bo'lishi kerak, «{value}» emas"
                ) from None
            return int(number) if number.is_integer() else number

        if spec.type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "on", "ha"}
            return bool(value)

        return value

    async def set_value(self, key: str, value: Any, *, user_id: UUID | None = None) -> None:
        spec = SETTINGS_BY_KEY.get(key)
        if spec is None:
            raise NotFoundError(f"Noma'lum sozlama: {key}")

        # Maska qaytib kelsa — o'zgartirmaymiz (foydalanuvchi tegmagan)
        if spec.is_secret and value == SECRET_MASK:
            return

        value = self._validate(spec, value)

        stmt = (
            insert(SettingModel)
            .values(
                key=key,
                category=spec.category.value,
                value={"v": value},
                updated_by=user_id,
            )
            .on_conflict_do_update(
                index_elements=[SettingModel.key],
                set_={"value": {"v": value}, "updated_by": user_id},
            )
        )
        await self._session.execute(stmt)

        if key == INTERNAL_NUMBERS_KEY:
            # ⚠️ Kompaniya liniyalari ro'yxati jarayon xotirasida
            # keshlanadi (minglab qo'ng'iroqda bir xil `SELECT`
            # takrorlanmasin). Admin raqam qo'shgan zahoti ro'yxat
            # yangilanishi kerak, aks holda u tugmani bosadi-yu, hech
            # narsa o'zgarmaydi va sozlama ishlamayotgandek ko'rinadi.
            from src.modules.calls.application import internal_directory

            internal_directory.reset()

    async def set_many(
        self, values: dict[str, Any], *, user_id: UUID | None = None
    ) -> None:
        for key, value in values.items():
            await self.set_value(key, value, user_id=user_id)
