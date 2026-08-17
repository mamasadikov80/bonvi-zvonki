"""Client baholari (so'rovnoma javoblari) endpointlari.

Ko'rinish qoidalari (PLAN.md D1 + access sozlamalari):
  • MANAGER / ADMIN — hammasi, izohlar bilan
  • SALES — faqat o'ziniki, izohlar `access.sales_client_rating`
    sozlamasiga bog'liq
  • Client kimligi HECH QACHON oshkor qilinmaydi — baho anonim

Ikkita endpoint (`/{token}/open` va `/{token}/submit`) — OCHIQ, ya'ni
avtorizatsiyasiz. Sababi pastda, ularning yonida yozilgan.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import Numeric, Select, cast, func, or_, select

from src.core.deps import CurrentUser, DbSession
from src.core.exceptions import ForbiddenError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.settings.application.services import SettingsService
from src.modules.settings.presentation.router import require_internal_token
from src.modules.surveys.application.services import (
    SurveyService,
    resolve_min_responses,
)
from src.modules.surveys.domain.entities import RED_FLAGS, Resolution
from src.modules.surveys.infrastructure.models import SurveyModel, SurveyResponseModel
from src.modules.surveys.presentation.webapp_router import router as webapp_router
from src.modules.users.domain.entities import (
    SALES_RATING_FULL,
    SALES_RATING_HIDDEN,
    Role,
)

router = APIRouter(prefix="/surveys", tags=["Surveys"])

# ⚠️ TARTIB MUHIM — bu qator shu yerda, eng boshida turishi kerak.
# Starlette marshrutlarni ro'yxatdan o'tish tartibida solishtiradi.
# Pastda `POST /surveys/{token}/open` bor: agar u OLDIN ro'yxatga tushsa,
# `/surveys/webapp/open` ga kelgan so'rov o'sha marshrutga `token="webapp"`
# bo'lib tushadi va Mini App endpointi umuman chaqirilmay, «So'rovnoma
# topilmadi» degan 404 qaytadi. `include_router` marshrutlarni CHAQIRILGAN
# PAYTDA ko'chiradi, shuning uchun uni pastga surmang.
router.include_router(webapp_router)

InternalOnly = Depends(require_internal_token)

# Bahoning hududi — UCH BOSQICHLI, tartibi muhim:
#
#   1. `surveys.region` — so'rovnoma yaratilgan LAHZADAGI nusxa.
#      Tarix shu yerdan o'qiladi va u hech qachon o'zgarmaydi.
#   2. `telegram_groups.region` — nusxa yo'q eski yozuvlar uchun zaxira
#      (ustun paydo bo'lishidan oldin yaratilganlar).
#   3. `agents.region` — guruhsiz eski client oqimi uchun oxirgi zaxira.
#
# ⚠️ NEGA NUSXA BIRINCHI. Ilgari hudud faqat TIRIK qiymatdan
# hisoblanardi. Natijada guruh boshqa hududga ko'chirilsa yoki hudud
# arxivlanib guruhdan uzilsa, o'tgan oylarning bahosi hisobotdan
# jimgina yo'qolardi — o'lchov o'zgargani uchun TARIX ham o'zgarardi.
# Endi o'tmish o'z hududida qoladi.
EFFECTIVE_REGION = func.coalesce(
    SurveyModel.region, TelegramGroupModel.region, AgentModel.region
)


class FeedbackItem(BaseModel):
    id: UUID
    agent_id: UUID
    agent_name: str
    csat: int
    resolution: str | None
    comment: str | None
    red_flags: list[str] = []
    responded_at: datetime
    region: str


class FeedbackSummary(BaseModel):
    average: float | None
    """Xom o'rtacha — javob bo'lsa doim to'ladi, `ready` ga bog'liq emas.
    Ko'rsatish qarori UI da: `ready=False` bo'lsa raqam chizilmaydi."""
    count: int
    ready: bool
    """`count >= survey.min_responses` (sozlamalardan, standart 5).
    `False` → dashboardda reyting o'rniga 'yig'ilmoqda' ko'rsatiladi."""
    min_responses: int
    """Amaldagi chegara. UI «1 / 5» va «yana 4 ta javob kerak» deb
    yozishi uchun kerak — aks holda u raqamni o'zi taxmin qilardi va
    admin sozlamani o'zgartirganda mos kelmay qolardi."""
    distribution: dict[str, int]
    response_rate: float | None
    """Javob berish darajasi, %. IKKITA MAYDON IKKI XIL VAQTNI SANAYDI —
    bu ataylab shunday va chalkashmaslik uchun ochiq yozib qo'yilgan:

      • maxraj — oynada YUBORILGAN so'rovnomalar (`surveys.sent_at`);
      • surat  — o'shalarning ichidan aynan shu oynada JAVOB KELGANLARI
        (`survey_responses.responded_at`).

    Ya'ni `average` / `count` / `distribution` javob vaqti bo'yicha
    hisoblanadi, `response_rate` ning maxraji esa yuborilgan vaqt
    bo'yicha. Savol ham shunday qo'yilgan: «shu kuni yuborilganlarning
    qanchasi javob oldi». Shuning uchun kechikkan javob (X kuni
    yuborilib X+1 kuni kelgan) X kuniga hisoblanmaydi, X+1 kunida esa
    maxraj boshqa — ikki kunning foizini qo'shib o'rtacha olib
    bo'lmaydi. Oyna ichida yuborilmagan (eski) so'rovnomaga kelgan
    javob ikkala tomonga ham tushmaydi.

    Maxraj nol bo'lsa `None` — «0%» emas: yuborilmagan joyda hisoblashga
    asos yo'q."""
    items: list[FeedbackItem]
    """⚠️ SALES roli uchun HAR DOIM bo'sh — `access.sales_client_rating`
    qanday bo'lishidan qat'i nazar. Sababi endpoint ichida yozilgan:
    har guruhda bitta mijoz, demak bitta baho mijozni oshkor qiladi."""


def _ilike_escape(value: str) -> str:
    """`ILIKE` metabelgilarini ekranlaydi.

    Foydalanuvchi yozgan `%` va `_` shablon belgisiga aylanib ketardi:
    bo'sh `%` butun ro'yxatni, `_` esa istalgan bitta harfni tortardi —
    ya'ni qidiruv o'rniga filtr yechilib qolardi. `\\` ning o'zi ham
    ekranlanadi, aks holda oxirgi belgi keyingi belgini yutib yuboradi.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _aware(value: datetime | None) -> datetime | None:
    """Mintaqasiz kelgan vaqtni UTC deb qabul qiladi.

    `?date_to=2026-08-16` kabi sana-only parametr naive `datetime` bo'lib
    keladi, ustunlar esa `timestamptz` — solishtirish uchun mintaqa shart.
    Qiymatning o'zi (soat-daqiqasi) o'zgarmaydi.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _period(
    days: int,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Vaqt oralig'ini hisoblaydi.

    `date_from` yoki `date_to` berilsa — ular ustun, `days` e'tiborga
    olinmaydi. Ikkalasi ham bo'lmasa — eskicha "oxirgi `days` kun".

    ⚠️ Berilgan vaqt AYNAN o'zi ishlatiladi, UTC KUNIGA KESILMAYDI.
    Ilgari bu yerda `datetime.combine(date_from.date(), time.min)` turardi.
    Frontend mahalliy yarim tunni yuboradi — UTC+5 da bu `...T19:00:00Z`,
    ya'ni OLDINGI kun. `.date()` o'sha oldingi kunni olib, oraliqqa butun
    bir kun ortiqcha qo'shardi: bitta xodimning bitta kundagi bahosi
    `/surveys` da 3.8, `/analytics/overview` da 3.0 bo'lib chiqardi —
    5 ballik shkalada 0.8 farq. Endi ikkala endpoint ham bir xil qoidada.

    Yagona istisno — `date_to` VAQTSIZ (aynan yarim tunga teng) kelgan
    holat: «16-avgustgacha» deganda 16-avgustning o'zi ham kirishi kerak,
    shuning uchun u o'sha kunning oxirigacha cho'ziladi. Aniq vaqt
    berilgan bo'lsa (`...T19:00:00Z`) — tegilmaydi.
    """
    if date_from is None and date_to is None:
        return datetime.now(UTC) - timedelta(days=days), None

    since = _aware(date_from)
    until = _aware(date_to)
    if until is not None and until.time() == time.min:
        # Sana-only qiymat: keyingi yarim tundan bir mikrosekund oldingacha
        until = until + timedelta(days=1) - timedelta(microseconds=1)
    return since, until


@router.get("", response_model=FeedbackSummary, summary="Client baholari")
async def list_feedback(
    session: DbSession,
    user: CurrentUser,
    agent_id: UUID | None = None,
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    date_from: Annotated[
        datetime | None,
        Query(
            description=(
                "Boshlanish sanasi, masalan `2026-07-01`. Aniq vaqt berilsa "
                "(`2026-07-01T19:00:00Z`) aynan o'sha lahzadan olinadi — "
                "kun boshiga kengaytirilmaydi."
            )
        ),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(
            description=(
                "Tugash sanasi. Vaqtsiz berilsa (`2026-08-16`) o'sha kun to'liq "
                "kiradi; aniq vaqt berilsa (`2026-08-16T19:00:00Z`) aynan o'sha "
                "lahzagacha olinadi."
            )
        ),
    ] = None,
    region: Annotated[
        str | None,
        Query(
            max_length=64,
            description=(
                "Hudud bo'yicha filtr. Guruh so'rovnomalarida hudud GURUHdan, "
                "eski client so'rovnomalarida xodimdan olinadi."
            ),
        ),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            max_length=120,
            description="Xodim ismi yoki hudud bo'yicha qidiruv",
        ),
    ] = None,
):
    access = await SettingsService(session).access_values()
    visibility = access.get("access.sales_client_rating", "score_only")

    # ── Ruxsat doirasi ────────────────────────────────────────
    if user.role is Role.SALES:
        if visibility == SALES_RATING_HIDDEN:
            raise ForbiddenError("Client baholari sizga ko'rsatilmaydi")
        # ⚠️ `users.agent_id` FK — `ON DELETE SET NULL`. Xodim kartochkasi
        # o'chirilsa, unga bog'langan savdo hisobining `agent_id` si NULL
        # bo'lib qoladi. Bo'sh doira — «hech narsa», «hammasi» EMAS: agar
        # bu yerda NULL o'tib ketsa, pastdagi filtr umuman qo'yilmaydi va
        # sotuvchi butun kompaniyaning statistikasini ko'radi.
        if user.agent_id is None:
            raise ForbiddenError("Hisobingiz savdo xodimiga bog'lanmagan")
        agent_id = user.agent_id  # o'zinikidan boshqasini ko'ra olmaydi
    elif user.role is Role.VIEWER:
        raise ForbiddenError("Ruxsat yetarli emas")

    # ══════════════════════════════════════════════════════════
    #  SALES uchun `items` HAR DOIM bo'sh
    #
    #  ⚠️ BU QOIDA `access.sales_client_rating` SOZLAMASIDAN
    #     KUCHLIROQ. `full` qo'yilsa ham alohida yozuvlar
    #     ko'rsatilmaydi — sozlama izohlarni boshqaradi, bu esa
    #     yozuvlarni butunlay yashiradi.
    #
    #  Sabab: har mijozga ALOHIDA guruh ochilgan, ya'ni guruhda
    #  bitta mijoz o'tiradi. Demak bitta baho — bitta mijoz.
    #  Sotuvchi «3 yulduz, 14-avgust» degan qatordan kim baho
    #  berganini darhol topadi, va bu munosabatlarni buzadi:
    #  mijoz keyingi safar rostini yozmaydi. So'rovnomaning butun
    #  qiymati anonimlikda.
    #
    #  Yig'ma ko'rsatkichlar (`average`, `count`, `ready`,
    #  `distribution`, `response_rate`) BARIBIR QAYTADI — sotuvchi
    #  o'z natijasini ko'rishi kerak, faqat kimning bahosi ekanini
    #  ko'rmasligi kerak.
    #
    #  Kim bu yerni keyin «tuzatmoqchi» bo'lsa: sozlamani `full`
    #  qilib qo'yish YETARLI EMAS va ataylab yetarli emas.
    # ══════════════════════════════════════════════════════════
    hide_items = user.role is Role.SALES

    show_comments = user.role is not Role.SALES or visibility == SALES_RATING_FULL
    since, until = _period(days, date_from, date_to)

    # Javob vaqti bo'yicha va yuborilgan vaqti bo'yicha shartlar
    responded_range = []
    if since is not None:
        responded_range.append(SurveyResponseModel.responded_at >= since)
    if until is not None:
        responded_range.append(SurveyResponseModel.responded_at <= until)

    sent_range = [SurveyModel.sent_at.isnot(None)]
    if since is not None:
        sent_range.append(SurveyModel.sent_at >= since)
    if until is not None:
        sent_range.append(SurveyModel.sent_at <= until)

    def scoped(stmt: Select) -> Select:
        """Barcha so'rovlar uchun umumiy bog'lanish va filtrlar.

        `agents` — INNER JOIN (`surveys.agent_id` doim to'la), `telegram_groups`
        — LEFT JOIN: eski client so'rovnomalarida guruh yo'q, ular ro'yxatdan
        tushib qolmasligi kerak.
        """
        stmt = stmt.join(AgentModel, AgentModel.id == SurveyModel.agent_id).outerjoin(
            TelegramGroupModel, TelegramGroupModel.id == SurveyModel.group_id
        )
        # `is not None` — `if agent_id:` EMAS. Falsy tekshiruv doirani
        # toraytirish o'rniga uni BUTUNLAY ochib yuborardi (yuqoridagi
        # izohga qarang).
        if agent_id is not None:
            stmt = stmt.where(SurveyModel.agent_id == agent_id)
        if region:
            stmt = stmt.where(EFFECTIVE_REGION == region)
        if search and search.strip():
            # Xodim ismi yoki hudud. Izoh bo'yicha qidirilmaydi — SALES
            # roli `score_only` rejimida izohlarni ko'rmasligi kerak,
            # qidiruv esa ularning borligini oshkor qilib qo'yardi
            needle = f"%{_ilike_escape(search.strip())}%"
            stmt = stmt.where(
                or_(
                    AgentModel.full_name.ilike(needle, escape="\\"),
                    EFFECTIVE_REGION.ilike(needle, escape="\\"),
                )
            )
        return stmt

    base = scoped(
        select(SurveyResponseModel, SurveyModel, AgentModel, TelegramGroupModel.region)
        .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
        .where(*responded_range)
    )

    # SALES da bu so'rov umuman yuborilmaydi: natijasi baribir
    # tashlab yuborilardi, bazani bekorga bezovta qilmaymiz.
    rows = (
        []
        if hide_items
        else (
            await session.execute(
                base.order_by(SurveyResponseModel.responded_at.desc()).limit(limit)
            )
        ).all()
    )

    # ── Yig'ma ko'rsatkichlar ─────────────────────────────────
    agg_stmt = scoped(
        select(
            func.avg(cast(SurveyResponseModel.csat, Numeric)).label("avg"),
            func.count(SurveyResponseModel.id).label("count"),
        )
        .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
        .where(*responded_range)
    )
    agg = (await session.execute(agg_stmt)).one()

    # Taqsimot (1..5 yulduz)
    dist_stmt = scoped(
        select(SurveyResponseModel.csat, func.count(SurveyResponseModel.id))
        .join(SurveyModel, SurveyModel.id == SurveyResponseModel.survey_id)
        .where(*responded_range)
    ).group_by(SurveyResponseModel.csat)
    distribution = {
        str(score): count for score, count in (await session.execute(dist_stmt)).all()
    }

    # ── Javob berish darajasi ─────────────────────────────────
    #
    #  Maxraj — oynada YUBORILGAN so'rovnomalar (`sent_at`).
    #  Surat — o'shalarning ichidan aynan SHU OYNADA javob KELGANLARI.
    #
    #  Ilgari surat `status == COMPLETED` edi, ya'ni javob QACHON
    #  kelganiga umuman qaramasdi. So'rovnoma X kuni yuborilib javob
    #  X+1 kuni kelsa, X kuni uchun `count: 0` bo'la turib
    #  `response_rate: 100.0` chiqardi — ekranda «bironta baho yo'q,
    #  javob berish darajasi 100%» degan zid juftlik.
    #
    #  `status` ni emas, javobning o'zini tekshiramiz: status
    #  so'rovnomaning umrbod holati, u vaqt oynasiga bog'lanmaydi.
    responded_in_window = (
        select(1)
        .select_from(SurveyResponseModel)
        .where(SurveyResponseModel.survey_id == SurveyModel.id, *responded_range)
        .exists()
    )

    sent_stmt = scoped(select(func.count(SurveyModel.id)).where(*sent_range))
    sent = (await session.execute(sent_stmt)).scalar_one()

    completed_stmt = scoped(
        select(func.count(SurveyModel.id)).where(*sent_range, responded_in_window)
    )
    completed = (await session.execute(completed_stmt)).scalar_one()

    # Chegara sozlamalardan olinadi (baza > .env > standart 5), konstantadan emas
    min_responses = await resolve_min_responses(session)
    ready = agg.count >= min_responses

    return FeedbackSummary(
        # O'rtacha HAR DOIM qaytariladi — `ready` bilan birga. Ilgari u
        # `ready=False` da `null` qilinardi, `GET /analytics/overview` esa
        # o'sha reytingni chegarasiz ko'rsatardi: bitta baho ikki xil
        # ko'rinardi. Endi qoida bitta — qiymat + soni + `ready`, nimani
        # chizishni UI hal qiladi.
        average=round(float(agg.avg), 2) if agg.avg else None,
        count=agg.count,
        ready=ready,
        min_responses=min_responses,
        distribution={str(i): distribution.get(str(i), 0) for i in range(1, 6)},
        response_rate=round(completed / sent * 100, 1) if sent else None,
        items=[
            FeedbackItem(
                id=response.id,
                agent_id=agent.id,
                agent_name=agent.full_name,
                csat=response.csat,
                resolution=response.resolution.value if response.resolution else None,
                comment=response.comment if show_comments else None,
                red_flags=response.red_flags or [],
                responded_at=response.responded_at,
                # Hudud endi GURUHdan keladi: bitta xodim bir nechta hududda
                # ishlashi mumkin. Eski client so'rovnomalarida guruh yo'q —
                # o'shanda xodimning o'z hududi ishlatiladi.
                region=group_region or agent.region,
            )
            for response, _survey, agent, group_region in rows
        ],
    )


class RedFlagItem(BaseModel):
    key: str
    label: str


@router.get(
    "/red-flags",
    response_model=list[RedFlagItem],
    summary="Red flag kalitlari va yorliqlari",
)
async def list_red_flags() -> list[RedFlagItem]:
    """Yagona registr — frontend ham, bot ham yorliqlarni shu yerdan oladi.

    Qo'lda ko'chirilgan ro'yxat ertami-kechmi asl nusxadan ajralib qoladi;
    kalitlar esa bazaga yozilgan, ya'ni eski javoblarni ham shu ro'yxat
    o'qiydi.

    **Autentifikatsiyasiz.** Bu shunchaki interfeys yorliqlari ro'yxati —
    ichida hech qanday ma'lumot yo'q. Botda JWT yo'q (u faqat
    `X-Internal-Token` bilan ishlaydi), kelajakdagi web so'rovnomada esa
    javob beruvchi client umuman tizimga kirmaydi. Ikkalasi ham shu
    ro'yxatga muhtoj, shuning uchun u ochiq.
    """
    return [RedFlagItem(key=key, label=label) for key, label in RED_FLAGS]


# ══════════════════════════════════════════════════════════════
#  Ochiq (avtorizatsiyasiz) endpointlar — bot uchun
# ══════════════════════════════════════════════════════════════
#
#  Bu ikkalasida `CurrentUser` ATAYLAB YO'Q va qo'shilmasin.
#  Baho beruvchi — do'kon egasi, u Telegram chatida o'tiribdi va
#  hech qachon dashboardga kirmaydi, unda login/parol yo'q.
#  KALIT — TOKENNING O'ZI: `secrets.token_urlsafe(24)`, muddati
#  `SURVEY_TOKEN_TTL_DAYS` kun, bitta so'rovnomaga bitta javob.
#
#  Xato xabarlari o'zbekcha, chunki bot ularni to'g'ridan-to'g'ri
#  mijozga ko'rsatadi. Konvert: {"error": {"code", "message"}}.


CommentText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=2000),
]


class SurveyOpenRequest(BaseModel):
    telegram_user_id: int | None = Field(
        default=None,
        description=(
            "Bot yuboradi, lekin ATAYLAB saqlanmaydi — mijoz anonim qoladi"
        ),
    )


class SurveyOpenResponse(BaseModel):
    """Bot ekranga chiqaradigan ma'lumot. Mijoz kimligi bu yerda YO'Q."""

    agent_name: str
    period_start: datetime
    period_end: datetime
    status: str


class SurveySubmitRequest(BaseModel):
    csat: Annotated[int, Field(ge=1, le=5, description="1..5 yulduz")]
    resolution: Resolution | None = None
    comment: CommentText | None = None


class SurveySubmitResponse(BaseModel):
    agent_name: str
    csat: int
    status: str


@router.post(
    "/{token}/open",
    response_model=SurveyOpenResponse,
    summary="So'rovnomani ochish (ochiq, tokensiz kirish yo'q)",
    responses={
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "Muddati o'tgan yoki allaqachon baholangan"},
    },
)
async def open_survey(
    token: str,
    session: DbSession,
    payload: SurveyOpenRequest | None = None,
):
    """Tokenni tekshiradi va so'rovnomani "ochilgan" deb belgilaydi."""
    return await SurveyService(session).open(
        token,
        telegram_user_id=payload.telegram_user_id if payload else None,
    )


@router.post(
    "/{token}/submit",
    response_model=SurveySubmitResponse,
    status_code=201,
    summary="Bahoni yuborish (ochiq, tokensiz kirish yo'q)",
    responses={
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "Muddati o'tgan yoki allaqachon baholangan"},
    },
)
async def submit_survey(token: str, session: DbSession, payload: SurveySubmitRequest):
    return await SurveyService(session).submit(
        token,
        csat=payload.csat,
        resolution=payload.resolution,
        comment=payload.comment,
    )


# ══════════════════════════════════════════════════════════════
#  Guruh oqimi — bot uchun ichki endpointlar (`X-Internal-Token`)
#
#  ⚠️  BU YERGA TELEGRAM IDENTIFIKATORI KELMAYDI VA KELMASLIGI KERAK.
#      Bot `sha256(token + ":" + telegram_user_id)` ni o'zi hisoblaydi
#      va faqat hash yuboradi. Har so'rovnomaning tokeni har xil,
#      shuning uchun bir odamning turli so'rovnomalardagi hash'lari
#      bir-biriga bog'lanmaydi.
#
#      Agar kimdir kelajakda "qulay bo'lsin" deb `telegram_user_id`
#      maydonini qo'shsa — bitta JOIN bilan "bu 2 yulduzni kim qo'ydi"
#      ochilib qoladi va butun tizimning anonimlik va'dasi buziladi.
# ══════════════════════════════════════════════════════════════


RespondentHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=16, max_length=64, pattern=r"^[0-9a-fA-F]+$"
    ),
]


class SurveySentRequest(BaseModel):
    chat_message_id: int


class SurveyRateRequest(BaseModel):
    respondent_hash: RespondentHash
    csat: Annotated[int, Field(ge=1, le=5, description="1..5 yulduz")]


class SurveyRateResponse(BaseModel):
    accepted: bool
    response_count: int
    already_rated: bool


class SurveyDetailRequest(BaseModel):
    respondent_hash: RespondentHash
    comment: CommentText | None = None
    red_flags: list[str] = []


@router.post(
    "/{token}/sent",
    summary="[ichki] Guruhga yuborilgani belgilanadi",
    dependencies=[InternalOnly],
    responses={404: {"description": "So'rovnoma topilmadi"}},
)
async def mark_sent(
    token: str, payload: SurveySentRequest, session: DbSession
) -> dict[str, str]:
    """Bot xabar id sini qaytaradi — keyin o'sha xabarni tahrirlab turadi."""
    return await SurveyService(session).mark_sent(token, payload.chat_message_id)


@router.post(
    "/{token}/rate",
    response_model=SurveyRateResponse,
    summary="[ichki] Guruhdagi tugmadan kelgan baho",
    dependencies=[InternalOnly],
    responses={
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "Muddati o'tgan"},
    },
)
async def rate_survey(token: str, payload: SurveyRateRequest, session: DbSession):
    """Takroriy hash — 200, `accepted=false, already_rated=true`.

    Ataylab 409 emas: odam ikkinchi marta bosishi xato emas, oddiy holat.
    Bot unga «Siz allaqachon baho bergansiz» degan oyna ko'rsatadi.
    """
    return await SurveyService(session).rate(
        token, respondent_hash=payload.respondent_hash, csat=payload.csat
    )


@router.post(
    "/{token}/detail",
    summary="[ichki] Izoh va red flag'lar (shaxsiy chatdan)",
    dependencies=[InternalOnly],
    responses={
        404: {"description": "So'rovnoma topilmadi"},
        409: {"description": "Bu hash hali ball qo'ymagan"},
        422: {"description": "Noma'lum red flag kaliti"},
    },
)
async def detail_survey(
    token: str, payload: SurveyDetailRequest, session: DbSession
) -> dict[str, bool]:
    return await SurveyService(session).detail(
        token,
        respondent_hash=payload.respondent_hash,
        comment=payload.comment,
        red_flags=payload.red_flags,
    )
