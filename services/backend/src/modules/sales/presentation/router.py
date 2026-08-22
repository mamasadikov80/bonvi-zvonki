"""«Savdo nazorati» endpointlari (shartnomaning 7.1-bo'limi).

Oltita yo'l bor va ular ikki xil ishni bajaradi:

  · MA'LUMOT KIRITISH — `POST /sales/import` (SAP eksporti);
  · NAZORAT — ro'yxat, hisobot, qaror va filial → xodim xaritasi.

⚠️ RUXSAT `sales:*` — ADMIN va MANAGER da. SALES va VIEWER da YO'Q va
`:own` ko'rinishi ham yo'q: bu ro'yxat XODIM USTIDAN olib boriladigan
tekshiruv. Xodim o'z savdosi shubhali deb belgilanganini ko'rsa,
tekshiruvdan oldin tayyorgarlik ko'rish imkoni tug'iladi;
televizordagi monitor (VIEWER) uchun esa bu umuman ochiq ma'lumot
emas.
"""

from dataclasses import asdict
from datetime import date, datetime
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field

from src.core.deps import CurrentUser, DbSession, require_permission
from src.modules.sales.application.branches import BranchRow, assign_branch, list_branches
from src.modules.sales.application.compliance import (
    ComplianceFilter,
    ComplianceService,
    ComplianceSort,
    ComplianceSummary,
    ReviewState,
    Rule,
    Verdict,
    resolve_window_days,
)
from src.modules.sales.application.importer import import_file
from src.modules.sales.application.reader import SalesFileError
from src.modules.sales.application.review import save_review
from src.modules.sales.domain.entities import SaleReviewReason, SaleReviewStatus

router = APIRouter(prefix="/sales", tags=["Sales"])

CanRead = Depends(require_permission("sales:read"))
CanReview = Depends(require_permission("sales:review"))
CanImport = Depends(require_permission("sales:import"))

#: Yuklanadigan faylning eng katta hajmi.
#
# O'lchandi: eng katta haqiqiy eksport (kontragentlar katalogi, 3746
# qator) 394 KB. 20 MB — bir yillik registr uchun ham ortig'i bilan
# yetadi. Chegara BOR bo'lishi shart: `openpyxl` faylni butunlay
# xotiraga ochadi va bir necha yuz megabaytli fayl butun jarayonni
# o'ldirardi.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: Qabul qilinadigan yagona kengaytma.
#
# ⚠️ `.xls` (eski ikkilik format) va `.csv` ATAYLAB rad etiladi:
# `openpyxl` ularni o'qiy olmaydi va xato tushunarsiz bo'lardi
# («File is not a zip file»). SAP ikkalasini ham `.xlsx` qilib
# beradi, ya'ni foydalanuvchi hech nima yo'qotmaydi.
ALLOWED_SUFFIX = ".xlsx"


# ══════════════════════════════════════════════════════════════
#  Javob shakllari
# ══════════════════════════════════════════════════════════════


class ImportReportOut(BaseModel):
    """Import natijasi. Har son ALOHIDA savolga javob beradi."""

    kind: str
    source: str
    read: int
    created: int
    updated: int
    skipped: int
    unknown_partner: int
    unknown_op_type: int
    phones_filled: int
    linked_sales: int
    unmatched_branches: list[str]


class ReviewOut(BaseModel):
    status: str
    reason: str | None = None
    note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class ComplianceItem(BaseModel):
    """Ro'yxatdagi bitta savdo — SAP fakti, xulosa va DALIL.

    Dalil maydonlari (`last_call_at` … `calls_total`) ixtiyoriy emas:
    rahbar sonni qo'lda qayta hisoblab tekshiradi (shartnoma, 4-bo'lim).
    """

    id: UUID
    occurred_on: date
    external_id: str
    partner_code: str
    partner_name: str | None = None
    phone: str | None = None
    phone_key: str | None = None
    branch: str | None = None
    direction: str | None = None
    agent_id: UUID | None = None
    agent_name: str | None = None
    amount: float | None = None
    currency: str
    amount_usd: float | None = None

    verdict: str
    broken_rules: list[str]
    skip_reason: str | None = None

    last_call_at: datetime | None = None
    last_call_agent: str | None = None
    days_before: int | None = None
    previous_sale_on: date | None = None
    calls_between: int
    calls_total: int

    review: ReviewOut | None = None


class PaginatedCompliance(BaseModel):
    items: list[ComplianceItem]
    total: int
    page: int
    page_size: int
    window_days: int
    """Qaysi oyna bilan hisoblangani — ekranda ochiq yoziladi."""


class AgentBreakdownOut(BaseModel):
    agent_id: UUID | None = None
    agent_name: str | None = None
    sales: int
    ok: int
    suspicious: int
    not_checkable: int
    new: int
    justified: int
    confirmed: int


class SummaryOut(BaseModel):
    total: int
    ok: int
    suspicious: int
    not_checkable: int
    new: int
    justified: int
    confirmed: int
    window_days: int
    agents: list[AgentBreakdownOut]


class BranchOut(BaseModel):
    branch: str
    agent_id: UUID | None = None
    agent_name: str | None = None
    matched_automatically: bool
    sales: int


class BranchAssignIn(BaseModel):
    agent_id: UUID | None = Field(
        default=None,
        description="Xodim. `null` — biriktirishni bekor qiladi.",
    )


class ReviewIn(BaseModel):
    status: SaleReviewStatus
    reason: SaleReviewReason | None = Field(
        default=None,
        description="Faqat «oqlandi» uchun: kelib oldi / Telegram / vizit…",
    )
    note: str | None = None


# ══════════════════════════════════════════════════════════════
#  Import
# ══════════════════════════════════════════════════════════════


@router.post(
    "/import",
    response_model=ImportReportOut,
    summary="SAP eksportini yuklash (registr / katalog / balans)",
    dependencies=[CanImport],
)
async def import_sales(
    session: DbSession,
    file: Annotated[UploadFile, File(description="`.xlsx` eksport fayli")],
) -> ImportReportOut:
    """Fayl TURI SARLAVHA bo'yicha aniqlanadi, nomiga qaralmaydi.

    Foydalanuvchi faylni har safar boshqacha nomlaydi («Workbook3»,
    «wb3», «savdo kunlik») — nomga tayanish jimgina noto'g'ri importga
    olib borardi.
    """
    name = (file.filename or "").strip()
    if not name.lower().endswith(ALLOWED_SUFFIX):
        raise SalesFileError(
            f"«{name or 'fayl'}» — faqat `.xlsx` fayl qabul qilinadi. "
            "SAP dan eksport qilishda «Excel» formatini tanlang."
        )

    # Bir belgi ortig'i bilan o'qiymiz — chegaraga TENG fayl o'tsin,
    # undan kattasi esa aniqlansin.
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise SalesFileError(
            f"Fayl juda katta ({len(payload) // (1024 * 1024)} MB). "
            f"Chegara — {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if not payload:
        raise SalesFileError("Fayl bo'sh")

    report = await import_file(session, BytesIO(payload), filename=name)
    return ImportReportOut(
        kind=str(report.kind),
        source=report.source,
        read=report.read,
        created=report.created,
        updated=report.updated,
        skipped=report.skipped,
        unknown_partner=report.unknown_partner,
        unknown_op_type=report.unknown_op_type,
        phones_filled=report.phones_filled,
        linked_sales=report.linked_sales,
        unmatched_branches=report.unmatched_branches,
    )


# ══════════════════════════════════════════════════════════════
#  Nazorat ro'yxati
# ══════════════════════════════════════════════════════════════


async def _filter(
    session: DbSession,
    *,
    date_from: date | None,
    date_to: date | None,
    agent_ids: list[UUID] | None,
    branches: list[str] | None,
    verdict: Verdict | None,
    review: ReviewState | None,
    rule: Rule | None,
    search: str | None,
) -> ComplianceFilter:
    """So'rov parametrlaridan filtr — ro'yxat va hisobotda BIR XIL."""
    return ComplianceFilter(
        since=date_from,
        until=date_to,
        agent_ids=list(agent_ids) if agent_ids else None,
        branches=list(branches) if branches else None,
        verdict=verdict.value if verdict else None,
        review=review.value if review else None,
        rule=rule.value if rule else None,
        search=search,
        window_days=await resolve_window_days(session),
    )


@router.get(
    "/compliance",
    response_model=PaginatedCompliance,
    summary="Tekshiruv navbati — savdolar va ular bo'yicha xulosa",
    dependencies=[CanRead],
)
async def compliance(
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    date_from: date | None = None,
    date_to: date | None = None,
    agent_ids: Annotated[list[UUID] | None, Query(description="Xodimlar")] = None,
    branches: Annotated[list[str] | None, Query(description="SAP filiallari")] = None,
    verdict: Annotated[
        Verdict | None, Query(description="ok | suspicious | not_checkable")
    ] = None,
    review: Annotated[
        ReviewState | None,
        Query(
            description=(
                "new — ko'rilmaganlar (sukut) | justified | confirmed | "
                "all — qarori bor-yo'qligidan qat'i nazar hammasi"
            )
        ),
    ] = ReviewState.NEW,
    rule: Annotated[Rule | None, Query(description="R1 | R2 | R3")] = None,
    search: Annotated[
        str | None, Query(description="Mijoz nomi, kodi, telefoni yoki operatsiya raqami")
    ] = None,
    sort: Annotated[ComplianceSort, Query()] = ComplianceSort.DATE,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> PaginatedCompliance:
    """Xulosa HAR SO'ROVDA qaytadan hisoblanadi, jadvalda saqlanmaydi.

    ⚠️ `review` ning sukut qiymati — `new`. Tekshiruv navbati aynan
    shu: qaror qo'yilgan savdo ro'yxatdan chiqadi, aks holda rahbar
    o'zi ko'rib bo'lgan qatorlarni har kuni qaytadan ko'rardi.
    `justified` / `confirmed` — arxiv, `all` — hammasi (oqlanganlar
    statistikasi shu ro'yxatdan o'qiladi).
    """
    f = await _filter(
        session,
        date_from=date_from,
        date_to=date_to,
        agent_ids=agent_ids,
        branches=branches,
        verdict=verdict,
        review=review,
        rule=rule,
        search=search,
    )
    result = await ComplianceService(session).page(
        f, page=page, page_size=page_size, sort=sort, order=order
    )

    return PaginatedCompliance(
        items=[
            ComplianceItem(
                id=row.id,
                occurred_on=row.occurred_on,
                external_id=row.external_id,
                partner_code=row.partner_code,
                partner_name=row.partner_name,
                phone=row.phone,
                phone_key=row.phone_key,
                branch=row.branch,
                direction=row.direction,
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                amount=row.amount,
                currency=row.currency,
                amount_usd=row.amount_usd,
                verdict=row.verdict.verdict,
                broken_rules=row.verdict.broken_rules,
                skip_reason=row.verdict.skip_reason,
                last_call_at=row.verdict.last_call_at,
                last_call_agent=row.verdict.last_call_agent,
                days_before=row.verdict.days_before,
                previous_sale_on=row.verdict.previous_sale_on,
                calls_between=row.verdict.calls_between,
                calls_total=row.verdict.calls_total,
                review=ReviewOut(**asdict(row.review)) if row.review else None,
            )
            for row in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        window_days=f.window_days,
    )


@router.get(
    "/compliance/summary",
    response_model=SummaryOut,
    summary="Toifalar soni va xodimlar kesimi",
    dependencies=[CanRead],
)
async def compliance_summary(
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    agent_ids: Annotated[list[UUID] | None, Query()] = None,
    branches: Annotated[list[str] | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> SummaryOut:
    """Uchala toifaning ham soni — hech narsa yashirilmaydi.

    ⚠️ `verdict`/`rule`/`review` parametrlari BU YERDA YO'Q va ataylab:
    hisobot ro'yxat filtriga ergashsa, «shubhalilar» tanlanganda
    «tekshirib bo'lmadi» katagi nolga tushardi va SAP ma'lumot
    sifatining ko'rsatkichi ko'rinmay qolardi.
    """
    f = await _filter(
        session,
        date_from=date_from,
        date_to=date_to,
        agent_ids=agent_ids,
        branches=branches,
        verdict=None,
        review=None,
        rule=None,
        search=search,
    )
    return _summary_out(await ComplianceService(session).summary(f))


def _summary_out(result: ComplianceSummary) -> SummaryOut:
    return SummaryOut(
        total=result.total,
        ok=result.ok,
        suspicious=result.suspicious,
        not_checkable=result.not_checkable,
        new=result.new,
        justified=result.justified,
        confirmed=result.confirmed,
        window_days=result.window_days,
        agents=[AgentBreakdownOut(**asdict(a)) for a in result.agents],
    )


# ══════════════════════════════════════════════════════════════
#  Filial → xodim
# ══════════════════════════════════════════════════════════════


@router.get(
    "/branches",
    response_model=list[BranchOut],
    summary="Filial → xodim xaritasi (dalili bilan)",
    dependencies=[CanRead],
)
async def branches(session: DbSession) -> list[BranchOut]:
    """Savdosi ko'p filial yuqorida — biriktirish shundan boshlanadi."""
    return [BranchOut(**asdict(row)) for row in await list_branches(session)]


@router.put(
    "/branches/{branch}",
    response_model=BranchOut,
    summary="Filialga xodimni qo'lda biriktirish",
    dependencies=[CanReview],
)
async def assign(
    branch: str, payload: BranchAssignIn, session: DbSession
) -> BranchOut:
    """Qo'lda qo'yilgan xodim keyingi importlarda O'ZGARMAYDI.

    Biriktirilgach shu filialdagi savdolar darhol yangi xodimga
    o'tkaziladi — aks holda hisobot eski holatda qolardi.
    """
    row: BranchRow = await assign_branch(session, branch, payload.agent_id)
    return BranchOut(**asdict(row))


# ══════════════════════════════════════════════════════════════
#  Qaror
# ══════════════════════════════════════════════════════════════


@router.post(
    "/{sale_id}/review",
    response_model=ReviewOut,
    summary="Savdo bo'yicha qaror qo'yish (oqlandi / haqiqatan shubhali)",
    dependencies=[CanReview],
)
async def review_sale(
    sale_id: UUID, payload: ReviewIn, session: DbSession, user: CurrentUser
) -> ReviewOut:
    """Bir savdoga BITTA qaror — takrori ustiga yoziladi.

    Qaror qo'yilgan savdo tekshiruv navbatidan chiqadi (`review=new`
    sukut filtri), lekin ro'yxatdan yo'qolmaydi: `review=justified`
    yoki `review=confirmed` bilan qaytib ko'rish mumkin.
    """
    result = await save_review(
        session,
        sale_id,
        status=payload.status,
        reason=payload.reason,
        note=payload.note,
        user_id=user.id,
    )
    return ReviewOut(
        status=result.status,
        reason=result.reason,
        note=result.note,
        reviewed_by=result.reviewed_by,
        reviewed_at=result.reviewed_at,
    )
