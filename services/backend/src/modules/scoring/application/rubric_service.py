"""Rubrika servisi — o'qish va yangi versiya yaratish."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.modules.scoring.application.prompt import MAX_EXTRA_RULES
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC
from src.modules.scoring.infrastructure.rubric_models import RubricModel

#: Red flag kaliti uchun ruxsat etilgan shakl.
#
# NEGA QAT'IY. Kalit uch joyda ishlatiladi: promptda («faqat shu
# kalitlar»), LLM javobining validatsiyasida va interfeys yorliqlarida.
# Bo'sh joy yoki kirill harfi bo'lsa model uni takrorlay olmaydi va
# BUTUN javob rad etiladi — ya'ni bitta xato kalit baholashni to'xtatadi.
RED_FLAG_KEY = re.compile(r"[a-z][a-z0-9_]{1,31}")


class RubricService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── O'qish ────────────────────────────────────────────────

    async def get_active(self) -> RubricModel:
        row = (
            await self._session.execute(
                select(RubricModel).where(RubricModel.is_active.is_(True))
            )
        ).scalar_one_or_none()

        if row is None:
            # Birinchi ishga tushirish — standart rubrikani yaratamiz
            row = await self._create_default()
        return row

    async def list_versions(self) -> list[RubricModel]:
        return list(
            (
                await self._session.execute(
                    select(RubricModel).order_by(RubricModel.version.desc())
                )
            )
            .scalars()
            .all()
        )

    async def get_version(self, version: int) -> RubricModel:
        row = (
            await self._session.execute(
                select(RubricModel).where(RubricModel.version == version)
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"Rubrika v{version} topilmadi")
        return row

    # ── Yozish ────────────────────────────────────────────────

    async def create_version(
        self,
        *,
        blocks: list[dict[str, Any]],
        red_flags: list[dict[str, Any]],
        extra_rules: str | None = None,
        name: str | None = None,
        description: str | None = None,
        user_id: UUID | None = None,
    ) -> RubricModel:
        """Yangi versiya yaratadi va uni faol qiladi.

        Eski versiya o'chirilmaydi — unga bog'langan baholar saqlanib qoladi.
        """
        self._validate(blocks, red_flags)
        extra_rules = self._clean_extra_rules(extra_rules)

        last = (
            await self._session.execute(
                select(RubricModel.version).order_by(RubricModel.version.desc()).limit(1)
            )
        ).scalar_one_or_none()
        next_version = (last or 0) + 1

        await self._session.execute(
            update(RubricModel).values(is_active=False).where(RubricModel.is_active.is_(True))
        )

        row = RubricModel(
            version=next_version,
            name=name or f"Rubrika v{next_version}",
            description=description,
            is_active=True,
            blocks=blocks,
            red_flags=red_flags,
            extra_rules=extra_rules,
            created_by=user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def activate(self, version: int) -> RubricModel:
        """Eski versiyaga qaytish (rollback)."""
        row = await self.get_version(version)
        await self._session.execute(
            update(RubricModel).values(is_active=False).where(RubricModel.is_active.is_(True))
        )
        row.is_active = True
        await self._session.flush()
        return row

    # ── Validatsiya ───────────────────────────────────────────

    @staticmethod
    def _validate(blocks: list[dict], red_flags: list[dict]) -> None:
        if not blocks:
            raise ValidationError("Kamida bitta blok bo'lishi kerak")

        total = 0
        for block in blocks:
            block_max = block.get("max", 0)
            criteria = block.get("criteria", [])
            if not criteria:
                raise ValidationError(
                    f"'{block.get('label', '?')}' blokida kamida bitta kriteriya bo'lishi kerak"
                )

            criteria_sum = sum(c.get("points", 0) for c in criteria)
            if criteria_sum != block_max:
                raise ValidationError(
                    f"'{block.get('label', '?')}' bloki: kriteriyalar yig'indisi "
                    f"{criteria_sum}, lekin blok maksimumi {block_max}. Tenglashtiring."
                )
            total += block_max

        if total != 100:
            raise ValidationError(
                f"Bloklar yig'indisi {total} ball. Umumiy ball aniq 100 bo'lishi kerak."
            )

        korilgan: set[str] = set()
        for flag in red_flags:
            if flag.get("penalty", 0) > 0:
                raise ValidationError(
                    f"'{flag.get('label', '?')}' jarimasi manfiy bo'lishi kerak"
                )

            # ⚠️ KALIT TEKSHIRUVI. `type` promptga kalit sifatida tushadi
            # va bazaga yoziladi. Bo'sh yoki g'alati belgili kalit ikki
            # joyda buzardi: LLM javobidagi kalit validatsiyadan o'tmay
            # baho RAD ETILARDI, interfeys esa yorliqni topolmasdi.
            kalit = str(flag.get("type") or "").strip()
            if not RED_FLAG_KEY.fullmatch(kalit):
                raise ValidationError(
                    f"«{kalit or '(bo\'sh)'}» — noto'g'ri red flag kaliti. "
                    "Faqat kichik lotin harflari, raqam va pastki chiziq "
                    "(masalan: `shaxsiy_raqamga_ogdirish`), 2–32 belgi."
                )
            if kalit in korilgan:
                raise ValidationError(f"«{kalit}» kaliti takrorlangan")
            korilgan.add(kalit)

    @staticmethod
    def _clean_extra_rules(text: str | None) -> str | None:
        """Adminning qo'shimcha ko'rsatmasini tozalaydi va cheklaydi.

        Chegara bor, chunki bu matn HAR BIR qo'ng'iroqda promptga
        qo'shiladi — uzunligi to'g'ridan-to'g'ri pulga aylanadi.
        Chegarasiz maydonga butun ish yo'riqnomasi joylanishi mumkin va
        buni hech narsa to'smasdi.
        """
        matn = (text or "").strip()
        if not matn:
            # Bo'sh satr bilan `NULL` ni ajratmaslik kerak: ikkalasi ham
            # «ko'rsatma yo'q» degani, lekin bo'sh satr promptda bo'sh
            # sarlavha qoldirardi
            return None
        if len(matn) > MAX_EXTRA_RULES:
            raise ValidationError(
                f"Qo'shimcha qoidalar juda uzun: {len(matn)} belgi. "
                f"Chegara — {MAX_EXTRA_RULES} belgi, chunki bu matn har bir "
                "qo'ng'iroqda AI ga yuboriladi va xarajatga ta'sir qiladi."
            )
        return matn

    # ── Standart rubrika ──────────────────────────────────────

    async def _create_default(self) -> RubricModel:
        return await self.create_version(
            blocks=DEFAULT_RUBRIC["blocks"],
            red_flags=DEFAULT_RUBRIC["red_flags"],
            name=DEFAULT_RUBRIC["name"],
            description=DEFAULT_RUBRIC["description"],
        )
