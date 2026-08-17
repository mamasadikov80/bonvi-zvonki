"""Telegram guruhlari endpointlari.

Ikki xil himoya bir router ichida:

  • admin panel — JWT + `groups:read` / `groups:write`
  • bot — `X-Internal-Token` (`/register`, `/pending-surveys`)

Bot foydalanuvchi emas, unda JWT yo'q. Ichki kalit tekshiruvi sozlamalar
modulida yozilgan (`require_internal_token`) — ikkinchi nusxa yozilmaydi,
o'sha yerdan import qilinadi.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession
from src.core.exceptions import ForbiddenError
from src.modules.groups.application.services import GroupService
from src.modules.groups.domain.entities import BotStatus
from src.modules.regions.application.services import RegionService
from src.modules.settings.application.services import SettingsService
from src.modules.settings.presentation.router import require_internal_token
from src.modules.users.domain.entities import User, resolve_permissions

router = APIRouter(prefix="/groups", tags=["Groups"])

InternalOnly = Depends(require_internal_token)


# ── Ruxsat tekshiruvi ─────────────────────────────────────────
#
# `core.deps.require_permission` faqat rolning QAT'IY ruxsatlarini biladi.
# `groups:write` esa menejerga sozlamalar orqali beriladi
# (`access.manager_manages_agents`), shuning uchun bu yerda
# `resolve_permissions` ishlatiladi — `agents:write` bilan bir xil qoida.


def require_group_permission(permission: str) -> Callable:
    async def checker(session: DbSession, user: CurrentUser) -> User:
        access = await SettingsService(session).access_values()
        if permission not in resolve_permissions(user.role, access):
            raise ForbiddenError(f"Ruxsat yetarli emas: {permission}")
        return user

    return checker


CanRead = Depends(require_group_permission("groups:read"))
CanWrite = Depends(require_group_permission("groups:write"))


# ── Sxemalar ──────────────────────────────────────────────────


class GroupResponse(BaseModel):
    id: UUID
    chat_id: int
    title: str
    agent_id: UUID | None
    agent_name: str | None
    agent_color: str | None
    region: str | None
    suggested_region: str | None = None
    """Guruh nomidan taxmin qilingan hudud — admin tasdiqlashi uchun.
    Hudud allaqachon biriktirilgan bo'lsa doim `null`."""
    regions: list[str] = []
    """Shu guruhga biriktirilgan xodimning BARCHA hududlari — uning
    guruhlaridan yig'iladi (bitta xodim bir nechta hududda bo'la oladi)."""
    member_count: int | None
    is_active: bool
    bound_by: str | None = None
    """`auto` — avtomatika biriktirgan, `manual` — admin qo'lda,
    `null` — hech kim. `manual` bo'lsa avtomatika bu guruhga tegmaydi."""
    bot_status: str
    bound_at: datetime | None
    last_survey_at: datetime | None
    survey_count: int
    response_count: int


class GroupPage(BaseModel):
    """Sahifalangan javob.

    ⚠️ Guruhlar ~1000 ta (har mijozga alohida guruh) — ro'yxat
    sahifalanmasa javob bir necha megabayt bo'lib, sahifa sudralib
    qolardi."""

    items: list[GroupResponse]
    total: int
    page: int
    page_size: int


class GroupUpdateRequest(BaseModel):
    agent_id: UUID | None = None
    region: str | None = Field(default=None, max_length=64)
    """`null` YUBORILSA hudud bo'shatiladi — admin guruhni «keraksiz»
    deb shunday belgilaydi. Umuman yuborilmasa tegilmaydi (`exclude_unset`)."""
    is_active: bool | None = None


class GroupBulkUpdateRequest(BaseModel):
    group_ids: list[UUID] = Field(min_length=1, max_length=200)
    agent_id: UUID | None = None
    region: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class GroupBulkUpdateResponse(BaseModel):
    updated: int


class GroupRegisterRequest(BaseModel):
    chat_id: int
    title: str = Field(min_length=1, max_length=255)
    member_count: int | None = None
    bot_status: BotStatus = BotStatus.MEMBER


class GroupRegisterResponse(BaseModel):
    id: UUID
    chat_id: int
    title: str
    agent_id: UUID | None
    region: str | None
    suggested_region: str | None = None
    is_active: bool
    bound: bool
    """`True` bo'lsa guruh so'rovnomaga tayyor (xodim + hudud biriktirilgan)."""


class GroupAutobindRequest(BaseModel):
    chat_id: int
    title: str = Field(min_length=1, max_length=255)
    member_count: int | None = None
    bot_status: BotStatus = BotStatus.MEMBER
    candidate_user_ids: list[int] = Field(
        default_factory=list,
        max_length=200,
        description=(
            "Guruhda ko'rilgan Telegram id lari: botni qo'shgan odam, "
            "guruh adminlari, guruhda yozganlar. Ro'yxatdan o'tgan "
            "xodim topilishi uchun bittasi yetadi."
        ),
    )


class GroupAutobindResponse(BaseModel):
    id: UUID
    chat_id: int
    title: str
    agent_id: UUID | None
    agent_name: str | None
    region: str | None
    """`null` — xodimda bir nechta hudud bor, admin daraxtda tanlaydi.
    Hududsiz guruh so'rovnoma OLMAYDI."""
    member_count: int | None
    bound: bool
    """Guruhga xodim biriktirilgani. So'rovnomaga tayyorligi EMAS —
    buning uchun hudud ham kerak."""
    bound_by: str | None
    reason: str
    """`matched` — guruhda xodim bor; `no_agent` — nomzodlar orasidan
    ro'yxatdan o'tgan xodim topilmadi; `manual` — admin qo'lda
    biriktirgan, avtomatika tegmadi."""


class TreeRegionNode(BaseModel):
    region: str | None
    """`null` — xodimga biriktirilgan, lekin hududi yo'q guruhlar.
    Ular so'rovnoma olmaydi: admin yo hudud beradi, yo keraksiz deb
    shu holida qoldiradi."""
    group_count: int
    response_count: int


class TreeAgentNode(BaseModel):
    agent_id: UUID
    full_name: str
    color: str
    avatar_url: str | None
    enrolled: bool
    """`false` — xodim botga raqamini yubormagan. Uning yangi guruhlari
    AVTOMATIK biriktirilmaydi, hammasi `unassigned` ga tushadi."""
    regions: list[TreeRegionNode]
    group_count: int


class TreeBucket(BaseModel):
    group_count: int


class GroupTreeResponse(BaseModel):
    agents: list[TreeAgentNode]
    unassigned: TreeBucket
    """Xodimi aniqlanmagan guruhlar — haqiqiy nosozlik belgisi:
    sotuvchi ro'yxatdan o'tmagan yoki guruhda umuman ko'rinmagan."""


class PendingSurveyResponse(BaseModel):
    survey_id: UUID
    token: str
    chat_id: int
    agent_name: str
    period_start: datetime
    period_end: datetime


class SurveyCreatedResponse(BaseModel):
    survey_id: UUID
    token: str
    status: str
    reused: bool = False
    """`True` — yangi so'rovnoma yaratilmadi, navbatda turgani qaytarildi.
    Guruhga ikkinchi bir xil xabar tushmasligi uchun."""


class SurveyCreateRequest(BaseModel):
    force: bool = False
    """`True` — suppression oynasi (10 kun) e'tiborsiz qoldiriladi.
    Tuzilmaviy qoidalar (xodim/hudud/faollik) baribir ishlaydi."""


class BroadcastRequest(BaseModel):
    force: bool = True
    """Sukut bo'yicha `True`: endpoint aynan majburiy yuborish uchun bor.
    `False` bilan chaqirilsa suppression oynasi hisobga olinadi — kelajakdagi
    avtomatik (kadans bo'yicha) ommaviy yuborish uchun shu yo'l ochiq turadi."""


class BroadcastSkipped(BaseModel):
    group_id: UUID
    title: str
    reason: str
    """`group_not_bound` | `group_inactive` | `survey_suppressed` —
    bitta guruh endpointidagi 409 kodlari bilan bir xil."""
    message: str


class BroadcastResponse(BaseModel):
    created: int
    reused: int
    """Navbatda allaqachon turgan (hali yuborilmagan) so'rovnomalar soni."""
    skipped: list[BroadcastSkipped]
    total_groups: int
    """Ko'rib chiqilgan barcha guruhlar (faolsizlari ham).
    `created + reused + len(skipped) == total_groups`."""


# ══════════════════════════════════════════════════════════════
#  Bot uchun ichki endpointlar
#
#  Yuqorida turadi: `/register` va `/pending-surveys` — qat'iy
#  yo'llar, `{group_id}` shabloniga tushib qolmasin.
# ══════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=GroupRegisterResponse,
    summary="[ichki] Guruhni ro'yxatga olish (upsert)",
    dependencies=[InternalOnly],
)
async def register_group(payload: GroupRegisterRequest, session: DbSession):
    """Bot guruhga qo'shilganda yoki holati o'zgarganda chaqiradi.

    Mavjud guruh yangilanadi (nomi, a'zolar soni, bot holati), biriktirish
    esa tegilmaydi — uni faqat admin o'zgartiradi.
    """
    return await GroupService(session).register(
        chat_id=payload.chat_id,
        title=payload.title,
        member_count=payload.member_count,
        bot_status=payload.bot_status.value,
    )


@router.post(
    "/autobind",
    response_model=GroupAutobindResponse,
    summary="[ichki] Guruhni ro'yxatga olish va xodimini avtomatik topish",
    dependencies=[InternalOnly],
)
async def autobind_group(payload: GroupAutobindRequest, session: DbSession):
    """`/register` ning kengaytmasi: xodimni ham O'ZI topadi.

    Guruhlar ~1000 ta — qo'lda biriktirish imkonsiz. Bot guruhda
    ko'rgan Telegram id larini yuboradi, backend ularni ro'yxatdan
    o'tgan xodimlar bilan solishtiradi.

    **Admin qo'lda biriktirgan guruh (`bound_by="manual"`) hech qachon
    qayta yozilmaydi** — `reason: "manual"` bilan qaytadi.

    Hudud xodimning mavjud guruhlaridan olinadi va faqat u AYNAN BITTA
    hududda ishlasa qo'yiladi. `agents.region` ishlatilmaydi.
    """
    return await GroupService(session).autobind(
        chat_id=payload.chat_id,
        title=payload.title,
        member_count=payload.member_count,
        bot_status=payload.bot_status.value,
        candidate_user_ids=payload.candidate_user_ids,
    )


@router.get(
    "/pending-surveys",
    response_model=list[PendingSurveyResponse],
    summary="[ichki] Yuborilmagan so'rovnomalar navbati",
    dependencies=[InternalOnly],
)
async def pending_surveys(session: DbSession):
    """Bot navbatni olib, har birini guruhga yuboradi va `/sent` deb belgilaydi."""
    return await GroupService(session).pending_surveys()


class LiveSurveyResponse(BaseModel):
    token: str
    chat_id: int
    chat_message_id: int
    response_count: int


@router.get(
    "/live-surveys",
    response_model=list[LiveSurveyResponse],
    summary="[ichki] Yuborilgan so'rovnomalar va javoblar soni",
    dependencies=[InternalOnly],
)
async def live_surveys(session: DbSession):
    """Guruhdagi hisoblagichni yangilash uchun.

    Mini App rejimida baho backendga to'g'ridan-to'g'ri tushadi, bot
    bundan bexabar qoladi. Bot shu ro'yxatni o'qib, soni o'zgargan
    xabarlarnigina tahrirlaydi.
    """
    return await GroupService(session).live_surveys()


class ExpiredSurveyMessage(BaseModel):
    token: str
    chat_id: int
    chat_message_id: int


@router.get(
    "/expired-survey-messages",
    response_model=list[ExpiredSurveyMessage],
    summary="[ichki] Guruhdan o'chirilishi kerak bo'lgan so'rovnoma xabarlari",
    dependencies=[InternalOnly],
)
async def expired_survey_messages(session: DbSession):
    """Muddati tugagan so'rovnoma xabarlari — bot ularni o'chiradi.

    ⚠️ Bot guruhdagi xabarlarni o'zi sanab chiqmaydi: u FAQAT shu
    ro'yxatdagi aniq `(chat_id, message_id)` juftliklarini o'chiradi.
    Har biri — botning o'zi yuborgan va `/sent` orqali qayd etilgan
    so'rovnoma xabari. Shu sababli bir bot bir nechta dastur bilan
    ishlatilsa ham begona xabar bu ro'yxatga tusha olmaydi.

    Muddat `survey.message_ttl_hours` sozlamasidan olinadi; `0`
    bo'lsa ro'yxat doim bo'sh — hech narsa o'chirilmaydi.
    """
    return await GroupService(session).expired_survey_messages()


@router.post(
    "/surveys/{token}/message-deleted",
    summary="[ichki] Xabar guruhdan olib tashlandi",
    dependencies=[InternalOnly],
    responses={404: {"description": "So'rovnoma topilmadi"}},
)
async def mark_survey_message_deleted(token: str, session: DbSession):
    """Bot o'chirgandan keyin chaqiradi — yozuv navbatdan chiqadi.

    O'chirib BO'LMAGAN holatda ham chaqiriladi (Telegram 48 soatdan
    keyin ruxsat bermaydi): aks holda o'sha xabar har aylanishda
    qaytib kelaverardi.
    """
    return await GroupService(session).mark_message_deleted(token)


# ══════════════════════════════════════════════════════════════
#  Admin panel
# ══════════════════════════════════════════════════════════════


@router.get(
    "/regions",
    response_model=list[str],
    summary="Hududlar ro'yxati (eski alias — `GET /regions` ga qarang)",
    deprecated=True,
)
async def list_regions(session: DbSession, user: CurrentUser) -> list[str]:
    """Eski alias: faqat nomlar. Endi qat'iy ro'yxat emas, BAZADAN o'qiladi.

    Ruxsat talab qilinmaydi, faqat avtorizatsiya: hudud nomlari maxfiy emas,
    lekin ro'yxat xodim formasida ham, guruh formasida ham kerak.

    Faolsizlar ham qaytadi: bu shim eski `<select>` larni to'ydiradi va
    ularda allaqachon biriktirilgan hudud tanlovdan yo'qolsa, saqlashda
    qiymat jimgina o'zgarib ketardi. To'liq ma'lumot (`is_active`, tartib,
    ishlatilish soni) yangi `GET /regions` da.
    """
    return await RegionService(session).names(include_inactive=True)


@router.get(
    "/tree",
    response_model=GroupTreeResponse,
    summary="Daraxt: xodim → hudud → guruhlar",
    dependencies=[CanRead],
)
async def groups_tree(session: DbSession):
    """1000 ta guruhni ko'rish uchun yagona amaliy shakl.

    Faqat SONLAR qaytadi, guruhlarning o'zi emas — tugunni ochganda
    frontend `GET /groups?agent_id=…&region=…` bilan sahifa so'raydi.

    Ichkarida N+1 YO'Q: to'rtta yig'ma so'rov, ularning soni xodimlar
    va guruhlar soniga bog'liq emas.
    """
    return await GroupService(session).tree()


@router.get(
    "",
    response_model=GroupPage,
    summary="Guruhlar ro'yxati (sahifalangan)",
    dependencies=[CanRead],
)
async def list_groups(
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    agent_id: UUID | None = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
    has_region: Annotated[
        bool | None,
        Query(
            description=(
                "`false` — faqat hududsiz guruhlar (daraxtdagi «hududsiz» "
                "tugunini ochish uchun), `true` — faqat hududlilar"
            )
        ),
    ] = None,
    has_agent: Annotated[
        bool | None,
        Query(
            description=(
                "`false` — xodimi aniqlanmagan guruhlar (bot ularni "
                "tanimagan), `true` — xodimi bor guruhlar"
            )
        ),
    ] = None,
    search: Annotated[
        str | None, Query(max_length=120, description="Guruh nomi yoki xodim ismi")
    ] = None,
    include_inactive: bool = False,
):
    """⚠️ Javob SAHIFALANGAN: `{items, total, page, page_size}`.

    `page_size` standart 50, eng ko'pi 200. Guruhlar ~1000 ta, hammasini
    bitta javobda qaytarish mumkin emas.
    """
    return await GroupService(session).list_groups(
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        region=region,
        has_region=has_region,
        has_agent=has_agent,
        search=search,
        include_inactive=include_inactive,
    )


# ⚠️ `/bulk` `/{group_id}` DAN OLDIN — aks holda "bulk" UUID deb
# o'qilib 422 qaytardi.
@router.patch(
    "/bulk",
    response_model=GroupBulkUpdateResponse,
    summary="Bir nechta guruhni birdaniga o'zgartirish",
    responses={404: {"description": "Guruh yoki xodim topilmadi"}},
)
async def bulk_update_groups(
    payload: GroupBulkUpdateRequest,
    session: DbSession,
    _: Annotated[User, CanWrite],
):
    """Eng ko'p ishlatiladigan holat — `{"region": null}`.

    Guruhlar ~1000 ta, ularning bir qismi ishchi guruh emas. Adminni
    har birini alohida ochib hududini o'chirishga majburlash — ishlab
    bo'lmaydigan interfeys.

    Bitta guruh endpointi bilan bir xil qoidalar: o'zgartirilgan
    guruhlar `bound_by="manual"` bo'ladi va avtomatika ularga
    boshqa tegmaydi.
    """
    fields = payload.model_dump(exclude_unset=True)
    fields.pop("group_ids", None)
    return await GroupService(session).bulk_update(payload.group_ids, fields)


@router.patch(
    "/{group_id}",
    response_model=GroupResponse,
    summary="Guruhga xodim va hudud biriktirish",
    responses={404: {"description": "Guruh yoki xodim topilmadi"}},
)
async def update_group(
    group_id: UUID,
    payload: GroupUpdateRequest,
    session: DbSession,
    _: Annotated[User, CanWrite],
):
    """Faqat yuborilgan maydonlar o'zgaradi (`exclude_unset`).

    ⚠️ `agent_id: null` / `region: null` — bog'lanishni ATAYLAB uzish,
    "yuborilmagan" dan farqlanadi. `exclude_unset` aynan shu farqni
    saqlaydi; usiz admin hududni hech qachon bo'shata olmasdi, ya'ni
    guruhni «keraksiz» deb belgilashning imkoni bo'lmasdi.

    Xodim yoki hudud qo'lda o'zgartirilsa guruh `bound_by="manual"`
    bo'ladi va avtomatik biriktirish bundan keyin unga tegmaydi.
    """
    return await GroupService(session).update(
        group_id, payload.model_dump(exclude_unset=True)
    )


@router.get(
    "/{group_id}",
    response_model=GroupResponse,
    summary="Bitta guruh",
    dependencies=[CanRead],
    responses={404: {"description": "Guruh topilmadi"}},
)
async def get_group(group_id: UUID, session: DbSession):
    """Ro'yxatdagi qator bilan bir xil shakl.

    Ro'yxat sahifalangandan keyin kerak bo'lib qoldi: bitta guruhni
    topish uchun 20 ta sahifani varaqlab chiqib bo'lmaydi.
    """
    return await GroupService(session).get_one(group_id)


@router.delete(
    "/{group_id}",
    status_code=204,
    summary="Guruhni o'chirish (faqat bot chiqib ketgan bo'lsa)",
    responses={409: {"description": "Bot hali guruhda"}},
)
async def delete_group(
    group_id: UUID,
    session: DbSession,
    _: Annotated[User, CanWrite],
) -> None:
    await GroupService(session).delete(group_id)


# ⚠️ `/surveys/broadcast` `/{group_id}/survey` DAN OLDIN turishi shart.
# FastAPI marshrutlarni e'lon tartibida solishtiradi: pastda turса
# "surveys" `{group_id}` shabloniga tushib, UUID emasligi uchun 422 berardi.
@router.post(
    "/surveys/broadcast",
    response_model=BroadcastResponse,
    summary="Barcha guruhlarga so'rovnoma yuborish (majburiy)",
)
async def broadcast_group_surveys(
    session: DbSession,
    _: Annotated[User, CanWrite],
    payload: BroadcastRequest | None = None,
):
    """Har bir yaroqli guruhga bittadan so'rovnoma qo'yadi.

    Har biri o'sha guruhning O'Z savdo xodimiga yoziladi.

    Sukut bo'yicha `force=True`: 10 kunlik oyna hisobga olinmaydi.
    Biriktirilmagan yoki faolsiz guruh baribir o'tkazib yuboriladi —
    unda bahoni kimga yozishni bilmaymiz.

    Tana yuborilmasa ham ishlaydi (`{"force": true}` sukut qiymati).
    """
    body = payload or BroadcastRequest()
    return await GroupService(session).broadcast_surveys(force=body.force)


@router.post(
    "/{group_id}/survey",
    response_model=SurveyCreatedResponse,
    status_code=201,
    summary="Guruh uchun so'rovnoma yaratish",
    responses={
        404: {"description": "Guruh topilmadi"},
        409: {"description": "Biriktirilmagan guruh yoki muddat o'tmagan"},
    },
)
async def create_group_survey(
    group_id: UUID,
    session: DbSession,
    _: Annotated[User, CanWrite],
    payload: SurveyCreateRequest | None = None,
):
    """So'rovnoma navbatga qo'yiladi — botni kutadi, darhol yuborilmaydi.

    `force=true` — suppression oynasini chetlab o'tadi (bitta guruhni
    qayta so'rash uchun). Navbatda turgan so'rovnoma bo'lsa yangisi
    yaratilmaydi: `reused: true` bilan o'shaning o'zi qaytadi.
    """
    body = payload or SurveyCreateRequest()
    return await GroupService(session).create_survey(group_id, force=body.force)
