"""Analitika endpointlari — dashboard shu yerdan ma'lumot oladi."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.deps import CurrentUser, DbSession
from src.modules.analytics.application.services import AnalyticsFilter, AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _inclusive_end(date_to: datetime | None) -> datetime | None:
    """`date_to` ni KUN OXIRIGA suradi — agar unda vaqt ko'rsatilmagan bo'lsa.

    ⚠️ NEGA KERAK. Filtr sharti `started_at <= date_to`. Foydalanuvchi
    «16-avgustgacha» deb tanlaganda frontend `2026-08-16` yuboradi va u
    `2026-08-16T00:00:00` ga aylanadi — natijada o'sha kunning BUTUN
    qo'ng'iroqlari tushib qolardi. Ekranda «bugungacha» so'ralib,
    bugungi ish ko'rinmasdi.

    Aniq vaqt berilgan bo'lsa (soat/daqiqa/soniya noldan farqli) hech
    narsa o'zgartirilmaydi: chaqiruvchi nima so'ragan bo'lsa o'sha.

    ⚠️ Bu qoida `surveys/presentation/router.py` dagi `_period()` bilan
    BIR XIL bo'lishi shart — aks holda ikkala sahifa bitta davr uchun
    ikki xil son ko'rsatadi.
    """
    if date_to is None:
        return None
    if (date_to.hour, date_to.minute, date_to.second, date_to.microsecond) != (
        0,
        0,
        0,
        0,
    ):
        return date_to
    return date_to + timedelta(days=1) - timedelta(microseconds=1)


def build_filter(
    date_from: Annotated[datetime | None, Query(description="Boshlanish sanasi")] = None,
    date_to: Annotated[datetime | None, Query(description="Tugash sanasi")] = None,
    agent_ids: Annotated[list[UUID] | None, Query(description="Xodimlar")] = None,
    regions: Annotated[list[str] | None, Query(description="Hududlar")] = None,
    score_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    score_max: Annotated[int | None, Query(ge=0, le=100)] = None,
    has_red_flags: Annotated[bool | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=365, description="Oxirgi N kun")] = 30,
) -> AnalyticsFilter:
    """Query parametrlarini filtrga aylantiradi.

    `date_from` berilmasa — oxirgi `days` kun olinadi.
    """
    now = datetime.now(UTC)
    return AnalyticsFilter(
        date_from=date_from or (now - timedelta(days=days)),
        date_to=_inclusive_end(date_to) or now,
        agent_ids=list(agent_ids) if agent_ids else None,
        regions=list(regions) if regions else None,
        score_min=score_min,
        score_max=score_max,
        has_red_flags=has_red_flags,
    )


Filters = Annotated[AnalyticsFilter, Depends(build_filter)]


@router.get("/overview", summary="KPI kartalar")
async def overview(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).overview(f)


@router.get("/timeseries", summary="Vaqt bo'yicha trend")
async def timeseries(
    session: DbSession,
    user: CurrentUser,
    f: Filters,
    bucket: Literal["day", "week", "month"] = "day",
):
    return await AnalyticsService(session, user).timeseries(f, bucket)


@router.get("/agents", summary="Xodimlar reytingi")
async def agents(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).agent_leaderboard(f)


@router.get("/blocks", summary="Rubrika bloklari bo'yicha razrez")
async def blocks(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).block_breakdown(f)


@router.get("/red-flags", summary="Qoidabuzarliklar razrezi")
async def red_flags(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).red_flag_breakdown(f)


@router.get("/distribution", summary="Ball taqsimoti")
async def distribution(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).score_distribution(f)


@router.get("/regions", summary="Hududlar bo'yicha")
async def regions(session: DbSession, user: CurrentUser, f: Filters):
    return await AnalyticsService(session, user).by_region(f)


@router.get("/filters", summary="Filtr variantlari")
async def filter_options(session: DbSession, user: CurrentUser):
    return await AnalyticsService(session, user).filter_options()
