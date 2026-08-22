"""Savdo nazorati qoidalari — R1, R2, R3.

Savol bitta: **savdo rasmiy kelishuv bilan bo'ldimi?** Ya'ni SAP dagi
savdo yonida bizda yozib olingan suhbat bormi. Yo'q bo'lsa — bu ayblov
EMAS, tekshiruv navbatiga tushadigan qator (`docs/savdo-nazorati.md`,
4 va 5-bo'limlar).

⚠️ XULOSA BAZAGA YOZILMAYDI. Har so'rovda qaytadan hisoblanadi.
Sabab shartnomaning 3-bo'limida: qo'ng'iroq savdodan KEYIN
sinxronlanishi mumkin (MoyZvonki tarixini orqaga surib olamiz) va
o'shanda bazaga yozib qo'yilgan «shubhali» belgisi YOLG'ONGA
aylanardi — uni qayta hisoblashni hech kim eslamas edi. Bazada faqat
odamning qarori (`sale_reviews`) turadi.

QOIDALAR (faqat `op_type = 'sale'` qatorlarga):

  R1 — savdo kuni yoki undan oldingi N kun ichida shu mijoz bilan
       suhbat bo'lmagan (N — `sales.window_days` sozlamasi, sukut 3);
  R2 — shu mijozning oldingi savdosidan keyin va shu savdogacha
       birorta suhbat bo'lmagan (birinchi savdoda QO'LLANMAYDI);
  R3 — butun tarixda shu mijoz bilan umuman gaplashilmagan.

UCH TOIFA — hech narsa yashirilmaydi:

  `ok`            — qoida buzilmagan;
  `suspicious`    — qoida buzilgan, tekshirish MUMKIN edi;
  `not_checkable` — tekshirishning iloji yo'q (umumiy kod yoki
                    telefonsiz mijoz). Bu «toza» degani EMAS, alohida
                    son bo'lib turadi.

IKKI O'LCHOV MASALASI VA ULARNING YECHIMI:

  1. SAVDODA VAQT YO'Q. SAP `Дата регистрации` da faqat sana beradi,
     shuning uchun oyna soat bilan emas, KUN bilan o'lchanadi: savdo
     kuni + oldingi N kun (jami N+1 kun). Buni ekranda ochiq yozamiz.
  2. QO'NG'IROQDA VAQT BOR, lekin u UTC da saqlanadi. Sana bo'yicha
     solishtirishdan oldin u MAHALLIY vaqtga o'tkaziladi
     (`Asia/Tashkent`) — aks holda ertalab soat 2 dagi qo'ng'iroq
     «kechagi» bo'lib qolardi va chegara bir kunga siljirdi. Bu
     `analytics/application/activity.py` bilan bir xil qoida.

UNUMDORLIK. 6 oylik eksport ~17 000 savdo bo'ladi va har qator uchun
uchta savol bor. Shuning uchun HAR QATOR UCHUN ALOHIDA SO'ROV YO'Q:
butun sahifa (va butun hisobot) bitta so'rovda hisoblanadi —
qo'ng'iroqlar mijoz kaliti bo'yicha BIR MARTA yig'iladi (`evidence`),
oldingi savdo esa oyna funksiyasi (`lag`) bilan topiladi.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CTE,
    Date,
    Integer,
    Select,
    String,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    nullslast,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallType
from src.modules.calls.infrastructure.models import CallModel
from src.modules.sales.domain.entities import GENERIC_PARTNER_CODES, SaleOpType
from src.modules.sales.infrastructure.models import (
    SaleModel,
    SalePartnerModel,
    SaleReviewModel,
)
from src.modules.settings.application.services import SettingsService
from src.modules.users.infrastructure.models import UserModel

# ══════════════════════════════════════════════════════════════
#  Doimiylar
# ══════════════════════════════════════════════════════════════

#: Qo'ng'iroq sanasi qaysi vaqt mintaqasida o'qiladi.
#
# ⚠️ `analytics/application/activity.py` dagi `LOCAL_TZ` bilan BIR XIL
# bo'lishi shart. Farq qilsa, bitta qo'ng'iroq ikki bo'limda ikki xil
# kunga tushardi va rahbar qaysi biriga ishonishni bilmasdi.
LOCAL_TZ = "Asia/Tashkent"

#: R1 oynasi shu sozlamadan o'qiladi.
WINDOW_DAYS_KEY = "sales.window_days"

#: Sozlama bo'sh yoki buzuq bo'lsa ishlatiladigan qiymat.
DEFAULT_WINDOW_DAYS = 3

#: Oyna uchun aqlli chegara — sozlamaga `99999` yozilib qo'yilsa
#: butun nazorat jimgina o'chib qolardi.
MAX_WINDOW_DAYS = 365


class Verdict(StrEnum):
    OK = "ok"
    SUSPICIOUS = "suspicious"
    NOT_CHECKABLE = "not_checkable"


class SkipReason(StrEnum):
    """Nega tekshirib bo'lmadi."""

    GENERIC_CODE = "generic_code"
    """Umumiy kod — bitta kod ostida ko'p mijoz (`К00001` va h.k.)."""

    NO_PHONE = "no_phone"
    """Telefon yo'q yoki ishonchsiz (`reader.phone_key` izohiga qarang)."""


class Rule(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class ReviewState(StrEnum):
    """Tekshiruv navbatidagi holat.

    `NEW` — rahbar hali qaror qo'ymagan. Ro'yxat sukut bo'yicha aynan
    shularni ko'rsatadi: ko'rilgan savdo ertasiga yana ro'yxat boshida
    turmasligi kerak, aks holda navbat hech qachon tugamaydi.
    """

    NEW = "new"
    JUSTIFIED = "justified"
    CONFIRMED = "confirmed"

    ALL = "all"
    """Qarori bor-yo'qligidan qat'i nazar HAMMASI.

    ⚠️ ATAYLAB ALOHIDA QIYMAT, `review=` ni bo'sh qoldirish emas.
    Rahbarga «hamma qarorlarni ko'rsat» kerak bo'ladi (oqlanganlar
    statistikasi ham shu ro'yxatdan o'qiladi), lekin bu ANIQ TANLOV
    bo'lsin. Bo'sh parametr esa «foydalanuvchi tanlamadi» degani va
    o'shanda sukut — `new`."""


class ComplianceSort(StrEnum):
    DATE = "date"
    AMOUNT = "amount"
    AGENT = "agent"
    PARTNER = "partner"


# ══════════════════════════════════════════════════════════════
#  Ma'lumot shakllari (shartnomaning 7.1-bo'limi)
# ══════════════════════════════════════════════════════════════


@dataclass(slots=True)
class SaleVerdict:
    """Bitta savdo bo'yicha xulosa VA UNING DALILI.

    ⚠️ Dalil maydonlari «yaxshi bo'lsa bo'ldi» emas — TALAB. Rahbar
    sonni qo'lda qayta hisoblab ko'rmoqchi (shartnoma, 4-bo'lim), ya'ni
    har shubhali qator yonida «oxirgi suhbat qachon, kim bilan, necha
    kun oldin» turishi kerak. Busiz ro'yxat ishonchsiz bo'lardi.
    """

    sale_id: UUID
    verdict: str
    broken_rules: list[str]
    skip_reason: str | None

    last_call_at: datetime | None
    """Savdodan OLDINGI (yoki savdo kunidagi) eng yaqin suhbat.

    ⚠️ Oynaga BOG'LIQ EMAS: oyna 3 kun bo'lsa ham, oxirgi suhbat 9 kun
    oldin bo'lgani ko'rinib tursin — aynan shu son qoidani tushuntiradi."""

    last_call_agent: str | None
    days_before: int | None
    """Savdodan necha kun oldin. `0` — o'sha kuni."""

    previous_sale_on: date | None
    """R2: shu mijozning oldingi savdo sanasi. `None` — birinchi savdo."""

    calls_between: int
    calls_total: int


@dataclass(slots=True)
class SaleReview:
    """Rahbarning qarori — bazadagi YAGONA subyektiv yozuv."""

    status: str
    reason: str | None
    note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None


@dataclass(slots=True)
class ComplianceRow:
    """Ro'yxatdagi bitta savdo: SAP fakti + xulosa + odamning qarori."""

    id: UUID
    occurred_on: date
    external_id: str
    partner_code: str
    partner_name: str | None
    phone: str | None
    phone_key: str | None
    branch: str | None
    direction: str | None
    agent_id: UUID | None
    agent_name: str | None
    amount: float | None
    currency: str
    amount_usd: float | None
    verdict: SaleVerdict
    review: SaleReview | None


@dataclass(slots=True)
class CompliancePage:
    items: list[ComplianceRow]
    total: int
    page: int
    page_size: int


@dataclass(slots=True)
class AgentBreakdown:
    """Xodimlar kesimi.

    `agent_id = None` — filiali xodimga biriktirilmagan savdolar
    (masalan «Зухриддин» — u bizning xodimimiz emas, lekin savdolari
    baribir nazoratda turadi). Ular jimgina yo'qolmasligi uchun
    ALOHIDA qator bo'lib chiqadi.
    """

    agent_id: UUID | None
    agent_name: str | None
    sales: int
    ok: int
    suspicious: int
    not_checkable: int
    new: int
    """Shubhali, lekin hali ko'rilmagan — rahbarning ish navbati."""
    justified: int
    confirmed: int


@dataclass(slots=True)
class ComplianceSummary:
    total: int
    ok: int
    suspicious: int
    not_checkable: int
    new: int
    justified: int
    confirmed: int
    window_days: int
    agents: list[AgentBreakdown] = field(default_factory=list)


@dataclass(slots=True)
class ClientSale:
    """Mijoz kartochkasidagi bitta savdo (3-bosqich, vaqt chizig'i)."""

    sale_id: UUID
    occurred_on: date
    external_id: str
    branch: str | None
    direction: str | None
    agent_id: UUID | None
    agent_name: str | None
    amount: float | None
    currency: str
    amount_usd: float | None
    verdict: str
    broken_rules: list[str]

    # ── DALIL ────────────────────────────────────────────────
    #
    # ⚠️ MAYDONLAR RO'YXATDAGI BILAN AYNAN BIR XIL (`SaleVerdict`).
    # Kartochkadagi savdo qatori xulosani KO'RSATADI, demak uni
    # tekshirish imkoni ham shu yerda bo'lishi kerak: «toza» degan
    # yorliq yonida «oxirgi suhbat qachon bo'lgan» turmasa, rahbar
    # nazorat ro'yxatini ochib qaytadan qidirishga majbur bo'lardi.
    # Ikki ekran bir xil savolga ikki xil to'liqlikda javob bersa,
    # ishonch ham shu yerda yo'qoladi.
    last_call_at: datetime | None
    last_call_agent: str | None
    days_before: int | None
    previous_sale_on: date | None
    calls_between: int
    calls_total: int

    skip_reason: str | None
    """⚠️ Kartochkada ham KERAK. Mijoz telefoni bo'yicha ochilgani
    uchun `no_phone` bo'lishi mumkin emas, lekin `generic_code`
    bo'ladi: umumiy kod («Разовый клиент») ostidagi savdo shu raqamga
    ham tushib qoladi. Sababsiz «tekshirib bo'lmadi» yorlig'i
    javobsiz savol bo'lardi."""
    review_status: str | None


@dataclass(slots=True)
class ClientSales:
    """Mijozning savdolari + kartochka tepasidagi qisqa yig'ma.

    ⚠️ SONLAR `items` DAN EMAS, BUTUN TANLOVDAN olinadi (oyna
    funksiyasi `LIMIT` dan OLDIN hisoblanadi). Ro'yxat kesilgan
    bo'lsa ham «nechta savdo, qanchaga, nechtasi shubhali» degan
    javob to'g'ri qoladi — aks holda yig'ma jimgina kamayib ketardi.
    """

    items: list[ClientSale]
    total: int
    amount_usd: float
    """Jami — DOLLARDA. Boshqa valyutadagi summalarni qo'shib
    bo'lmaydi (`sales.amount` hujjat valyutasida), `amount_usd` esa
    SAP ning o'zi bergan ekvivalent."""
    suspicious: int
    not_checkable: int


@dataclass(slots=True)
class ComplianceFilter:
    """Ro'yxat, hisobot va eksport uchun BIR XIL filtr.

    ⚠️ Uchalasi bir xil oynani ko'rishi shart: hisobotdagi «41 shubhali»
    ro'yxatdagi qator soni bilan mos kelmasa, foydalanuvchi qaysi
    biriga ishonishni bilmaydi.
    """

    since: date | None = None
    until: date | None = None
    agent_ids: list[UUID] | None = None
    branches: list[str] | None = None
    verdict: str | None = None
    review: str | None = None
    rule: str | None = None
    search: str | None = None
    window_days: int = DEFAULT_WINDOW_DAYS
    """Sozlamadan keladi (`resolve_window_days`), qattiq yozilmaydi."""


# ══════════════════════════════════════════════════════════════
#  Sozlama
# ══════════════════════════════════════════════════════════════


async def resolve_window_days(session: AsyncSession) -> int:
    """`sales.window_days` sozlamasini o'qiydi.

    Buzuq qiymat butun bo'limni to'xtatib qo'ymasligi kerak: sozlamaga
    qo'l bilan matn yozilgan bo'lsa standart qiymatga qaytamiz.
    Sozlamalar servisi ham tekshiradi, lekin bu yerdagi himoya eski
    (tekshiruv qo'shilishidan oldin yozilgan) qiymatlar uchun.
    """
    raw = await SettingsService(session).get_value(WINDOW_DAYS_KEY)
    try:
        days = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return max(0, min(days, MAX_WINDOW_DAYS))


# ══════════════════════════════════════════════════════════════
#  SQL bo'laklari
# ══════════════════════════════════════════════════════════════

#: Qo'ng'iroqdagi mijoz raqamining OXIRGI 9 tasi — savdo bilan bog'lash
#: kaliti.
#
# ⚠️ Ifoda `ix_calls_phone_tail` indeksidagi bilan SO'ZMA-SO'Z bir xil
# (`bootstrap.py`), `coalesce` ham shu jumladan. Bir belgi farq qilsa
# PostgreSQL indeksni tanimay qoladi va har hisobot butun `calls`
# jadvalini skanerlashga aylanardi.
_CALL_KEY = func.right(
    func.regexp_replace(func.coalesce(CallModel.client_phone, ""), r"\D", "", "g"), 9
)

#: Qo'ng'iroqning MAHALLIY sanasi — savdo sanasi bilan solishtirish uchun.
_CALL_DAY = func.timezone(LOCAL_TZ, CallModel.started_at).cast(Date)


def _ilike_escape(text: str) -> str:
    """`ILIKE` metabelgilarini oddiy belgiga aylantiradi."""
    for sign in ("\\", "%", "_"):
        text = text.replace(sign, f"\\{sign}")
    return text


def _previous_sale_cte() -> CTE:
    """Har mijozning OLDINGI savdo sanasi (butun tarix bo'yicha).

    ⚠️ NEGA `DISTINCT` DAN KEYIN `lag`. Bir kunda bitta mijozga ikki
    savdo bo'lishi normal holat. `lag` to'g'ridan-to'g'ri qatorlar
    ustidan yurganda ikkinchi savdo o'zining KUNDOSHINI «oldingi savdo»
    deb olardi, oraliq esa bo'sh chiqib R2 avtomatik buzilardi — ya'ni
    har ikkinchi savdo asossiz shubhali bo'lib qolardi. Avval sanalar
    yagonalashtiriladi, keyin oldingisi olinadi.

    ⚠️ NEGA FILTRDAN TASHQARIDA. Foydalanuvchi «oxirgi 7 kun» deb
    tanlasa ham, oldingi savdo o'sha oynadan tashqarida bo'lishi mumkin.
    Filtrlangan to'plam ustidan hisoblansa, davr boshidagi savdolar
    «birinchi savdo» bo'lib ko'rinardi va R2 ular uchun jimgina
    o'chib qolardi.
    """
    days = (
        select(SaleModel.phone_key, SaleModel.occurred_on)
        .where(SaleModel.op_type == SaleOpType.SALE.value)
        .where(SaleModel.phone_key.is_not(None))
        .distinct()
        .subquery("sale_days")
    )
    return select(
        days.c.phone_key,
        days.c.occurred_on,
        func.lag(days.c.occurred_on)
        .over(partition_by=days.c.phone_key, order_by=days.c.occurred_on)
        .label("previous_sale_on"),
    ).cte("previous_sale")


class ComplianceService:
    """Qoidalar mexanizmi. Bazaga HECH NARSA YOZMAYDI — faqat o'qiydi."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── 1-bosqich: tanlangan savdolar ─────────────────────────

    def _selected(self, f: ComplianceFilter, *, phone_key: str | None = None) -> CTE:
        """Filtrga mos savdolar + oldingi savdo sanasi + qaror.

        Bu yerda FAQAT bazadagi faktlar bo'yicha filtrlash bo'ladi.
        Xulosa bo'yicha filtr (`verdict`, `rule`) pastda, `_rows` da —
        u yerda xulosa allaqachon hisoblangan.
        """
        prev = _previous_sale_cte()
        reviewer = aliased(UserModel)

        stmt = (
            select(
                SaleModel.id,
                SaleModel.external_id,
                SaleModel.occurred_on,
                SaleModel.partner_code,
                SaleModel.partner_name,
                SaleModel.phone_key,
                SaleModel.branch,
                SaleModel.direction,
                SaleModel.amount,
                SaleModel.currency,
                SaleModel.amount_usd,
                SaleModel.agent_id,
                AgentModel.full_name.label("agent_name"),
                SalePartnerModel.phone.label("phone"),
                prev.c.previous_sale_on,
                SaleReviewModel.status.label("review_status"),
                SaleReviewModel.reason.label("review_reason"),
                SaleReviewModel.note.label("review_note"),
                SaleReviewModel.reviewed_at.label("reviewed_at"),
                reviewer.full_name.label("reviewed_by"),
            )
            .select_from(SaleModel)
            # Hamma bog'lanish IXTIYORIY: xodimsiz filial ham, katalogda
            # topilmagan kod ham, ko'rilmagan savdo ham ro'yxatda
            # QOLISHI kerak — nazoratdan chiqib ketmasin.
            .outerjoin(AgentModel, AgentModel.id == SaleModel.agent_id)
            .outerjoin(SalePartnerModel, SalePartnerModel.code == SaleModel.partner_code)
            .outerjoin(
                prev,
                and_(
                    prev.c.phone_key == SaleModel.phone_key,
                    prev.c.occurred_on == SaleModel.occurred_on,
                ),
            )
            .outerjoin(SaleReviewModel, SaleReviewModel.sale_id == SaleModel.id)
            .outerjoin(reviewer, reviewer.id == SaleReviewModel.reviewed_by)
            # ⚠️ Qoidalar FAQAT savdoga. To'lov, qaytarish va buxgalteriya
            # operatsiyalari bazada qoladi (mijoz kartochkasidagi vaqt
            # chizig'i uchun), lekin tekshirilmaydi.
            .where(SaleModel.op_type == SaleOpType.SALE.value)
        )

        if phone_key is not None:
            stmt = stmt.where(SaleModel.phone_key == phone_key)
        if f.since is not None:
            stmt = stmt.where(SaleModel.occurred_on >= f.since)
        if f.until is not None:
            stmt = stmt.where(SaleModel.occurred_on <= f.until)
        if f.agent_ids:
            stmt = stmt.where(SaleModel.agent_id.in_(f.agent_ids))
        if f.branches:
            stmt = stmt.where(SaleModel.branch.in_(f.branches))

        text = (f.search or "").strip()
        if text:
            conditions = [
                SaleModel.partner_name.ilike(
                    f"%{_ilike_escape(text)}%", escape="\\"
                ),
                SaleModel.partner_code.ilike(f"%{_ilike_escape(text)}%", escape="\\"),
                SaleModel.external_id.ilike(f"%{_ilike_escape(text)}%", escape="\\"),
            ]
            digits = "".join(char for char in text if char.isdigit())
            if digits:
                # Raqam istalgan formatda kiritilishi mumkin — kalit
                # esa faqat raqamlardan iborat.
                conditions.append(SaleModel.phone_key.like(f"%{digits}%"))
            stmt = stmt.where(or_(*conditions))

        return stmt.cte("selected")

    # ── 2-bosqich: qo'ng'iroq dalili ──────────────────────────

    def _evidence(self, selected: CTE) -> CTE:
        """Har savdo uchun qo'ng'iroq yig'masi — BITTA o'tishda.

        Uchala qoida ham bitta savolning uch kesimi: «shu raqam bilan
        qachon gaplashilgan». Shuning uchun qo'ng'iroqlar bir marta
        olinadi va uchta yig'ma `FILTER` bilan ajratiladi:

          · `last_call_at`  — savdodan oldingi eng yaqin suhbat (R1);
          · `calls_between` — oldingi savdodan keyingi suhbatlar (R2);
          · `calls_total`   — butun tarix (R3).

        ⚠️ FAQAT `call_type = 'sales'`. Ichki suhbat (ikkala tomon ham
        bizning xodimimiz) mijoz bilan kelishuv EMAS — u R1 ni oqlay
        olmaydi. Tur RAQAM bo'yicha aniqlanadi
        (`calls/domain/routing.py`), ya'ni ishonchli.

        ⚠️ `calls_total` DAVR BILAN CHEGARALANMAGAN — savdodan keyingi
        suhbatlar ham sanaladi. R3 «umuman gaplashilmagan» degan eng
        qattiq signal, shuning uchun u eng EHTIYOTKOR shaklda: mijoz
        bilan bir marta bo'lsa ham aloqa bo'lgan bo'lsa, R3 qo'yilmaydi.
        """
        # Faqat KERAKLI raqamlar. Busiz butun `calls` jadvali (bir
        # yillik sinxronizatsiyadan keyin yuz minglab qator) har
        # so'rovda birlashmaga tortilardi.
        keys = select(distinct(selected.c.phone_key)).where(
            selected.c.phone_key.is_not(None)
        )
        calls = (
            select(
                _CALL_KEY.label("key"),
                CallModel.started_at.label("started_at"),
                _CALL_DAY.label("day"),
                CallModel.agent_id.label("agent_id"),
            )
            .where(CallModel.call_type == CallType.SALES.value)
            .where(_CALL_KEY.in_(keys))
            .subquery("client_calls")
        )
        talker = aliased(AgentModel)
        before = calls.c.day <= selected.c.occurred_on

        return (
            select(
                selected.c.id.label("sale_id"),
                func.max(calls.c.started_at).filter(before).label("last_call_at"),
                func.count(calls.c.started_at).label("calls_total"),
                func.count(calls.c.started_at)
                .filter(
                    and_(
                        selected.c.previous_sale_on.is_not(None),
                        # ⚠️ Oldingi savdo KUNIDAGI qo'ng'iroq oraliqqa
                        # KIRMAYDI: u o'sha savdoni oqlagan bo'lishi
                        # mumkin va bitta suhbat ikki savdoni oqlab
                        # yuborardi. Shu savdo kuni esa kiradi — savdo
                        # vaqti noma'lum, ya'ni suhbat undan oldin
                        # bo'lgan deb hisoblanadi.
                        calls.c.day > selected.c.previous_sale_on,
                        before,
                    )
                )
                .label("calls_between"),
                # Oxirgi suhbatda KIM gaplashgani. `max()` bilan olib
                # bo'lmaydi (bu ism emas, sana bo'yicha tanlov), shuning
                # uchun tartiblangan massivning birinchi elementi.
                # `cast` — ustun turi CTE dan tashqarida ham ma'lum
                # bo'lishi uchun.
                cast(
                    func.array_agg(
                        aggregate_order_by(
                            talker.full_name, calls.c.started_at.desc()
                        )
                    ).filter(before),
                    ARRAY(String),
                ).label("last_call_agents"),
            )
            .select_from(selected)
            .outerjoin(calls, calls.c.key == selected.c.phone_key)
            .outerjoin(talker, talker.id == calls.c.agent_id)
            .group_by(selected.c.id)
            .cte("evidence")
        )

    # ── 3-bosqich: xulosa ─────────────────────────────────────

    def _rows(self, f: ComplianceFilter, selected: CTE, evidence: CTE) -> Select:
        """Qoidalarni qo'llaydi va xulosa bo'yicha filtrlaydi."""
        window = int(f.window_days)

        last_day = func.timezone(LOCAL_TZ, evidence.c.last_call_at).cast(Date)
        days_before = cast(selected.c.occurred_on - last_day, Integer)

        # ── Tekshirib bo'lmaydiganlar ─────────────────────────
        generic = selected.c.partner_code.in_(GENERIC_PARTNER_CODES)
        no_phone = selected.c.phone_key.is_(None)
        skipped = or_(generic, no_phone)
        checkable = ~skipped

        # ── Qoidalar ──────────────────────────────────────────
        #
        # R1: oyna ichida suhbat yo'q. `last_call_at` oynadan TASHQARIDA
        # bo'lishi mumkin (dalil sifatida ko'rsatiladi), shuning uchun
        # shart «umuman yo'q YOKI juda eski» ko'rinishida.
        r1 = and_(
            checkable,
            or_(evidence.c.last_call_at.is_(None), days_before > window),
        )
        # R2: birinchi savdoda QO'LLANMAYDI — solishtiradigan narsa yo'q.
        r2 = and_(
            checkable,
            selected.c.previous_sale_on.is_not(None),
            evidence.c.calls_between == 0,
        )
        r3 = and_(checkable, evidence.c.calls_total == 0)

        verdict = case(
            (skipped, literal(Verdict.NOT_CHECKABLE.value)),
            (or_(r1, r2, r3), literal(Verdict.SUSPICIOUS.value)),
            else_=literal(Verdict.OK.value),
        )
        skip_reason = case(
            # Tartib muhim: umumiy kodda telefon ham bo'lmaydi, lekin
            # sabab «umumiy kod» — u aniqroq va tuzatib bo'lmaydigan.
            (generic, literal(SkipReason.GENERIC_CODE.value)),
            (no_phone, literal(SkipReason.NO_PHONE.value)),
        )

        stmt = (
            select(
                selected.c.id,
                selected.c.external_id,
                selected.c.occurred_on,
                selected.c.partner_code,
                selected.c.partner_name,
                selected.c.phone,
                selected.c.phone_key,
                selected.c.branch,
                selected.c.direction,
                selected.c.agent_id,
                selected.c.agent_name,
                selected.c.amount,
                selected.c.currency,
                selected.c.amount_usd,
                selected.c.previous_sale_on,
                selected.c.review_status,
                selected.c.review_reason,
                selected.c.review_note,
                selected.c.reviewed_at,
                selected.c.reviewed_by,
                evidence.c.last_call_at,
                evidence.c.calls_between,
                evidence.c.calls_total,
                evidence.c.last_call_agents[1].label("last_call_agent"),
                days_before.label("days_before"),
                verdict.label("verdict"),
                skip_reason.label("skip_reason"),
                r1.label("r1"),
                r2.label("r2"),
                r3.label("r3"),
            )
            .select_from(selected)
            .join(evidence, evidence.c.sale_id == selected.c.id)
        )

        if f.verdict:
            stmt = stmt.where(verdict == f.verdict)
        if f.rule:
            stmt = stmt.where({Rule.R1: r1, Rule.R2: r2, Rule.R3: r3}[Rule(f.rule)])

        # ⚠️ TEKSHIRUV HOLATI FILTRI ATAYLAB SHU YERDA, `_selected` da EMAS.
        #
        # O'lchandi (17 663 savdo, `sale_reviews` bo'sh): shart yuqoriga
        # qo'yilganda PostgreSQL `LEFT JOIN … IS NULL` ni juda tanlovchi
        # deb baholaydi (88 qator deb chamalaydi, aslida 17 663) va
        # `evidence` uchun NESTED LOOP tanlaydi — qo'ng'iroqlar jadvali
        # HAR SAVDO uchun qaytadan skanerlanadi. So'rov 0.2 s dan 0.8 s
        # ga chiqardi va savdo soni ortgani sayin kvadrat bo'lib
        # o'sardi. Bu yerda esa `selected` ning hajmi to'g'ri
        # baholanadi va reja HASH JOIN bo'lib qoladi.
        if f.review == ReviewState.NEW:
            stmt = stmt.where(selected.c.review_status.is_(None))
        elif f.review in (ReviewState.JUSTIFIED, ReviewState.CONFIRMED):
            stmt = stmt.where(selected.c.review_status == f.review)
        # `ALL` va `None` — filtr yo'q. Ikkalasi bir xil natija beradi,
        # lekin ma'nosi boshqa: `ALL` — rahbarning tanlovi, `None` —
        # parametr umuman berilmagan (router o'shanda `new` yuboradi).
        return stmt

    # ── Ro'yxat ───────────────────────────────────────────────

    async def page(
        self,
        f: ComplianceFilter,
        *,
        page: int = 1,
        page_size: int = 50,
        sort: ComplianceSort = ComplianceSort.DATE,
        order: str = "desc",
    ) -> CompliancePage:
        """Tekshiruv navbatining bir sahifasi."""
        selected = self._selected(f)
        rows = self._rows(f, selected, self._evidence(selected))

        total = (
            await self._session.execute(
                select(func.count()).select_from(rows.subquery("counted"))
            )
        ).scalar_one()

        listed = rows.subquery("listed")
        column = {
            ComplianceSort.DATE: listed.c.occurred_on,
            ComplianceSort.AMOUNT: listed.c.amount_usd,
            ComplianceSort.AGENT: listed.c.agent_name,
            ComplianceSort.PARTNER: listed.c.partner_name,
        }[sort]
        direction = column.desc() if order == "desc" else column.asc()

        result = (
            await self._session.execute(
                select(listed)
                # Ikkilamchi mezon — bir xil qiymatli qatorlar sahifalar
                # orasida sakrab yurmasligi uchun barqaror tartib kerak.
                .order_by(nullslast(direction), listed.c.external_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

        return CompliancePage(
            items=[_to_row(row) for row in result],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ── Hisobot ───────────────────────────────────────────────

    async def summary(self, f: ComplianceFilter) -> ComplianceSummary:
        """Toifalar soni + xodimlar kesimi.

        ⚠️ XULOSA FILTRLARI (`verdict`, `rule`, `review`) BU YERDA
        E'TIBORSIZ QOLDIRILADI. Sabab shartnomada: uchala toifaning ham
        soni ekranda TURISHI kerak. Foydalanuvchi «shubhalilar» ni
        tanlaganda hisobot ham faqat shubhalilarni sanasa, uchta
        katakdan ikkitasi nolga tushardi va «nechta savdo tekshirib
        bo'lmadi» degan savol javobsiz qolardi.

        Davr, xodim, filial va qidiruv esa SAQLANADI — ular ekrandagi
        oynani belgilaydi.
        """
        scope = replace(f, verdict=None, rule=None, review=None)
        selected = self._selected(scope)
        rows = self._rows(scope, selected, self._evidence(selected)).subquery("scoped")

        def counted(condition: Any) -> Any:
            return func.count().filter(condition)

        result = (
            await self._session.execute(
                select(
                    rows.c.agent_id,
                    rows.c.agent_name,
                    func.count().label("sales"),
                    counted(rows.c.verdict == Verdict.OK.value).label("ok"),
                    counted(rows.c.verdict == Verdict.SUSPICIOUS.value).label(
                        "suspicious"
                    ),
                    counted(rows.c.verdict == Verdict.NOT_CHECKABLE.value).label(
                        "not_checkable"
                    ),
                    counted(
                        and_(
                            rows.c.verdict == Verdict.SUSPICIOUS.value,
                            rows.c.review_status.is_(None),
                        )
                    ).label("new"),
                    counted(rows.c.review_status == ReviewState.JUSTIFIED.value).label(
                        "justified"
                    ),
                    counted(rows.c.review_status == ReviewState.CONFIRMED.value).label(
                        "confirmed"
                    ),
                )
                .group_by(rows.c.agent_id, rows.c.agent_name)
                .order_by(func.count().filter(
                    rows.c.verdict == Verdict.SUSPICIOUS.value
                ).desc(), nullslast(rows.c.agent_name.asc()))
            )
        ).all()

        agents = [
            AgentBreakdown(
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                sales=row.sales,
                ok=row.ok,
                suspicious=row.suspicious,
                not_checkable=row.not_checkable,
                new=row.new,
                justified=row.justified,
                confirmed=row.confirmed,
            )
            for row in result
        ]
        # Umumiy sonlar xodimlar kesimidan yig'iladi — ular bir xil
        # to'plamning bo'laklari, ya'ni ikkinchi so'rov ortiqcha
        # bo'lardi va ikki so'rov orasida farq chiqish xavfi bor edi.
        return ComplianceSummary(
            total=sum(a.sales for a in agents),
            ok=sum(a.ok for a in agents),
            suspicious=sum(a.suspicious for a in agents),
            not_checkable=sum(a.not_checkable for a in agents),
            new=sum(a.new for a in agents),
            justified=sum(a.justified for a in agents),
            confirmed=sum(a.confirmed for a in agents),
            window_days=int(f.window_days),
            agents=agents,
        )

    # ── Mijoz kartochkasi (3-bosqich) ─────────────────────────

    async def for_client(
        self,
        phone_key: str,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 200,
        window_days: int | None = None,
    ) -> ClientSales:
        """Bitta mijozning savdolari — yangisidan eskisiga.

        Qo'ng'iroqlar bilan bir vaqt chizig'ida ko'rsatish uchun
        (shartnoma, 7-bo'lim). Mijoz allaqachon tanlangan, shuning
        uchun yagona filtr — DAVR, va u kartochkadagi qo'ng'iroqlar
        bilan BIR XIL bo'lishi shart: bir ekranda ikki xil oyna
        bo'lsa, vaqt chizig'i yolg'on ketma-ketlik ko'rsatardi.

        ⚠️ Davr qoidalarni TORAYTIRMAYDI. «Oldingi savdo» (R2) va
        «butun tarix» (R3) baribir butun tarixdan hisoblanadi
        (`_previous_sale_cte`, `_evidence` izohlariga qarang) — davr
        faqat ekranda nima KO'RINISHINI belgilaydi. Aks holda davr
        boshidagi savdo «birinchi savdo» bo'lib ko'rinardi va o'sha
        savdo nazorat ro'yxatida shubhali, kartochkada esa toza bo'lib
        chiqardi.
        """
        f = ComplianceFilter(
            since=since,
            until=until,
            window_days=window_days
            if window_days is not None
            else DEFAULT_WINDOW_DAYS,
        )
        selected = self._selected(f, phone_key=phone_key)
        rows = self._rows(f, selected, self._evidence(selected)).subquery("client")

        # Yig'ma OYNA FUNKSIYASI bilan — alohida so'rovsiz. `LIMIT`
        # oyna funksiyasidan KEYIN qo'llanadi, ya'ni sonlar butun
        # tanlov bo'yicha to'g'ri qoladi. Ikkinchi so'rov bo'lsa,
        # ikkalasi orasida ma'lumot o'zgarib, yig'ma bilan ro'yxat
        # bir-biriga zid chiqishi mumkin edi.
        result = (
            await self._session.execute(
                select(
                    rows,
                    func.count().over().label("t_total"),
                    func.sum(rows.c.amount_usd).over().label("t_amount"),
                    func.count()
                    .filter(rows.c.verdict == Verdict.SUSPICIOUS.value)
                    .over()
                    .label("t_suspicious"),
                    func.count()
                    .filter(rows.c.verdict == Verdict.NOT_CHECKABLE.value)
                    .over()
                    .label("t_not_checkable"),
                )
                .order_by(rows.c.occurred_on.desc(), rows.c.external_id.desc())
                .limit(limit)
            )
        ).all()

        head = result[0] if result else None
        return ClientSales(
            items=[
                ClientSale(
                    sale_id=row.id,
                    occurred_on=row.occurred_on,
                    external_id=row.external_id,
                    branch=row.branch,
                    direction=row.direction,
                    agent_id=row.agent_id,
                    agent_name=row.agent_name,
                    amount=_number(row.amount),
                    currency=row.currency,
                    amount_usd=_number(row.amount_usd),
                    verdict=row.verdict,
                    broken_rules=_broken(row),
                    last_call_at=row.last_call_at,
                    last_call_agent=row.last_call_agent,
                    days_before=row.days_before,
                    previous_sale_on=row.previous_sale_on,
                    calls_between=row.calls_between,
                    calls_total=row.calls_total,
                    skip_reason=row.skip_reason,
                    review_status=row.review_status,
                )
                for row in result
            ],
            total=head.t_total if head else 0,
            amount_usd=_number(head.t_amount) or 0.0 if head else 0.0,
            suspicious=head.t_suspicious if head else 0,
            not_checkable=head.t_not_checkable if head else 0,
        )


# ══════════════════════════════════════════════════════════════
#  Qatorni ma'lumot shakliga o'tkazish
# ══════════════════════════════════════════════════════════════


def _number(value: Any) -> float | None:
    """`Decimal` → `float`. JSON da `Decimal` yo'q."""
    return None if value is None else float(value)


def _broken(row: Any) -> list[str]:
    """Buzilgan qoidalar — HAR DOIM shu tartibda (R1, R2, R3).

    Tartib barqaror bo'lishi kerak: ekranda belgilar joyini
    almashtirib tursa, ro'yxat o'qib bo'lmaydigan bo'lardi.
    """
    return [
        rule.value
        for rule, broken in ((Rule.R1, row.r1), (Rule.R2, row.r2), (Rule.R3, row.r3))
        if broken
    ]


def _to_row(row: Any) -> ComplianceRow:
    review = (
        SaleReview(
            status=row.review_status,
            reason=row.review_reason,
            note=row.review_note,
            reviewed_by=row.reviewed_by,
            reviewed_at=row.reviewed_at,
        )
        if row.review_status is not None
        else None
    )
    return ComplianceRow(
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
        amount=_number(row.amount),
        currency=row.currency,
        amount_usd=_number(row.amount_usd),
        verdict=SaleVerdict(
            sale_id=row.id,
            verdict=row.verdict,
            broken_rules=_broken(row),
            skip_reason=row.skip_reason,
            last_call_at=row.last_call_at,
            last_call_agent=row.last_call_agent,
            days_before=row.days_before,
            previous_sale_on=row.previous_sale_on,
            calls_between=row.calls_between,
            calls_total=row.calls_total,
        ),
        review=review,
    )


__all__: Sequence[str] = (
    "AgentBreakdown",
    "ClientSale",
    "ClientSales",
    "CompliancePage",
    "ComplianceFilter",
    "ComplianceService",
    "ComplianceSort",
    "ComplianceSummary",
    "ComplianceRow",
    "ReviewState",
    "Rule",
    "SaleReview",
    "SaleVerdict",
    "SkipReason",
    "Verdict",
    "resolve_window_days",
)
