"""Baholash mezonlari (rubrika) endpointlari."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession, require_permission
from src.modules.scoring.application.prompt import (
    MAX_EXTRA_RULES,
    build_system_prompt,
    split_system_prompt,
)
from src.modules.scoring.application.rubric_service import RubricService

router = APIRouter(prefix="/rubric", tags=["Rubric"])


class Criterion(BaseModel):
    id: str
    label: str
    points: int = Field(ge=0, le=100)
    description: str | None = None
    optional: bool = False
    """Mezon HAR SUHBATGA tushadimi.

    `True` — AI uni «bu suhbatga taalluqli emas» deb belgilashi va ball
    hisobidan chiqarib tashlashi mumkin. Eski mijoz «menga 50 ta
    chiqaring» deb qo'ng'iroq qilganda ehtiyojni aniqlash ham,
    mahsulotni taqdim etish ham talab qilinmaydi — bunday mezonga nol
    qo'yish xodimni aybsiz holda jazolash bo'lardi.

    `False` (sukut bo'yicha) — mezon har qanday suhbatda tekshiriladi.
    Sukut ATAYLAB `False`: yangi mezon qo'shgan admin uni bexosdan
    «tashlab ketsa bo'ladi» deb belgilab qo'ymasin."""


class Block(BaseModel):
    key: str
    label: str
    max: int = Field(ge=1, le=100)
    criteria: list[Criterion]


class RedFlag(BaseModel):
    type: str
    label: str
    penalty: int = Field(le=0)
    zeroes_score: bool = False
    description: str | None = None


class RubricResponse(BaseModel):
    id: UUID
    version: int
    name: str
    description: str | None
    is_active: bool
    blocks: list[Any]
    red_flags: list[Any]
    extra_rules: str | None = None
    """Admin yozgan qo'shimcha baholash ko'rsatmalari."""
    created_at: datetime

    model_config = {"from_attributes": True}


class RubricVersionSummary(BaseModel):
    version: int
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SaveRubricRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    blocks: list[Block]
    red_flags: list[RedFlag]
    extra_rules: str | None = Field(
        default=None,
        max_length=MAX_EXTRA_RULES,
        description=(
            "Qo'shimcha baholash ko'rsatmalari (erkin matn). Promptga "
            "alohida bo'lim bo'lib qo'shiladi. Javob shakliga ta'sir "
            "qilmaydi — format qismi undan keyin turadi va ustun."
        ),
    )


class PromptSection(BaseModel):
    """Yig'ilgan promptning bir bo'lagi.

    Admin nima yuborilayotganini AYNAN ko'rishi kerak. Faqat tahrir
    qilinadigan qismni ko'rsatish yetmaydi: ko'rsatma qanday kontekstga
    qo'shilayotganini bilmasa, admin allaqachon aytilgan narsani
    takrorlaydi yoki unga zid gap yozadi."""

    key: str
    editable: bool
    text: str


class PromptPreview(BaseModel):
    rubric_version: int
    """Qaysi rubrika versiyasidan yig'ilgan."""
    sections: list[PromptSection]
    full_text: str
    char_count: int
    approx_tokens: int
    """Taxminiy token soni — har qo'ng'iroqda to'lanadi."""
    extra_rules_limit: int


@router.get(
    "",
    response_model=RubricResponse,
    summary="Faol rubrika",
    dependencies=[Depends(require_permission("rubric:read"))],
)
async def get_active(session: DbSession, user: CurrentUser):
    rubric = await RubricService(session).get_active()
    await session.commit()
    return rubric


@router.get(
    "/versions",
    response_model=list[RubricVersionSummary],
    summary="Versiyalar tarixi",
    dependencies=[Depends(require_permission("rubric:read"))],
)
async def list_versions(session: DbSession, user: CurrentUser):
    return await RubricService(session).list_versions()


@router.put(
    "",
    response_model=RubricResponse,
    summary="Yangi versiya saqlash",
    dependencies=[Depends(require_permission("rubric:write"))],
)
async def save(payload: SaveRubricRequest, session: DbSession, user: CurrentUser):
    """Har saqlash YANGI versiya yaratadi — eskisi o'chirilmaydi.

    Sabab: eski baholar o'z rubrikasi bilan bog'liq qolishi kerak,
    aks holda ballarni taqqoslash ma'nosini yo'qotadi.
    """
    rubric = await RubricService(session).create_version(
        blocks=[b.model_dump() for b in payload.blocks],
        red_flags=[f.model_dump() for f in payload.red_flags],
        extra_rules=payload.extra_rules,
        name=payload.name,
        description=payload.description,
        user_id=user.id,
    )
    await session.commit()
    return rubric


@router.post(
    "/versions/{version}/activate",
    response_model=RubricResponse,
    summary="Eski versiyaga qaytish",
    dependencies=[Depends(require_permission("rubric:write"))],
)
async def activate(version: int, session: DbSession, user: CurrentUser):
    rubric = await RubricService(session).activate(version)
    await session.commit()
    return rubric


@router.get(
    "/prompt",
    response_model=PromptPreview,
    summary="AI ga yuboriladigan so'rov matni (o'qish uchun)",
    dependencies=[Depends(require_permission("rubric:read"))],
)
async def prompt_preview(session: DbSession, user: CurrentUser) -> PromptPreview:
    """Faol rubrikadan yig'ilgan TIZIM PROMPTINI qaytaradi.

    ⚠️ NEGA BU ENDPOINT BOR. Admin baholashga ta'sir qiladigan matnni
    tahrirlaydi, lekin AI ga aynan nima ketayotganini ko'rmasa —
    ko'r-ko'rona ishlaydi: allaqachon aytilgan qoidani takrorlaydi
    (tokenni bejiz to'laydi) yoki unga zid gap yozadi va nega natija
    o'zgarmaganini tushunmaydi.

    Bo'limlar `editable` belgisi bilan keladi: faqat bittasi tahrir
    qilinadi, qolganlari ko'rinadi-yu, o'zgartirilmaydi. Javob shakli
    va til qoidalari o'zgarmas bo'lishi SHART — ular buzilsa har bir
    baho validatsiyadan o'tmay qoladi.

    Foydalanuvchi xabari (transkript, sana, davomiylik) bu yerda YO'Q:
    u har qo'ng'iroqda boshqacha bo'ladi va promptning keshlanadigan
    qismiga kirmaydi.
    """
    rubric = await RubricService(session).get_active()
    await session.commit()

    full = build_system_prompt(rubric.blocks, rubric.red_flags, rubric.extra_rules)
    sections = split_system_prompt(
        rubric.blocks, rubric.red_flags, rubric.extra_rules
    )
    return PromptPreview(
        rubric_version=rubric.version,
        sections=[PromptSection(**part) for part in sections],
        full_text=full,
        char_count=len(full),
        # Taxmin: o'zbek/rus matnida ~3.3 belgi bir tokenga to'g'ri
        # keladi. Aniq son vendorga bog'liq, shuning uchun «taxminiy» —
        # admin kattalik tartibini ko'rsin, aniq hisob-kitob emas.
        approx_tokens=round(len(full) / 3.3),
        extra_rules_limit=MAX_EXTRA_RULES,
    )
