"""Analitika servisi — dashboard uchun barcha hisob-kitoblar.

Muhim prinsiplar:
  • SALES roli faqat o'z ma'lumotini ko'radi (filtr shu yerda majburlanadi)
  • Client reytingi HAR DOIM xom qiymat + `count` + `ready` bo'lib qaytadi.
    Chegara (`survey.min_responses`) sozlamalardan olinadi, nimani
    ko'rsatish esa UI qarori — shu bilan `/analytics/overview` va
    `/surveys` bitta bahoni ikki xil ko'rsatadigan holat yopildi.
  • Divergensiya (AI ↔ client farqi) gaming aniqlash uchun hisoblanadi
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallStatus, CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.scoring.domain.entities import BLOCK_LABEL_UZ, RED_FLAG_LABEL_UZ
from src.modules.scoring.infrastructure.models import CallScoreModel
from src.modules.surveys.application.services import resolve_min_responses
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.users.domain.entities import Role, User


@dataclass(slots=True)
class AnalyticsFilter:
    """Dashboard filtrlari."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    agent_ids: list[UUID] | None = None
    regions: list[str] | None = None
    score_min: int | None = None
    score_max: int | None = None
    has_red_flags: bool | None = None

    @classmethod
    def last_days(cls, days: int = 30) -> "AnalyticsFilter":
        now = datetime.now(UTC)
        return cls(date_from=now - timedelta(days=days), date_to=now)

    @property
    def period_days(self) -> int:
        if self.date_from and self.date_to:
            return max((self.date_to - self.date_from).days, 1)
        return 30


class AnalyticsService:
    def __init__(self, session: AsyncSession, user: User | None = None) -> None:
        self._session = session
        self._user = user
        # Bir so'rov ichida sozlama bir marta o'qiladi
        self._min_responses: int | None = None

    async def min_responses(self) -> int:
        """`survey.min_responses` — sozlamalardan, so'rov davomida keshlanadi."""
        if self._min_responses is None:
            self._min_responses = await resolve_min_responses(self._session)
        return self._min_responses

    # ── Ruxsat doirasi ────────────────────────────────────────

    def _scoped(self, f: AnalyticsFilter) -> AnalyticsFilter:
        """SALES roli uchun filtrni o'z agentiga majburiy toraytiradi."""
        if self._user and self._user.role == Role.SALES:
            f.agent_ids = [self._user.agent_id] if self._user.agent_id else []
        return f

    def _apply(self, stmt: Select, f: AnalyticsFilter) -> Select:
        conditions = [CallModel.status == CallStatus.COMPLETED]

        if f.date_from:
            conditions.append(CallModel.started_at >= f.date_from)
        if f.date_to:
            conditions.append(CallModel.started_at <= f.date_to)
        if f.agent_ids is not None:
            conditions.append(CallModel.agent_id.in_(f.agent_ids or [None]))
        if f.regions:
            conditions.append(AgentModel.region.in_(f.regions))
        if f.score_min is not None:
            conditions.append(CallScoreModel.overall_score >= f.score_min)
        if f.score_max is not None:
            conditions.append(CallScoreModel.overall_score <= f.score_max)
        if f.has_red_flags is True:
            conditions.append(func.jsonb_array_length(CallScoreModel.red_flags) > 0)
        elif f.has_red_flags is False:
            conditions.append(func.jsonb_array_length(CallScoreModel.red_flags) == 0)

        return stmt.where(and_(*conditions))

    # ── 1. Umumiy ko'rsatkichlar (KPI kartalar) ───────────────

    async def overview(self, f: AnalyticsFilter) -> dict[str, Any]:
        f = self._scoped(f)

        base = (
            select(
                func.count(CallModel.id).label("calls"),
                func.avg(CallScoreModel.overall_score).label("avg_score"),
                func.sum(
                    case(
                        (func.jsonb_array_length(CallScoreModel.red_flags) > 0, 1),
                        else_=0,
                    )
                ).label("red_flags"),
                func.avg(CallModel.duration_sec).label("avg_duration"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
        )
        current = (await self._session.execute(self._apply(base, f))).one()

        # Oldingi davr bilan solishtirish (trend uchun)
        prev = self._previous_period(f)
        previous = (await self._session.execute(self._apply(base, prev))).one()

        client_rating = await self._avg_client_rating(f)
        prev_rating = await self._avg_client_rating(prev)
        call_types = await self._call_type_counts(f)

        def delta(now: float | None, before: float | None) -> float | None:
            if now is None or before is None or before == 0:
                return None
            return round(((now - before) / before) * 100, 1)

        return {
            "calls": {
                "value": current.calls or 0,
                "delta_percent": delta(current.calls, previous.calls),
            },
            # ⚠️ Yuqoridagi `calls` — BAHOLANGAN qo'ng'iroqlar soni
            # (so'rovda `CallScoreModel` ga INNER JOIN bor). Savdo
            # bo'lmagan suhbatda baho qatori ataylab yozilmaydi, ya'ni
            # ular bu songa KIRMAYDI.
            #
            # Shu sabab tur bo'yicha taqsimot kerak. Bo'lmasa menejer
            # 172 ta qo'ng'iroq bo'lgan davrda «6» degan raqamni ko'rib,
            # qolgan 166 tasi qayerga ketganini bilmaydi — bu tizim
            # ma'lumot yo'qotgandek ko'rinadi. Aslida ular joyida,
            # shunchaki savdo suhbati emas.
            "call_types": call_types,
            "calls_total": sum(call_types.values()),
            "ai_score": {
                "value": round(float(current.avg_score), 1) if current.avg_score else None,
                "delta_percent": delta(
                    float(current.avg_score) if current.avg_score else None,
                    float(previous.avg_score) if previous.avg_score else None,
                ),
            },
            # Xom qiymat + soni + `ready` — `GET /surveys` bilan bir xil
            # qoida. UI `ready=false` da raqamni chizmasligi kerak.
            "client_rating": {
                "value": client_rating["value"],
                "count": client_rating["count"],
                "ready": client_rating["ready"],
                "min_responses": client_rating["min_responses"],
                "delta_percent": delta(client_rating["value"], prev_rating["value"]),
            },
            "red_flags": {
                "value": int(current.red_flags or 0),
                "delta_percent": delta(current.red_flags, previous.red_flags),
            },
            # `int()` EMAS: u kesadi, yaxlitlamaydi — 695.53 s -> 695 s
            # bo'lib xato har doim pastga qarab siljirdi.
            "avg_duration_sec": (
                round(float(current.avg_duration))
                if current.avg_duration is not None
                else 0
            ),
        }

    async def _call_type_counts(self, f: AnalyticsFilter) -> dict[str, int]:
        """Tur bo'yicha qo'ng'iroq soni. Baho bilan bog'lanmaydi.

        ⚠️ `_apply` ISHLATILMAYDI. U `CallScoreModel` ga tayanadigan
        shartlar qo'shadi (`score_min`, `has_red_flags`) — bahosi
        bo'lmagan qatorda ular NULL beradi va savdo bo'lmagan
        qo'ng'iroqlarning hammasi yo'qolardi, ya'ni bu razrez aynan
        ko'rsatishi kerak bo'lgan narsani ko'rsatmasdi.

        Shuning uchun faqat qo'ng'iroqning O'ZIGA tegishli filtrlar
        qo'llanadi: sana, xodim, hudud.
        """
        conditions = [CallModel.status == CallStatus.COMPLETED]
        if f.date_from:
            conditions.append(CallModel.started_at >= f.date_from)
        if f.date_to:
            conditions.append(CallModel.started_at <= f.date_to)
        if f.agent_ids is not None:
            conditions.append(CallModel.agent_id.in_(f.agent_ids or [None]))
        if f.regions:
            conditions.append(AgentModel.region.in_(f.regions))

        rows = (
            await self._session.execute(
                select(CallModel.call_type, func.count(CallModel.id))
                .select_from(CallModel)
                .join(AgentModel, AgentModel.id == CallModel.agent_id)
                .where(and_(*conditions))
                .group_by(CallModel.call_type)
            )
        ).all()

        # Barcha turlar HAR DOIM javobda bo'ladi, nol bo'lsa ham: UI
        # kalitlarni o'zi to'ldirmasligi kerak, aks holda backend va
        # frontend ro'yxatlari ajralib ketadi.
        counts = {tur.value: 0 for tur in CallType}
        counts["unknown"] = 0  # hali tasniflanmagan (`call_type IS NULL`)
        for raw, count in rows:
            kalit = raw if raw in counts else "unknown"
            counts[kalit] += int(count or 0)
        return counts

    @staticmethod
    def _previous_period(f: AnalyticsFilter) -> AnalyticsFilter:
        """Solishtirish uchun oldingi, XUDDI SHUNCHA UZUN oyna.

        ⚠️ IKKI XATO shu yerda tuzatilgan:

        1. Ilgari `AnalyticsFilter(...)` qo'lda qurilardi va unga faqat
           bir necha maydon ko'chirilardi — `score_min`, `score_max`,
           `has_red_flags` TUSHIB QOLARDI. Natijada filtrlangan joriy
           davr FILTRSIZ oldingi davr bilan solishtirilardi: `score_min=95`
           da 98 ball 78 ball bilan taqqoslanib «+25.6% o'sish» chiqardi.
           Endi `replace()` — kelajakda yangi filtr qo'shilsa ham
           avtomatik ko'chadi.

        2. Oyna uzunligi `period_days` (butun KUN) bilan hisoblanardi va
           kasr qism tashlanardi — 1 soatlik oyna 24 soatlik oldingi
           oyna bilan solishtirilardi. Endi ayirma `timedelta` bo'yicha,
           ikkala oyna aynan teng.

        Yuqori chegara mikrosekundga qisqartirilgan: `date_from` ham,
        `date_to` ham inklyuziv bo'lgani uchun aynan chegarada boshlangan
        qo'ng'iroq IKKALA davrga ham tushib ketardi.
        """
        from dataclasses import replace

        if f.date_from is None or f.date_to is None:
            return replace(f)

        span = f.date_to - f.date_from
        return replace(
            f,
            date_from=f.date_from - span,
            date_to=f.date_from - timedelta(microseconds=1),
        )

    # ── Client reytingi: filtrni YAGONA joyda qo'llash ────────

    #: Bahoning hududi: so'rovnoma yuborilgan GURUHNIKI ustun, guruh
    #: bo'lmasa (eski client oqimi) xodimniki. Aynan shu ifoda
    #: `surveys/presentation/router.py` da ham ishlatiladi — ikkala
    #: sahifa bitta bahoni bitta hududga joylashi uchun.
    EFFECTIVE_RATING_REGION = func.coalesce(
        TelegramGroupModel.region, AgentModel.region
    )

    def _scope_ratings(self, stmt: Select, f: AnalyticsFilter) -> Select:
        """Reyting so'roviga davr, xodim va HUDUD filtrlarini qo'llaydi.

        ⚠️ NEGA ALOHIDA METOD. Ilgari bu shartlar uchta joyda alohida
        yozilgan edi (`_avg_client_rating`, `timeseries`,
        `_client_ratings_by_agent`) va uchalasida ham `regions` TUSHIB
        QOLGAN edi: hudud tanlanganda qo'ng'iroqlar toraya-yu, client
        bahosi butun kompaniyaniki bo'lib qolardi. Natijada bitta
        ekranda KPI kartasi 4.18, uning ostidagi jadval 4.67 ko'rsatardi.

        Endi qo'shiladigan har qanday yangi filtr uchala so'rovga ham
        avtomatik tushadi.

        `score_*` / `has_red_flags` ATAYLAB qo'llanmaydi:
        ular qo'ng'iroq xususiyatlari, baho esa qo'ng'iroqqa bog'lanmagan
        (mijoz butun davr uchun baho beradi). Ularni «qo'llagandek»
        ko'rsatish yolg'on bo'lardi.
        """
        stmt = stmt.join(AgentModel, AgentModel.id == SurveyModel.agent_id).outerjoin(
            TelegramGroupModel, TelegramGroupModel.id == SurveyModel.group_id
        )
        if f.date_from:
            stmt = stmt.where(SurveyResponseModel.responded_at >= f.date_from)
        if f.date_to:
            stmt = stmt.where(SurveyResponseModel.responded_at <= f.date_to)
        if f.agent_ids is not None:
            stmt = stmt.where(SurveyModel.agent_id.in_(f.agent_ids or [None]))
        if f.regions:
            stmt = stmt.where(self.EFFECTIVE_RATING_REGION.in_(f.regions))
        return stmt

    async def _avg_client_rating(self, f: AnalyticsFilter) -> dict[str, Any]:
        """O'rtacha client reytingi: `{value, count, ready}`.

        `value` chegaraga qarab NULL qilinmaydi — bu aynan `/surveys` bilan
        farq qilib turgan joy edi.
        """
        stmt = self._scope_ratings(
            select(
                func.avg(SurveyResponseModel.csat).label("avg"),
                func.count(SurveyResponseModel.id).label("count"),
            ).select_from(SurveyResponseModel).join(
                SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id
            ),
            f,
        )

        row = (await self._session.execute(stmt)).one()
        threshold = await self.min_responses()
        return {
            "value": round(float(row.avg), 2) if row.avg else None,
            "count": row.count,
            "ready": row.count >= threshold,
            "min_responses": threshold,
        }

    # ── 2. Vaqt qatori (AI vs client trendi) ──────────────────

    async def timeseries(self, f: AnalyticsFilter, bucket: str = "day") -> list[dict]:
        f = self._scoped(f)
        trunc = func.date_trunc(bucket, CallModel.started_at).label("period")

        stmt = (
            select(
                trunc,
                func.count(CallModel.id).label("calls"),
                func.avg(CallScoreModel.overall_score).label("ai_score"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .group_by(trunc)
            .order_by(trunc)
        )
        rows = (await self._session.execute(self._apply(stmt, f))).all()

        # Client reytingi alohida so'rov (boshqa jadval)
        rating_trunc = func.date_trunc(bucket, SurveyResponseModel.responded_at).label("period")
        rating_stmt = self._scope_ratings(
            select(rating_trunc, func.avg(SurveyResponseModel.csat).label("csat"))
            .select_from(SurveyResponseModel)
            .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id),
            f,
        ).group_by(rating_trunc).order_by(rating_trunc)

        ratings = {
            r.period.date().isoformat(): round(float(r.csat), 2)
            for r in (await self._session.execute(rating_stmt)).all()
        }

        by_period = {
            r.period.date().isoformat(): {
                "calls": r.calls,
                "ai_score": round(float(r.ai_score), 1) if r.ai_score else None,
            }
            for r in rows
        }

        # ── Bo'sh kunlarni to'ldirish ─────────────────────────
        #
        # ⚠️ Faqat qo'ng'iroq BO'LGAN kunlarni qaytarish grafikni
        # yolg'onchi qiladi: o'q toifaviy (kategoriya), ya'ni 5 ta
        # kun 7 kunlik davrda ham, 90 kunlikda ham bir xil — teng
        # oraliqda — chiziladi. Natijada admin yuqoridagi davr
        # filtrini o'zgartiradi, grafik esa qimirlamaydi va "filtr
        # ishlamayapti" degan xulosa chiqadi. Aslida ishlagan, faqat
        # ko'rinmagan.
        #
        # Endi javob TANLANGAN DAVRNI to'liq qamraydi: qo'ng'iroqsiz
        # kun `calls: 0` va `ai_score: null` bo'lib turadi. Chiziq
        # `connectNulls` bilan uzilmaydi, o'q esa haqiqiy masofani
        # ko'rsatadi.
        periods = self._bucket_starts(f.date_from, f.date_to, bucket)
        if periods is None:
            # Juda uzoq davr — to'ldirish o'rniga borini qaytaramiz.
            # Grafik baribir o'qib bo'lmas holga kelardi.
            periods = sorted(by_period)

        return [
            {
                "date": period,
                "calls": by_period.get(period, {}).get("calls", 0),
                "ai_score": by_period.get(period, {}).get("ai_score"),
                # 5 ballik reytingni 100 ballikka keltirish (bitta grafikda ko'rsatish uchun)
                "client_rating": ratings.get(period),
            }
            for period in periods
        ]

    #: To'ldirilgan nuqtalarning yuqori chegarasi. Kunlik razrezda bu
    #: ~1.5 yil — undan uzunini grafikda o'qib bo'lmaydi.
    MAX_BUCKETS = 550

    @staticmethod
    def _bucket_starts(
        date_from: datetime | None, date_to: datetime | None, bucket: str
    ) -> list[str] | None:
        """Davrdagi barcha oraliq boshlanishlari, `YYYY-MM-DD` ko'rinishida.

        PostgreSQL `date_trunc` bilan BIR XIL natija berishi shart —
        aks holda to'ldirilgan kalitlar bazadagilarga tushmaydi va
        haqiqiy qiymatlar «yo'q» bo'lib qoladi:
          · `day`   — kunning o'zi
          · `week`  — dushanba (Postgres ISO haftani dushanbadan boshlaydi)
          · `month` — oyning 1-kuni

        Chegaradan oshsa `None` — chaqiruvchi to'ldirishdan voz kechadi.
        """
        if date_from is None or date_to is None:
            return None

        start, end = date_from.date(), date_to.date()
        if start > end:
            return []

        if bucket == "day":
            step = timedelta(days=1)
            cursor = start
        elif bucket == "week":
            step = timedelta(days=7)
            cursor = start - timedelta(days=start.weekday())
        elif bucket == "month":
            step = None  # oylar uzunligi har xil — alohida yuriladi
            cursor = start.replace(day=1)
        else:
            return None

        periods: list[str] = []
        while cursor <= end:
            periods.append(cursor.isoformat())
            if len(periods) > AnalyticsService.MAX_BUCKETS:
                return None
            if step is not None:
                cursor += step
            else:
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        return periods

    # ── 3. Xodimlar reytingi (leaderboard) ────────────────────

    async def agent_leaderboard(self, f: AnalyticsFilter) -> list[dict]:
        f = self._scoped(f)
        rows = await self._leaderboard_rows(f)

        # Oldingi davrdagi o'rin — trend ustuni uchun
        prev = AnalyticsFilter(
            date_from=(f.date_from - timedelta(days=f.period_days)) if f.date_from else None,
            date_to=f.date_from,
            agent_ids=f.agent_ids,
            regions=f.regions,
        )
        prev_rank = {
            r["agent_id"]: i + 1
            for i, r in enumerate(await self._leaderboard_rows(prev))
        }

        for index, row in enumerate(rows):
            rank = index + 1
            row["rank"] = rank
            before = prev_rank.get(row["agent_id"])
            # Musbat = ko'tarildi (o'rin raqami kichraydi)
            row["rank_delta"] = (before - rank) if before else None

        return rows

    async def _leaderboard_rows(self, f: AnalyticsFilter) -> list[dict]:
        stmt = (
            select(
                AgentModel.id,
                AgentModel.full_name,
                AgentModel.region,
                AgentModel.color,
                AgentModel.avatar_url,
                func.count(CallModel.id).label("calls"),
                func.avg(CallScoreModel.overall_score).label("ai_score"),
                func.sum(
                    case(
                        (func.jsonb_array_length(CallScoreModel.red_flags) > 0, 1),
                        else_=0,
                    )
                ).label("red_flags"),
                func.avg(CallModel.duration_sec).label("avg_duration"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .group_by(
                AgentModel.id,
                AgentModel.full_name,
                AgentModel.region,
                AgentModel.color,
                AgentModel.avatar_url,
            )
            .order_by(func.avg(CallScoreModel.overall_score).desc())
        )
        rows = (await self._session.execute(self._apply(stmt, f))).all()

        ratings = await self._client_ratings_by_agent(f)

        result = []
        for r in rows:
            rating = ratings.get(r.id)
            ai = round(float(r.ai_score), 1) if r.ai_score else None

            # Divergensiya: client 5 ballik → 100 ballikka keltiriladi.
            # Faqat `ready` bo'lganda hisoblanadi: bitta bahodan chiqarilgan
            # "gaming" belgisi shovqindan boshqa narsa emas.
            divergence = None
            if (
                rating
                and rating["ready"]
                and rating["value"] is not None
                and ai is not None
            ):
                divergence = round((rating["value"] / 5 * 100) - ai, 1)

            result.append(
                {
                    "agent_id": str(r.id),
                    "full_name": r.full_name,
                    "region": r.region,
                    "color": r.color,
                    "avatar_url": r.avatar_url,
                    "calls": r.calls,
                    "ai_score": ai,
                    "client_rating": rating["value"] if rating else None,
                    "client_rating_count": rating["count"] if rating else 0,
                    "client_rating_ready": bool(rating and rating["ready"]),
                    "divergence": divergence,
                    "divergence_flag": divergence is not None and abs(divergence) >= 15,
                    "red_flags": int(r.red_flags or 0),
                    "avg_duration_sec": int(r.avg_duration or 0),
                }
            )

        # Qo'ng'irog'i yo'q, lekin bahosi bor xodimlar oxiriga qo'shiladi
        result.extend(
            await self._rated_without_calls(f, ratings, {r.id for r in rows})
        )
        return result

    @staticmethod
    def _has_call_filters(f: AnalyticsFilter) -> bool:
        """Filtr qo'ng'iroqning O'ZIGA tegishlimi?

        Shunday bo'lsa "qo'ng'irog'i yo'q" xodim ro'yxatda chiqmasligi
        kerak: foydalanuvchi aynan qo'ng'iroqlarni saralayapti.
        """
        return bool(
            f.score_min is not None
            or f.score_max is not None
            or f.has_red_flags is not None
        )

    async def _rated_without_calls(
        self,
        f: AnalyticsFilter,
        ratings: dict[UUID, dict],
        seen: set[UUID],
    ) -> list[dict]:
        """Davr ichida qo'ng'irog'i yo'q, ammo client bahosi bor xodimlar.

        Nega SQL da OUTER JOIN emas: `_apply` shartlari (`status`, ball
        oralig'i, red flag, til) qo'ng'iroq jadvaliga tegishli. Ularni
        `ON` ga ko'chirmasdan turib outer join hech narsa bermaydi
        (NULL qator baribir `WHERE` da yo'qoladi), ko'chirilsa esa mavjud
        15 xodimning raqamlari o'zgarib ketishi mumkin. Shuning uchun
        asosiy so'rov bir harf ham o'zgartirilmadi — yetishmagan qatorlar
        shu yerda qo'shiladi.

        `ai_score`, `divergence` — `None`, `calls` — 0. Ular ro'yxat
        oxirida turadi (AI balli bo'yicha saralashda joyi yo'q).
        """
        missing = [agent_id for agent_id in ratings if agent_id not in seen]
        if not missing or self._has_call_filters(f):
            return []

        stmt = (
            select(AgentModel)
            .where(AgentModel.id.in_(missing))
            .order_by(AgentModel.full_name)
        )
        if f.regions:
            stmt = stmt.where(AgentModel.region.in_(f.regions))

        agents = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "agent_id": str(agent.id),
                "full_name": agent.full_name,
                "region": agent.region,
                "color": agent.color,
                "avatar_url": agent.avatar_url,
                "calls": 0,
                "ai_score": None,
                "client_rating": ratings[agent.id]["value"],
                "client_rating_count": ratings[agent.id]["count"],
                "client_rating_ready": ratings[agent.id]["ready"],
                "divergence": None,
                "divergence_flag": False,
                "red_flags": 0,
                "avg_duration_sec": 0,
            }
            for agent in agents
        ]

    async def _client_ratings_by_agent(self, f: AnalyticsFilter) -> dict[UUID, dict]:
        stmt = self._scope_ratings(
            select(
                SurveyModel.agent_id,
                func.avg(SurveyResponseModel.csat).label("avg"),
                func.count(SurveyResponseModel.id).label("count"),
            ).select_from(SurveyResponseModel).join(
                SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id
            ),
            f,
        ).group_by(SurveyModel.agent_id)

        threshold = await self.min_responses()
        out: dict[UUID, dict] = {}
        for row in (await self._session.execute(stmt)).all():
            out[row.agent_id] = {
                # Xom qiymat. Ilgari `ready=False` da `None` qilinardi va
                # xodim profilida reyting bor, dashboardda yo'q bo'lardi.
                "value": round(float(row.avg), 2) if row.avg else None,
                "count": row.count,
                "ready": row.count >= threshold,
            }
        return out

    # ── 4. Blok bo'yicha razrez (radar chart) ─────────────────

    async def block_breakdown(self, f: AnalyticsFilter) -> list[dict]:
        f = self._scoped(f)
        stmt = (
            select(CallScoreModel.blocks)
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
        )
        rows = (await self._session.execute(self._apply(stmt, f))).scalars().all()

        totals: dict[str, list[float]] = {}
        for blocks in rows:
            for key, value in (blocks or {}).items():
                # ⚠️ `_` bilan boshlangan kalitlar — texnik metama'lumot
                # (`_meta`), blok EMAS. Ular razrezga tushsa 5-chi
                # «blok» bo'lib chiqadi.
                if key.startswith("_"):
                    continue
                # Sonli bo'lmagan qiymat — eski yoki buzuq yozuv.
                # Ilgari `float(value)` bu yerda `TypeError` berib
                # BUTUN endpointni 500 ga olib borardi.
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                totals.setdefault(key, []).append(float(value))

        # ⚠️ Blok maksimumi FAOL RUBRIKADAN olinadi, koddagi qotirilgan
        # `BLOCK_MAX` dan emas. Ular ajralib ketgan edi (`sales_skill`:
        # kodda 15, rubrikada 25) va radar chart 105.8% ko'rsatardi —
        # ya'ni shkaladan chiqib ketgan, o'qib bo'lmaydigan grafik.
        # Rubrika — bu raqamlarning yagona egasi: admin uni panelda
        # o'zgartira oladi, kod esa o'zgarmaydi.
        limits, labels = await self._rubric_block_limits()

        return [
            {
                "block": key,
                "label": labels.get(key, key),
                "score": round(sum(values) / len(values), 1),
                "max": limits[key],
                "percent": round(sum(values) / len(values) / limits[key] * 100, 1),
            }
            for key, values in totals.items()
            # Rubrikada yo'q blok ko'rsatilmaydi: uni nimaga bo'lishni
            # bilmaymiz va foizi ma'nosiz chiqadi
            if values and limits.get(key)
        ]

    async def _rubric_block_limits(self) -> tuple[dict[str, int], dict[str, str]]:
        """Faol rubrikadan `{blok: maksimum}` va `{blok: nom}`.

        Rubrika o'qilmasa (birinchi ishga tushirish, buzuq yozuv) —
        koddagi zaxira qiymatlar. Analitika hech qachon rubrika sababli
        500 bermasligi kerak.
        """
        from src.modules.scoring.application.rubric_service import RubricService
        from src.modules.scoring.domain.entities import BLOCK_MAX, ScoreBlock

        limits: dict[str, int] = {}
        labels: dict[str, str] = {}
        try:
            rubric = await RubricService(self._session).get_active()
            for block in rubric.blocks or []:
                key = block.get("key")
                maximum = block.get("max")
                if key and isinstance(maximum, (int, float)) and maximum > 0:
                    limits[key] = int(maximum)
                    labels[key] = block.get("label") or key
        except Exception:  # noqa: BLE001 — zaxiraga tushamiz
            pass

        if not limits:
            limits = {b.value: BLOCK_MAX.get(b, 25) for b in ScoreBlock}
            labels = {b.value: BLOCK_LABEL_UZ.get(b, b.value) for b in ScoreBlock}
        return limits, labels

    # ── 5. Red flag razrezi ───────────────────────────────────

    async def red_flag_breakdown(self, f: AnalyticsFilter) -> list[dict]:
        f = self._scoped(f)
        stmt = (
            select(CallScoreModel.red_flags)
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
        )
        rows = (await self._session.execute(self._apply(stmt, f))).scalars().all()

        counter: dict[str, int] = {}
        for flags in rows:
            for flag in flags or []:
                key = flag.get("type") if isinstance(flag, dict) else str(flag)
                if key:
                    counter[key] = counter.get(key, 0) + 1

        from src.modules.scoring.domain.entities import RedFlagType

        out = []
        for key, count in sorted(counter.items(), key=lambda kv: -kv[1]):
            try:
                label = RED_FLAG_LABEL_UZ[RedFlagType(key)]
            except ValueError:
                label = key
            out.append({"type": key, "label": label, "count": count})
        return out

    # ── 6. Ball taqsimoti (histogram) ─────────────────────────

    async def score_distribution(self, f: AnalyticsFilter) -> list[dict]:
        f = self._scoped(f)
        bucket = (func.floor(CallScoreModel.overall_score / 10) * 10).label("bucket")

        stmt = (
            select(bucket, func.count(CallModel.id).label("count"))
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await self._session.execute(self._apply(stmt, f))).all()
        return [
            {"range": f"{int(r.bucket)}–{int(r.bucket) + 9}", "count": r.count}
            for r in rows
        ]

    # ── 7. Region bo'yicha ────────────────────────────────────

    async def by_region(self, f: AnalyticsFilter) -> list[dict]:
        f = self._scoped(f)
        stmt = (
            select(
                AgentModel.region,
                func.count(CallModel.id).label("calls"),
                func.avg(CallScoreModel.overall_score).label("ai_score"),
            )
            .select_from(CallModel)
            .join(AgentModel, AgentModel.id == CallModel.agent_id)
            .join(CallScoreModel, CallScoreModel.call_id == CallModel.id)
            .group_by(AgentModel.region)
            .order_by(func.avg(CallScoreModel.overall_score).desc())
        )
        rows = (await self._session.execute(self._apply(stmt, f))).all()
        return [
            {
                "region": r.region,
                "calls": r.calls,
                "ai_score": round(float(r.ai_score), 1) if r.ai_score else None,
            }
            for r in rows
        ]

    # ── 8. Filtr variantlari (UI dropdownlari uchun) ──────────

    async def filter_options(self) -> dict[str, list]:
        """Filtr uchun variantlar — ROL DOIRASIDA.

        ⚠️ Savdo xodimi uchun ro'yxatlar o'ziga toraytiriladi. Ilgari
        bu endpoint hammaga bir xil javob qaytarardi: xodim o'z
        panelida butun kompaniyaning xodimlari va hududlarini ko'rardi.
        Ma'lumot baribir ko'rinmasdi (`_scoped()` so'rovni o'z
        agentiga qisadi), lekin filtrda tanlangan hudud jimgina bo'sh
        jadval berardi — filtr buzuqdek ko'rinardi. Bundan tashqari
        boshqa xodimlarning ismlari oshkor bo'lardi.
        """
        is_sales = bool(self._user and self._user.role == Role.SALES)
        own_agent_id = self._user.agent_id if is_sales else None

        agent_stmt = (
            select(AgentModel.id, AgentModel.full_name, AgentModel.region)
            .where(AgentModel.is_active.is_(True))
            .order_by(AgentModel.full_name)
        )
        region_stmt = select(AgentModel.region).distinct().order_by(AgentModel.region)

        if is_sales:
            # `agent_id` bo'lmagan savdo hisobi — hech qanday ma'lumoti
            # yo'q, demak filtrda ham hech narsa bo'lmasligi kerak.
            agent_stmt = agent_stmt.where(AgentModel.id == own_agent_id)
            region_stmt = region_stmt.where(AgentModel.id == own_agent_id)

        agents = (await self._session.execute(agent_stmt)).all()
        regions = (await self._session.execute(region_stmt)).scalars().all()

        return {
            "agents": [
                {"id": str(a.id), "name": a.full_name, "region": a.region}
                for a in agents
            ],
            "regions": list(regions),
        }
