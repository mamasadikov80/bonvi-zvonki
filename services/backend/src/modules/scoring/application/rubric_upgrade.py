"""Mavjud rubrikaga «qo'llanilish» belgilarini qo'shish — BIR MARTA.

NEGA KERAK. Rubrika bazada saqlanadi va admin uni panelda tahrirlaydi,
ya'ni koddagi standart rubrikani o'zgartirish TIRIK tizimga ta'sir
qilmaydi. Yangi `optional` bayrog'i esa aynan rubrikada turishi kerak:
undan ikkita narsa kelib chiqadi — promptdagi ⟨taalluqli bo'lmasa `na`⟩
belgisi va validatordagi ruxsat.

Belgisiz rubrika ESKICHA ishlaydi (hamma mezon har doim baholanadi),
ya'ni yangilanish o'tkazib yuborilsa hech narsa buzilmaydi — shunchaki
qisqa suhbatlar avvalgidek qattiq baholanaveradi. Shuning uchun bu
funksiya «tuzatish» emas, «yangilanish»: u yangi VERSIYA yaratadi va
eskisi joyida qoladi (admin bir bosishda qaytara oladi).

Idempotentlik: rubrikada birorta `optional` kaliti bo'lsa — hech narsa
qilinmaydi. Ya'ni admin bayroqlarni o'zgartirsa, keyingi ishga tushish
uni bosib ketmaydi.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.scoring.application.rubric_service import RubricService
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

log = structlog.get_logger(__name__)


def _default_flags() -> dict[str, bool]:
    """Standart rubrikadagi `{kriteriya_id: optional}`."""
    flags: dict[str, bool] = {}
    for block in DEFAULT_RUBRIC["blocks"]:
        for criterion in block.get("criteria", []):
            flags[criterion["id"]] = bool(criterion.get("optional"))
    return flags


def _has_flags(blocks: list[dict[str, Any]]) -> bool:
    return any(
        "optional" in criterion
        for block in blocks or []
        for criterion in block.get("criteria", [])
    )


def apply_flags(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bloklar nusxasiga `optional` bayrog'ini qo'shadi.

    Standart rubrikada yo'q kriteriya (admin o'zi qo'shgani) `False`
    oladi — ya'ni har doim baholanadi. Bu ATAYLAB shunday: admin
    qo'shgan mezonni tizim o'zi «tashlab ketsa bo'ladi» deb belgilab
    qo'ymasligi kerak, bunday qaror faqat odamniki.
    """
    flags = _default_flags()
    natija: list[dict[str, Any]] = []
    for block in blocks or []:
        nusxa = dict(block)
        nusxa["criteria"] = [
            {**criterion, "optional": flags.get(criterion.get("id"), False)}
            for criterion in block.get("criteria", [])
        ]
        natija.append(nusxa)
    return natija


async def upgrade_rubric_applicability(session: AsyncSession) -> int | None:
    """Faol rubrikaga bayroqlarni qo'shib, YANGI versiya yaratadi.

    Qaytaradi: yangi versiya raqami, yoki `None` — kerak bo'lmadi.
    """
    service = RubricService(session)
    faol = await service.get_active()

    if _has_flags(faol.blocks):
        return None

    yangi = await service.create_version(
        blocks=apply_flags(faol.blocks),
        red_flags=faol.red_flags,
        extra_rules=faol.extra_rules,
        name=f"{faol.name} · qo'llanilish belgilari",
        description=(
            "Qisqa va takroriy suhbatlarda taalluqli bo'lmagan mezonlar "
            "endi nol olmaydi — ular ball hisobidan chiqariladi. "
            f"Manba: v{faol.version}."
        ),
    )
    await session.commit()
    log.info("rubric.applicability_upgraded", version=yangi.version)
    return yangi.version
