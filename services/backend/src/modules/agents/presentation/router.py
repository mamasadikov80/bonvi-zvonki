"""Savdo xodimlari endpointlari."""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession, RequireAdmin, require_permission
from src.core.exceptions import ForbiddenError, NotFoundError
from src.modules.agents.application.avatar_service import delete_avatar, save_avatar
from src.modules.agents.application.services import AgentService
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.moizvonki.application.directory import (
    PHONE_LOOKBACK_DAYS,
    load_directory,
)
from src.modules.moizvonki.application.factory import moizvonki_client
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.settings.presentation.router import require_internal_token
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.users.infrastructure.models import UserModel
from src.modules.users.domain.entities import has_permission

router = APIRouter(prefix="/agents", tags=["Agents"])

InternalOnly = Depends(require_internal_token)


class AgentResponse(BaseModel):
    id: UUID
    full_name: str

    region: str
    """Xodim YASHAYDIGAN hudud — kartochkadagi maydon.

    ⚠️ Bu u XIZMAT KO'RSATADIGAN hudud EMAS: Toshkentda yashab
    Samarqand mijozlarini yuritish mumkin. Ekranlarda `regions`
    ko'rsatiladi, bu maydon esa tahrirlash formasi va eski
    integratsiyalar uchun qoladi."""

    regions: list[str] = []
    """Xodim xizmat ko'rsatadigan hududlar — biriktirilgan FAOL
    guruhlaridan yig'iladi. Telegram guruhlari daraxti bilan AYNAN
    bir xil manba (`groups/application/agent_regions.py`), shuning
    uchun ikkala ekranda bir xil ro'yxat ko'rinadi.

    Bo'sh ro'yxat — guruhi yo'q yoki guruhlariga hudud biriktirilmagan."""

    phone: str | None
    external_id: str | None
    hired_at: date | None
    is_active: bool
    color: str
    avatar_url: str | None = None

    telegram_user_id: int | None = None
    """Xodimning Telegram identifikatori. `null` — hali botga kontaktini
    yubormagan, ya'ni uning guruhlari AVTOMATIK biriktirilmaydi."""
    telegram_username: str | None = None
    enrolled_at: datetime | None = None

    archived_at: datetime | None = None
    """Arxivga o'tgan vaqt. `null` — odatdagi xodim.

    Arxivlangan xodim ekranlarda ko'rinmaydi, lekin uning qo'ng'iroqlari
    va baholari joyida turadi va kimga tegishli ekani bilinadi."""

    bound_groups: int = 0
    """Shu xodimga hozir biriktirilgan Telegram guruhlari soni.
    Ro'yxatda ham, bitta xodimda ham bor — faolsizlantirishdan OLDIN
    adminni ogohlantirish uchun ("3 ta guruh bo'shaydi")."""

    freed_groups: int | None = None
    """Faqat `PATCH` javobida to'ladi: shu amal natijasida bo'shatilgan
    guruhlar soni. Xodim faolsizlantirilmagan bo'lsa `0`, boshqa
    endpointlarda `null`."""

    model_config = {"from_attributes": True}


class AgentCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    region: str = Field(min_length=2, max_length=100)
    phone: str | None = None
    external_id: str | None = None
    hired_at: date | None = None
    color: str = "#6366f1"


class AgentUpdateRequest(BaseModel):
    full_name: str | None = None
    region: str | None = None
    phone: str | None = None
    external_id: str | None = None
    hired_at: date | None = None
    is_active: bool | None = None
    color: str | None = None


@router.get(
    "",
    response_model=list[AgentResponse],
    summary="Xodimlar ro'yxati",
    dependencies=[Depends(require_permission("agents:read"))],
)
async def list_agents(
    session: DbSession,
    include_inactive: bool = False,
    search: str | None = None,
    include_archived: bool = False,
):
    """Arxivlanganlar standart holatda CHIQMAYDI.

    `include_inactive` ularni ochmaydi: «ishdan bo'shagan» va «tizimdan
    olib tashlangan» — boshqa-boshqa holat. Arxivni ko'rish uchun
    ataylab `include_archived=true` so'raladi.
    """
    return await AgentService(session).list_agents(
        include_inactive=include_inactive,
        search=search,
        include_archived=include_archived,
    )


@router.post("", response_model=AgentResponse, status_code=201, summary="Xodim qo'shish")
async def create_agent(payload: AgentCreateRequest, session: DbSession, _: RequireAdmin):
    return await AgentService(session).create(payload.model_dump())


# ══════════════════════════════════════════════════════════════
#  MoyZvonki'dan xodimlarni import qilish
#
#  ⚠️ `/{agent_id}` DAN OLDIN turishi shart: FastAPI marshrutlarni
#     e'lon tartibida solishtiradi.
# ══════════════════════════════════════════════════════════════


class DirectoryRow(BaseModel):
    external_id: str
    email: str | None
    display_name: str | None
    group_name: str | None
    role: int | None

    detected_phone: str | None
    """Qo'ng'iroqlardagi `src_number` dan aniqlangan raqam.

    `null` — topilmadi. Bu ODDIY holat: Android'da SIM o'z raqamini
    ko'pincha bermaydi. Admin uni qo'lda to'ldiradi."""

    call_count: int
    """Oxirgi davrdagi qo'ng'iroqlar soni — kimni import qilishni
    tanlashda asosiy mezon. 0 bo'lsa bu odam qo'ng'iroq qilmaydi."""

    truncated: bool = False
    """Skanerlash chegarasiga yetildi — `call_count` to'liq emas."""

    linked_agent_id: UUID | None = None
    """Bizda allaqachon shu `external_id` bilan xodim bor bo'lsa."""


class ImportRow(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=2, max_length=255)
    region: str = Field(min_length=2, max_length=100)
    phone: str | None = None


class ImportRequest(BaseModel):
    agents: list[ImportRow] = Field(min_length=1, max_length=200)


class ImportResult(BaseModel):
    created: int
    linked: int
    """Mavjud xodimga `external_id` yozib qo'yilganlar soni."""
    skipped: int


@router.get(
    "/moizvonki/employees",
    response_model=list[DirectoryRow],
    summary="MoyZvonki xodimlari — import uchun ro'yxat",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def moizvonki_employees(
    session: DbSession, lookback_days: int = PHONE_LOOKBACK_DAYS
):
    """Xodimlar ro'yxati + har biriga aniqlangan raqam va qo'ng'iroq soni.

    Raqam `company.list_employee` javobida YO'Q — u oxirgi kunlarning
    qo'ng'iroqlaridagi `src_number` dan aniqlanadi (eng ko'p uchragani).
    Shuning uchun bu so'rov bir necha soniya olishi mumkin.
    """
    async with moizvonki_client(session) as client:
        entries = await load_directory(client, lookback_days=lookback_days)

    # Bizda allaqachon bog'langanlarni belgilaymiz — admin ularni
    # ikkinchi marta yaratmasin
    linked = {
        (row.external_id or "").strip().lower(): row.id
        for row in (
            await session.execute(
                select(AgentModel).where(AgentModel.external_id.is_not(None))
            )
        ).scalars()
    }

    return [
        DirectoryRow(
            external_id=entry.external_id,
            email=entry.email,
            display_name=entry.display_name,
            group_name=entry.group_name,
            role=entry.role,
            detected_phone=entry.detected_phone,
            call_count=entry.call_count,
            truncated=entry.truncated,
            linked_agent_id=linked.get(entry.external_id.strip().lower()),
        )
        for entry in entries
    ]


@router.post(
    "/moizvonki/import",
    response_model=ImportResult,
    summary="Tanlangan MoyZvonki xodimlarini yaratish",
    dependencies=[Depends(require_permission("agents:sync"))],
)
async def import_employees(payload: ImportRequest, session: DbSession):
    """Tanlangan xodimlarni yaratadi yoki mavjudiga `external_id` yozadi.

    IDEMPOTENT: shu `external_id` bilan xodim allaqachon bo'lsa
    hech narsa qilinmaydi (`skipped`). Ismi bo'yicha mos keladigan,
    lekin `external_id` siz xodim topilsa — unga yoziladi (`linked`),
    ya'ni qo'lda kiritilgan xodim dublikat bo'lib ketmaydi.
    """
    service = AgentService(session)
    created = linked = skipped = 0

    for row in payload.agents:
        marker = row.external_id.strip()
        existing = (
            await session.execute(
                select(AgentModel).where(AgentModel.external_id == marker)
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue

        by_name = (
            await session.execute(
                select(AgentModel).where(
                    func.lower(AgentModel.full_name) == row.full_name.strip().lower(),
                    AgentModel.external_id.is_(None),
                )
            )
        ).scalars().first()

        if by_name is not None:
            by_name.external_id = marker
            if row.phone and not by_name.phone:
                by_name.phone = row.phone
            linked += 1
            continue

        await service.create(
            {
                "full_name": row.full_name.strip(),
                "region": row.region.strip(),
                "phone": row.phone,
                "external_id": marker,
                "hired_at": None,
                "color": "#6366f1",
            }
        )
        created += 1

    await session.flush()
    return ImportResult(created=created, linked=linked, skipped=skipped)


#: Hudud aniqlanmaganda qo'yiladigan belgi.
#
# MoyZvonki xodimda HUDUD MAYDONI YO'Q — u faqat bo'lim beradi
# («Савдо булими», «Вилоят складлари»). Bo'limni hudud deb yozib
# qo'yish yolg'on bo'lardi va hudud filtrini ifloslantirardi.
#
# Bu «xato» emas, «hali to'ldirilmagan»: `agents.region` — xodim
# YASHAYDIGAN joy, u xizmat ko'rsatadigan hududlar esa Telegram
# guruhlaridan yig'iladi (`regions`). Ya'ni bu maydon bo'sh bo'lsa
# ham tizim to'liq ishlaydi, admin uni bo'sh vaqtida to'ldiradi.
UNKNOWN_REGION = "Aniqlanmagan"


class ImportAllRequest(BaseModel):
    region: str = Field(
        default=UNKNOWN_REGION,
        min_length=2,
        max_length=100,
        description="Yangi yaratilganlarga qo'yiladigan hudud",
    )
    detect_phones: bool = Field(
        default=True,
        description=(
            "Telefon raqamini oxirgi kunlar qo'ng'iroqlaridan aniqlash. "
            "Raqam Telegram orqali ro'yxatdan o'tish uchun kerak, lekin "
            "aniqlash bir necha soniya oladi."
        ),
    )


class ImportAllResult(BaseModel):
    total: int
    """MoyZvonki'da jami nechta xodim bor."""
    created: int
    linked: int
    """Ismi bo'yicha topilgan, `external_id` si to'ldirilgan xodimlar."""
    skipped: int
    """Allaqachon bog'langanlar — ULARGA TEGILMADI."""
    created_names: list[str]
    message: str


@router.post(
    "/moizvonki/import-all",
    response_model=ImportAllResult,
    summary="MoyZvonki'dagi BARCHA xodimni olish (faqat admin)",
)
async def import_all_employees(
    payload: ImportAllRequest, session: DbSession, _: RequireAdmin
) -> ImportAllResult:
    """Bitta tugma: MoyZvonki'dagi hamma xodim tizimga tushadi.

    ⚠️ MAVJUDLARGA TEGILMAYDI. Bu amal faqat YETISHMAYOTGANINI
    yaratadi:

      · `external_id` bo'yicha topilsa — o'tkazib yuboriladi
        (`skipped`). Ismi, hududi, telefoni, rangi — hech biri
        qayta yozilmaydi;
      · `external_id` siz, ismi mos xodim topilsa — unga faqat
        `external_id` (va bo'sh bo'lsa telefon) yoziladi (`linked`),
        ya'ni qo'lda kiritilgan xodim dublikat bo'lib ketmaydi;
      · qolganlari yangi savdo xodimi sifatida yaratiladi (`created`).

    Shu sababli buyruqni necha marta bosish xavfsiz: ikkinchi safar
    `created` nolga tushadi.
    """
    lookback = PHONE_LOOKBACK_DAYS if payload.detect_phones else 0
    async with moizvonki_client(session) as client:
        if payload.detect_phones:
            entries = await load_directory(client, lookback_days=lookback)
            rows = [(e.external_id, e.display_name, e.email, e.detected_phone) for e in entries]
        else:
            # Raqamsiz — qo'ng'iroqlar skanerlanmaydi, javob darhol keladi
            rows = [
                (e.id, e.display_name, e.email, None)
                for e in await client.list_employees()
            ]

    service = AgentService(session)
    created = linked = skipped = 0
    created_names: list[str] = []

    for external_id, display_name, email, phone in rows:
        marker = (external_id or "").strip()
        if not marker:
            continue

        # Ism bo'lmasa email'dan, u ham bo'lmasa identifikatordan —
        # nomsiz xodim ro'yxatda ko'rinmay qolmasin
        name = (display_name or "").strip() or (email or "").strip() or f"MoyZvonki #{marker}"

        exists = (
            await session.execute(
                select(AgentModel).where(AgentModel.external_id == marker)
            )
        ).scalar_one_or_none()
        if exists is not None:
            skipped += 1
            continue

        by_name = (
            (
                await session.execute(
                    select(AgentModel).where(
                        func.lower(AgentModel.full_name) == name.lower(),
                        AgentModel.external_id.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if by_name is not None:
            by_name.external_id = marker
            if phone and not by_name.phone:
                by_name.phone = phone
            linked += 1
            continue

        await service.create(
            {
                "full_name": name[:255],
                "region": payload.region.strip(),
                "phone": phone,
                "external_id": marker,
                "hired_at": None,
                "color": "#6366f1",
            }
        )
        created += 1
        created_names.append(name)

    await session.flush()

    parts = [f"MoyZvonki'da {len(rows)} ta xodim"]
    parts.append(f"{created} tasi yangi qo'shildi")
    if linked:
        parts.append(f"{linked} tasi mavjud xodimga bog'landi")
    if skipped:
        parts.append(f"{skipped} tasi allaqachon bor edi — tegilmadi")

    return ImportAllResult(
        total=len(rows),
        created=created,
        linked=linked,
        skipped=skipped,
        created_names=created_names,
        message=". ".join(parts),
    )


# ══════════════════════════════════════════════════════════════
#  XODIMNI O'CHIRISH — FAQAT ADMIN
#
#  MoyZvonki'dan BARCHA xodim tortiladi (nafaqat savdo menejerlari),
#  chunki kimning ma'lumoti kerak bo'lishini oldindan bilib bo'lmaydi.
#  Ortiqchasini keyin o'chirib tashlash kerak — shu blok o'shani
#  qiladi.
#
#  ⚠️ MA'LUMOT HECH QACHON YO'QOLMAYDI.
#
#  `calls.agent_id` va `surveys.agent_id` da `ON DELETE CASCADE` bor:
#  xodim qatori o'chsa, uning qo'ng'iroqlari, transkriptlari, BAHOLARI
#  va mijoz javoblari ham o'chib ketadi — oylar davomida yig'ilgan ish
#  natijasi. Shuning uchun tizimda bunday yo'l UMUMAN YO'Q:
#
#    · bog'liq ma'lumoti YO'Q xodim → qatori butunlay o'chadi;
#    · ma'lumoti BOR xodim         → ARXIVGA o'tadi (`archived_at`).
#      Ekranlardan, filtrlardan va guruh biriktirishdan yo'qoladi,
#      qatori esa qoladi — qo'ng'iroqlari kimga tegishli ekani
#      bilinib turadi.
#
#  Qaror AVTOMATIK: admin «force» tugmasini izlab, xato bosib
#  qo'yishi mumkin bo'lgan holat yaratilmagan.
#
#  ⚠️ `/{agent_id}` DAN OLDIN turishi shart: FastAPI marshrutlarni
#     e'lon tartibida solishtiradi.
# ══════════════════════════════════════════════════════════════


class DeleteRequest(BaseModel):
    agent_ids: list[UUID] = Field(min_length=1, max_length=500)


class DeletionImpact(BaseModel):
    """Shu xodim o'chirilsa NIMA yo'qoladi."""

    agent_id: UUID
    full_name: str

    calls: int
    """Qo'ng'iroqlar — transkript va baholari bilan BIRGA o'chadi."""
    scores: int
    surveys: int
    survey_responses: int

    groups: int
    """Telegram guruhlari — o'chmaydi, faqat biriktirish uziladi."""
    clients: int
    """Mijozlar — o'chmaydi, faqat biriktirish uziladi."""
    users: int
    """Bog'langan tizim hisobi — o'chmaydi, lekin xodimsiz qoladi."""

    safe: bool
    """`true` — bog'liq ma'lumoti yo'q, qatori butunlay o'chiriladi.
    `false` — arxivga o'tadi, ma'lumoti saqlanadi."""
    blockers: list[str]
    """Nega arxivga o'tishi — o'zbekcha, admin o'qishi uchun."""


class DeleteResult(BaseModel):
    deleted: list[UUID]
    """Qatori butunlay o'chirildi — ularda saqlanadigan narsa yo'q edi."""
    archived: list[DeletionImpact]
    """Ekranlardan olib tashlandi, MA'LUMOTI SAQLANDI."""
    kept_calls: int
    """Arxivlash tufayli saqlanib qolgan qo'ng'iroqlar."""
    kept_surveys: int
    message: str


async def _impact(session: DbSession, agent: AgentModel) -> DeletionImpact:
    """Bitta xodim bo'yicha bog'liqliklarni sanaydi."""

    async def count(model, column) -> int:
        return int(
            (
                await session.execute(
                    select(func.count()).select_from(model).where(column == agent.id)
                )
            ).scalar_one()
        )

    calls = await count(CallModel, CallModel.agent_id)
    surveys = await count(SurveyModel, SurveyModel.agent_id)
    groups = await count(TelegramGroupModel, TelegramGroupModel.agent_id)
    clients = await count(ClientModel, ClientModel.agent_id)
    users = await count(UserModel, UserModel.agent_id)

    scores = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CallScoreModel)
                .join(CallModel, CallModel.id == CallScoreModel.call_id)
                .where(CallModel.agent_id == agent.id)
            )
        ).scalar_one()
    )
    responses = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SurveyResponseModel)
                .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
                .where(SurveyModel.agent_id == agent.id)
            )
        ).scalar_one()
    )

    blockers: list[str] = []
    if calls:
        blockers.append(
            f"{calls} ta qo'ng'iroq"
            + (f" ({scores} tasi baholangan)" if scores else "")
            + " saqlanadi"
        )
    if surveys:
        blockers.append(
            f"{surveys} ta so'rovnoma"
            + (f" va {responses} ta mijoz javobi" if responses else "")
            + " saqlanadi"
        )
    if users:
        blockers.append(f"{users} ta tizim hisobi bog'langan")

    return DeletionImpact(
        agent_id=agent.id,
        full_name=agent.full_name,
        calls=calls,
        scores=scores,
        surveys=surveys,
        survey_responses=responses,
        groups=groups,
        clients=clients,
        users=users,
        safe=not blockers,
        blockers=blockers,
    )


@router.post(
    "/deletion-impact",
    response_model=list[DeletionImpact],
    summary="O'chirishdan oldin: nima yo'qoladi",
)
async def deletion_impact(
    payload: DeleteRequest, session: DbSession, _: RequireAdmin
) -> list[DeletionImpact]:
    """Tasdiqlash oynasi shu javob asosida chiziladi.

    Hech narsa o'zgartirmaydi — faqat sanaydi.
    """
    agents = (
        await session.execute(
            select(AgentModel).where(AgentModel.id.in_(payload.agent_ids))
        )
    ).scalars().all()
    return [await _impact(session, agent) for agent in agents]


@router.post(
    "/delete",
    response_model=DeleteResult,
    summary="Xodimlarni o'chirish (faqat admin)",
)
async def delete_agents(
    payload: DeleteRequest, session: DbSession, _: RequireAdmin
) -> DeleteResult:
    """Tanlangan xodimlarni tizimdan olib tashlaydi.

    ⚠️ MA'LUMOT HECH QACHON YO'QOLMAYDI. Har bir xodim uchun qaror
    AVTOMATIK, uning bog'liq ma'lumotiga qarab:

      · bog'liq ma'lumoti YO'Q  → qatori butunlay o'chadi
        (yo'qoladigan narsaning o'zi yo'q);
      · qo'ng'iroq, so'rovnoma yoki hisobi BOR → ARXIVGA o'tadi.
        Ekranlardan, filtrlardan va guruh biriktirishdan yo'qoladi,
        lekin qatori qoladi — shuning uchun uning qo'ng'iroqlari,
        transkriptlari va baholari joyida turadi va kimga tegishli
        ekani ham bilinib turadi.

    Nega shunday: `calls.agent_id` da `ON DELETE CASCADE` bor. Xodim
    qatori o'chsa, uning butun ish tarixi ham o'chib ketardi. Buni
    «force» tugmasi ortiga yashirish xavfli — bir marta bosilsa
    qaytarib bo'lmaydi. Shuning uchun bunday yo'l UMUMAN YO'Q.

    Arxivdan qaytarish mumkin: xodimni tahrirlashda arxivdan chiqariladi.
    """
    agents = (
        (
            await session.execute(
                select(AgentModel).where(AgentModel.id.in_(payload.agent_ids))
            )
        )
        .scalars()
        .all()
    )

    service = AgentService(session)
    deleted: list[UUID] = []
    archived: list[DeletionImpact] = []
    kept_calls = kept_surveys = 0

    for agent in agents:
        impact = await _impact(session, agent)

        if impact.safe:
            # Avatar fayli bazada emas, diskda — kaskad uni olmaydi
            if agent.avatar_url:
                delete_avatar(agent.id)
            await session.delete(agent)
            deleted.append(agent.id)
            continue

        # Arxiv: guruhlari ham bo'shatiladi, aks holda arxivdagi xodim
        # jimgina 12 ta guruhni ushlab turaverardi
        await service.update(
            agent.id, {"is_active": False, "archived_at": datetime.now(UTC)}
        )
        archived.append(impact)
        kept_calls += impact.calls
        kept_surveys += impact.surveys

    await session.flush()

    parts: list[str] = []
    if deleted:
        parts.append(f"{len(deleted)} ta xodim butunlay o'chirildi")
    if archived:
        parts.append(f"{len(archived)} tasi arxivga o'tdi")
        saqlangan = []
        if kept_calls:
            saqlangan.append(f"{kept_calls} ta qo'ng'iroq")
        if kept_surveys:
            saqlangan.append(f"{kept_surveys} ta so'rovnoma")
        if saqlangan:
            parts.append(" va ".join(saqlangan) + " saqlanib qoldi")
    if not parts:
        parts.append("Hech narsa o'zgarmadi")

    return DeleteResult(
        deleted=deleted,
        archived=archived,
        kept_calls=kept_calls,
        kept_surveys=kept_surveys,
        message=". ".join(parts),
    )


@router.post(
    "/restore",
    response_model=DeleteResult,
    summary="Arxivdan qaytarish (faqat admin)",
)
async def restore_agents(
    payload: DeleteRequest, session: DbSession, _: RequireAdmin
) -> DeleteResult:
    """Arxivlangan xodimni ishchi ro'yxatga qaytaradi.

    Guruhlari AVTOMATIK qaytarilmaydi — ular orada boshqa xodimga
    berilgan bo'lishi mumkin. Kim qaysi guruhni oladi — adminning
    qarori (`AgentService.update` dagi bir xil qoida).
    """
    agents = (
        (
            await session.execute(
                select(AgentModel).where(
                    AgentModel.id.in_(payload.agent_ids),
                    AgentModel.archived_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    service = AgentService(session)
    for agent in agents:
        await service.update(agent.id, {"archived_at": None, "is_active": True})
    await session.flush()

    return DeleteResult(
        deleted=[],
        archived=[],
        kept_calls=0,
        kept_surveys=0,
        message=f"{len(agents)} ta xodim arxivdan qaytarildi",
    )


# ══════════════════════════════════════════════════════════════
#  Bot uchun ichki endpoint — ro'yxatdan o'tish
#
#  ⚠️ `/{agent_id}` DAN OLDIN turishi shart: FastAPI marshrutlarni
#     e'lon tartibida solishtiradi.
# ══════════════════════════════════════════════════════════════


class EnrollRequest(BaseModel):
    phone: str = Field(
        min_length=5,
        max_length=32,
        description=(
            "Telegram `contact.phone_number`. Istalgan shaklda: "
            "`+998 90 123-45-67`, `998901234567`, `901234567`"
        ),
    )
    telegram_user_id: int = Field(
        description="Telegram `contact.user_id` — o'zgarmas identifikator"
    )
    telegram_username: str | None = Field(default=None, max_length=64)


class EnrollResponse(BaseModel):
    matched: bool
    """`false` — bunday raqamli FAOL xodim topilmadi. Bot foydalanuvchiga
    «Raqamingiz tizimda topilmadi» deb javob beradi."""
    agent_id: UUID | None = None
    full_name: str | None = None
    bound_groups: int | None = None
    """Shu xodimga hozir biriktirilgan guruhlar soni — bot xodimga
    «Sizga 12 ta guruh biriktirilgan» deb tasdiq ko'rsatadi."""


@router.post(
    "/enroll",
    response_model=EnrollResponse,
    summary="[ichki] Xodimni Telegram raqami bo'yicha ro'yxatga olish",
    dependencies=[InternalOnly],
)
async def enroll_agent(payload: EnrollRequest, session: DbSession):
    """Bot xodimning kontaktini olganda chaqiradi (bir martalik).

    **Telegram cheklovi:** bot guruh a'zosining raqamini ko'ra olmaydi —
    Bot API dagi `User` obyektida `phone_number` maydoni umuman yo'q.
    Yagona yo'l — xodimning o'zi `request_contact` tugmasi orqali
    yuborishi. Shundan keyin hammasi avtomatik: bot guruhda ko'rgan
    `user_id` backendda xodimga aylanadi.

    Raqam **normallashtirilgan** holda solishtiriladi: faqat raqamlar
    qoldirilib, **oxirgi 9 ta** bo'yicha. Ya'ni `+998 90 123-45-67`,
    `998901234567` va `901234567` — bitta xodim.

    Topilmasa **200** va `matched: false` qaytadi, xato emas: begona
    odam ham botni ochib raqam yuborishi mumkin, bu istisno holat emas.
    """
    return await AgentService(session).enroll(
        phone=payload.phone,
        telegram_user_id=payload.telegram_user_id,
        telegram_username=payload.telegram_username,
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Bitta xodim",
    dependencies=[Depends(require_permission("agents:read"))],
)
async def get_agent(agent_id: UUID, session: DbSession):
    """`bound_groups` bilan — faolsizlantirishdan oldin ogohlantirish uchun."""
    return await AgentService(session).get_one(agent_id)


@router.patch("/{agent_id}", response_model=AgentResponse, summary="Xodimni tahrirlash")
async def update_agent(
    agent_id: UUID,
    payload: AgentUpdateRequest,
    session: DbSession,
    _: RequireAdmin,
):
    """`is_active: false` — xodim ishdan ketdi.

    Unga biriktirilgan guruhlar AVTOMATIK bo'shatiladi (`agent_id`,
    `bound_at` → `null`; `region` saqlanadi) va ularning navbatdagi
    so'rovnomalari `expired` qilinadi. Nechta guruh bo'shagani javobdagi
    `freed_groups` da qaytadi. Qayta faollashtirish hech narsani
    qaytarmaydi — biriktirishni admin o'zi qiladi.
    """
    return await AgentService(session).update(
        agent_id, payload.model_dump(exclude_unset=True)
    )


# ── Profil rasmi ──────────────────────────────────────────────


def _require_manage(user: CurrentUser) -> None:
    """Rasm yuklash `agents:write` ruxsatini talab qiladi.

    Bu ruxsat adminda doim bor; menejerga esa
    Sozlamalar → Ruxsatlar orqali beriladi.
    """
    if not has_permission(user.role, "agents:write"):
        raise ForbiddenError("Savdo xodimlarini boshqarish ruxsati yo'q")


@router.post(
    "/{agent_id}/avatar",
    response_model=AgentResponse,
    summary="Profil rasmini yuklash",
)
async def upload_avatar(
    agent_id: UUID,
    session: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    """Rasm 256×256 WebP ga normallashtiriladi (~10 KB)."""
    _require_manage(user)

    agent = await session.get(AgentModel, agent_id)
    if agent is None:
        raise NotFoundError("Xodim topilmadi")

    raw = await file.read()
    agent.avatar_url = save_avatar(agent_id, raw, file.content_type)
    await session.flush()
    return await AgentService(session).serialize(agent)


@router.delete(
    "/{agent_id}/avatar",
    response_model=AgentResponse,
    summary="Profil rasmini o'chirish",
)
async def remove_avatar(agent_id: UUID, session: DbSession, user: CurrentUser):
    _require_manage(user)

    agent = await session.get(AgentModel, agent_id)
    if agent is None:
        raise NotFoundError("Xodim topilmadi")

    delete_avatar(agent_id)
    agent.avatar_url = None
    await session.flush()
    return await AgentService(session).serialize(agent)
