"""Hududlar endpointlari.

O'qish HAR QANDAY autentifikatsiyadan o'tgan rolga ochiq: hudud filtri
dashboardda ham, xodim profilida ham kerak, sales ham o'z hududini ko'radi.
Yozish esa admin ishi — menejerga faqat `access.manager_manages_agents`
yoqilganda beriladi, xuddi `agents:write` / `groups:write` kabi.
"""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession
from src.core.exceptions import ForbiddenError
from src.modules.regions.application.services import RegionService
from src.modules.regions.domain.entities import REGION_NAME_MAX, REGION_NOTE_MAX
from src.modules.settings.application.services import SettingsService
from src.modules.users.domain.entities import Role, User, resolve_permissions

router = APIRouter(prefix="/regions", tags=["Regions"])


# ── Ruxsat tekshiruvi ─────────────────────────────────────────
#
# `core.deps.require_permission` faqat rolning QAT'IY ruxsatlarini biladi.
# `regions:write` menejerga sozlamalar orqali beriladi, shuning uchun
# bu yerda `resolve_permissions` — `groups:write` bilan bir xil qoida.


def require_region_permission(permission: str) -> Callable:
    async def checker(session: DbSession, user: CurrentUser) -> User:
        access = await SettingsService(session).access_values()
        if permission not in resolve_permissions(user.role, access):
            raise ForbiddenError(f"Ruxsat yetarli emas: {permission}")
        return user

    return checker


CanRead = Depends(require_region_permission("regions:read"))
CanWrite = Depends(require_region_permission("regions:write"))


# ── Sxemalar ──────────────────────────────────────────────────


class RegionUsage(BaseModel):
    """Hudud nechta yozuvda ishlatilmoqda — o'chirishdan oldingi ogohlantirish."""

    agents: int = 0
    clients: int = 0
    groups: int = 0


class RegionResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool
    sort_order: int
    note: str | None
    usage: RegionUsage


class RegionArchivePreview(BaseModel):
    """Arxivlashdan OLDIN: nima to'xtaydi."""

    region: str
    active_groups: int
    """Shu hududdagi faol guruhlar. Arxivlashda ular so'rovnoma
    olishni to'xtatadi (agar `detach_groups: true` bilan uzilsa)."""


class RegionUpdateResponse(RegionResponse):
    renamed: RegionUsage = RegionUsage()
    """Nom o'zgarganda kaskad yangilangan qatorlar soni.
    Nom o'zgarmagan bo'lsa — hammasi nol."""

    detached_groups: int = 0
    """Arxivlashda hududi olib tashlangan FAOL guruhlar soni.

    Faqat `detach_groups: true` bilan so'ralganda noldan katta bo'ladi.
    Bu guruhlar endi so'rovnoma olmaydi va daraxtdagi «Hududsiz»
    tugunida ko'rinadi — UI shu sonni adminga qaytarib ko'rsatsin."""


class RegionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=REGION_NAME_MAX)
    sort_order: int | None = None
    note: str | None = Field(default=None, max_length=REGION_NOTE_MAX)


class RegionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=REGION_NAME_MAX)
    is_active: bool | None = None
    sort_order: int | None = None
    note: str | None = Field(default=None, max_length=REGION_NOTE_MAX)

    detach_groups: bool = True
    """Arxivlashda (`is_active: false`) hududni FAOL guruhlardan uzsinmi?

    ⚠️ Standart qiymat `True` — arxivlashdan maqsad shu hududga endi
    xizmat ko'rsatmaslik, demak guruhlarning uzilishi KUTILGAN natija.

    Ilgari bu yerda `False` turardi va qaror KLIENT tomonida edi:
    admin hududni o'chirardi, guruhlar esa eski hududda qolib
    so'rovnoma olishda davom etardi. Eski keshlangan sahifa yoki
    boshqa API klienti maydonni umuman yubormasa, natija jimgina
    boshqacha bo'lardi. Endi qoida serverda: kim so'rashidan qat'i
    nazar natija bir xil.

    Guruhlar eski hududda qolishi kerak bo'lsa — ataylab `false`
    yuboriladi.

    Tarixga ta'sir qilmaydi: har so'rovnoma o'z hudud nusxasini saqlaydi
    (`surveys.region`), shuning uchun o'tgan oylarning hisoboti
    o'zgarmaydi."""


# ── Endpointlar ───────────────────────────────────────────────


@router.get(
    "",
    response_model=list[RegionResponse],
    summary="Hududlar ro'yxati",
    dependencies=[CanRead],
)
async def list_regions(
    session: DbSession, user: CurrentUser, include_inactive: bool = False
):
    """Tartib bo'yicha saralangan ro'yxat + ishlatilish statistikasi.

    SAVDO XODIMI uchun ro'yxat O'ZINING hududlari bilan cheklanadi.
    Uning butun ekrani o'z ma'lumotiga tuzilgan, filtrda esa butun
    kompaniyaning hududlari turardi — ularning ko'pini tanlash bo'sh
    jadval berardi va filtr buzuqdek ko'rinardi. Boshqa rollar
    (admin, menejer, kuzatuvchi) avvalgidek to'liq ro'yxatni oladi.
    """
    only_for_agent = user.agent_id if user.role is Role.SALES else None
    return await RegionService(session).list_regions(
        include_inactive=include_inactive, only_for_agent=only_for_agent
    )


@router.post(
    "",
    response_model=RegionResponse,
    status_code=201,
    summary="Hudud qo'shish",
    responses={409: {"description": "Shu nomli hudud allaqachon bor"}},
)
async def create_region(
    payload: RegionCreateRequest,
    session: DbSession,
    _: Annotated[User, CanWrite],
):
    """Viloyatni bo'lish uchun ham shu endpoint: «Samarqand shimol» —
    oddiy yangi hudud, alohida tur emas."""
    return await RegionService(session).create(
        name=payload.name,
        sort_order=payload.sort_order,
        note=payload.note,
    )


@router.get(
    "/{region_id}/archive-preview",
    response_model=RegionArchivePreview,
    summary="Arxivlashdan oldin: nechta faol guruh uziladi",
    dependencies=[CanRead],
    responses={404: {"description": "Hudud topilmadi"}},
)
async def archive_preview(
    region_id: UUID,
    session: DbSession,
    user: CurrentUser,  # noqa: ARG001 — ruxsat `CanRead` da tekshiriladi
):
    """UI arxivlash tugmasini bosishdan oldin shuni so'raydi.

    «12 ta faol guruh uziladi va so'rovnoma olishni to'xtatadi» degan
    ogohlantirish taxminга emas, aniq songa asoslansin.
    """
    service = RegionService(session)
    region = await service.get_one(region_id)
    return RegionArchivePreview(
        region=region["name"],
        active_groups=await service.active_group_count(region["name"]),
    )


@router.patch(
    "/{region_id}",
    response_model=RegionUpdateResponse,
    summary="Hududni tahrirlash (nom o'zgarsa — kaskad yangilanish)",
    responses={
        404: {"description": "Hudud topilmadi"},
        409: {"description": "Shu nomli hudud allaqachon bor"},
    },
)
async def update_region(
    region_id: UUID,
    payload: RegionUpdateRequest,
    session: DbSession,
    _: Annotated[User, CanWrite],
):
    """Faqat yuborilgan maydonlar o'zgaradi (`exclude_unset`).

    Nom o'zgarsa, javobdagi `renamed` da nechta xodim/mijoz/guruh
    yangilangani qaytadi — UI shuni adminga ko'rsatsin.
    """
    return await RegionService(session).update(
        region_id, payload.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{region_id}",
    status_code=204,
    summary="Hududni o'chirish (faqat ishlatilmayotgan bo'lsa)",
    responses={
        404: {"description": "Hudud topilmadi"},
        409: {"description": "Hudud ishlatilmoqda — faolsizlantiring"},
    },
)
async def delete_region(
    region_id: UUID,
    session: DbSession,
    _: Annotated[User, CanWrite],
) -> None:
    await RegionService(session).delete(region_id)
