"""Import oldidan HISOB-KITOB — bazaga hech narsa yozilmaydi.

NEGA KERAK. Ilgari fayl tanlanishi bilan bazaga tushardi va
foydalanuvchi nima kirganini FAQAT KEYIN ko'rardi. Ikkita xato
jimgina o'tib ketardi:

  · noto'g'ri fayl (o'tgan haftaning eksporti, boshqa bo'limniki) —
    savdolar bazaga tushib bo'lgan, orqaga qaytarish yo'q;
  · takroriy yuklash — hisobotda «0 yangi» chiqardi, lekin buni
    ko'rish uchun ham import BAJARILGAN bo'lishi kerak edi.

Endi ketma-ketlik boshqacha: `POST /sales/import/preview` faylni
o'qiydi, bazadan FAQAT SO'RAYDI va nima bo'lishini aytadi.
Foydalanuvchi tasdiqlagach o'sha faylning O'ZI `POST /sales/import`
ga boradi.

⚠️ BU MODULDA `INSERT`/`UPDATE`/`commit` BO'LMASLIGI KERAK. Bu
shartning o'zi testda tekshiriladi (`test_sales_preview.py`):
preview dan oldin va keyin `select count(*)` teng bo'lishi shart.
Shu sababli bu yerda `importer._resolve_branches` ISHLATILMAYDI —
u topilmagan filialni `sale_branches` ga YOZADI.

⚠️ BAZAGA HAR TUR UCHUN BITTA SO'ROV. Fayldagi 2383 operatsiya
raqami uchun 2383 ta `SELECT` qilish bir necha o'n soniya olardi va
hisob-kitob oynasi importning o'zidan sekinroq bo'lardi.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.sales.application.reader import (
    SalesFileKind,
    SalesWorkbook,
    parse_balance,
    parse_catalog,
    parse_register,
    read_workbook,
)
from src.modules.sales.domain.entities import (
    OP_TYPE_LABELS,
    SaleOpType,
    normalize_branch,
)
from src.modules.sales.infrastructure.models import (
    SaleBranchModel,
    SaleModel,
    SalePartnerModel,
)

#: Ekranda ko'rsatiladigan topilmagan kodlar soni.
#
# Ro'yxatning O'ZI kerak (son bilan hech nima qilib bo'lmaydi), lekin
# 500 ta kod modalni bosib ketardi. Umumiy son alohida maydonda
# (`unknown_partner_count`) qaytadi va matn «20 tasi ko'rsatilgan»
# deyishi mumkin.
MAX_UNKNOWN_PARTNERS = 20

#: Guruhi/filiali ko'rsatilmagan qatorlar shu yorliq ostida yig'iladi.
_NO_GROUP = "—"


@dataclass(frozen=True, slots=True)
class PreviewTypeRow:
    """Tur (registr) yoki guruh/filial (katalog, balans) kesimi."""

    type: str
    label: str
    count: int
    amount_usd: float | None = None


@dataclass(frozen=True, slots=True)
class PreviewDayRow:
    """Kun kesimi — faqat registr uchun."""

    day: date
    count: int
    amount_usd: float | None = None


@dataclass(slots=True)
class SalesPreview:
    """Tasdiqlashdan oldin ko'rsatiladigan hisob-kitob.

    Sonlar ALOHIDA savollarga javob beradi va qo'shilmaydi:
    `rows` — fayldagi ma'noli qatorlar, `new_rows`/`existing_rows` —
    NOYOB kalitlar bo'yicha bazadagi holat. Ikkisi teng bo'lmasligi
    mumkin va bu normal: faylda takrorlangan kalit uchraydi
    (o'lchandi — 2384 qatorda 2383 noyob operatsiya raqami).
    """

    kind: str
    filename: str
    rows: int = 0

    date_from: date | None = None
    date_to: date | None = None

    by_type: list[PreviewTypeRow] = field(default_factory=list)
    by_day: list[PreviewDayRow] = field(default_factory=list)

    new_rows: int = 0
    """Bazada YO'Q kalitlar (registrda `external_id`, qolganida `code`)."""

    existing_rows: int = 0
    """Allaqachon bor kalitlar — ular ustiga yoziladi, nusxa chiqmaydi."""

    unknown_partners: list[str] = field(default_factory=list)
    unknown_partner_count: int = 0

    unmatched_branches: list[str] = field(default_factory=list)
    """Xodimga biriktirilmagan filiallar — NOMLARI bilan.

    ⚠️ Bu yerda ro'yxat bazaga YOZILMAYDI (importdan farqi shu):
    filial `sale_branches` ga faqat haqiqiy import paytida tushadi."""

    without_phone: int = 0
    """Telefon kaliti olinmaydigan qatorlar — ular nazoratdan tashqarida."""

    warnings: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  Kirish nuqtasi
# ══════════════════════════════════════════════════════════════


async def build_preview(
    session: AsyncSession, source: Any, *, filename: str = ""
) -> SalesPreview:
    """Faylni o'qiydi va nima bo'lishini hisoblaydi. YOZMAYDI.

    Tur SARLAVHA bo'yicha aniqlanadi — aynan importdagidek, ya'ni
    hisob-kitobda ko'ringan tur bilan yoziladigan tur bir xil bo'ladi.
    Fayl tanilmasa `SalesFileError` (422) chiqadi va foydalanuvchi
    noto'g'ri faylni tasdiqlash bosqichiga umuman olib bora olmaydi.
    """
    book = read_workbook(source, filename=filename)
    if book.kind is SalesFileKind.REGISTER:
        return await _register_preview(session, book, filename)
    if book.kind is SalesFileKind.CATALOG:
        return await _catalog_preview(session, book, filename)
    return await _balance_preview(session, book, filename)


# ══════════════════════════════════════════════════════════════
#  Registr
# ══════════════════════════════════════════════════════════════


async def _register_preview(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> SalesPreview:
    rows = parse_register(book)
    preview = SalesPreview(
        kind=str(book.kind),
        filename=filename or "savdo registri",
        rows=len(rows),
    )

    type_count: Counter[SaleOpType] = Counter()
    type_sum: defaultdict[SaleOpType, Decimal] = defaultdict(Decimal)
    day_count: Counter[date] = Counter()
    day_sum: defaultdict[date, Decimal] = defaultdict(Decimal)

    no_date = no_amount = no_code = 0
    for row in rows:
        type_count[row.op_type] += 1
        if row.amount_usd is None:
            no_amount += 1
        else:
            type_sum[row.op_type] += row.amount_usd

        if row.occurred_on is None:
            no_date += 1
        else:
            day_count[row.occurred_on] += 1
            if row.amount_usd is not None:
                day_sum[row.occurred_on] += row.amount_usd

        if not row.partner_code:
            no_code += 1

    if day_count:
        preview.date_from = min(day_count)
        preview.date_to = max(day_count)

    # Turlar KO'PLIGI bo'yicha: birinchi qatorda «Продажа» turishi
    # kerak — hisob-kitobning butun ma'nosi o'sha sonda.
    preview.by_type = [
        PreviewTypeRow(
            type=str(op_type),
            label=OP_TYPE_LABELS.get(op_type, str(op_type)),
            count=count,
            amount_usd=_money(type_sum.get(op_type)),
        )
        for op_type, count in sorted(
            type_count.items(), key=lambda pair: (-pair[1], pair[0])
        )
    ]
    # Kunlar esa VAQT bo'yicha: diagramma sifatida o'qiladi.
    preview.by_day = [
        PreviewDayRow(
            day=day, count=day_count[day], amount_usd=_money(day_sum.get(day))
        )
        for day in sorted(day_count)
    ]

    # ── Bazadagi holat: BITTA so'rov ────────────────────────────
    ids = {row.external_id for row in rows}
    known_ids = await _existing(session, SaleModel.external_id, ids)
    preview.existing_rows = len(known_ids)
    preview.new_rows = len(ids) - len(known_ids)

    # ── Katalog bilan solishtirish: yana BITTA so'rov ───────────
    codes = {row.partner_code for row in rows if row.partner_code}
    phones = await _partner_phones(session, codes)
    unknown = sorted(codes - phones.keys())
    preview.unknown_partner_count = len(unknown)
    preview.unknown_partners = unknown[:MAX_UNKNOWN_PARTNERS]
    preview.without_phone = sum(
        1 for row in rows if phones.get(row.partner_code or "") is None
    )

    branches = await _match_branches(session, {r.branch for r in rows if r.branch})
    preview.unmatched_branches = sorted(
        name for name, agent_id in branches.items() if agent_id is None
    )

    duplicates = len(rows) - len(ids)
    unknown_types = type_count.get(SaleOpType.OTHER, 0)
    preview.warnings = _warnings(
        (no_date, "{n} qatorda sana o'qilmadi — ular bazaga yozilmaydi"),
        (no_code, "{n} qatorda mijoz kodi yo'q — ular bazaga yozilmaydi"),
        (no_amount, "{n} qatorda summa o'qilmadi"),
        (
            duplicates,
            "{n} ta operatsiya raqami faylda takrorlangan — "
            "har biridan oxirgi ko'rinishi yoziladi",
        ),
        (
            unknown_types,
            "{n} qatorning turi SAP da tanilmadi — ular «boshqa» "
            "bo'lib saqlanadi va qoidalarga kirmaydi",
        ),
    )
    return preview


# ══════════════════════════════════════════════════════════════
#  Katalog
# ══════════════════════════════════════════════════════════════


async def _catalog_preview(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> SalesPreview:
    """Kontragentlar katalogi.

    Sana ham, summa ham yo'q — shuning uchun `by_day` bo'sh, `by_type`
    esa GURUH kesimini ko'rsatadi (`Клиенты`, `Поставщики импорт`…).
    Nazorat faqat «Клиенты» guruhiga qo'llanadi, ya'ni bu son
    foydalanuvchi uchun eng ma'nolisi.
    """
    rows = parse_catalog(book)
    preview = SalesPreview(
        kind=str(book.kind),
        filename=filename or "kontragentlar katalogi",
        rows=len(rows),
    )

    groups: Counter[str] = Counter(row.group_name or _NO_GROUP for row in rows)
    preview.by_type = _label_rows(groups)

    codes = {row.code for row in rows}
    known = await _existing(session, SalePartnerModel.code, codes)
    preview.existing_rows = len(known)
    preview.new_rows = len(codes) - len(known)

    preview.without_phone = sum(1 for row in rows if row.phone_key is None)
    inactive = sum(1 for row in rows if not row.is_active)

    preview.warnings = _warnings(
        (
            len(rows) - len(codes),
            "{n} ta kod faylda takrorlangan — har biridan oxirgi "
            "ko'rinishi yoziladi",
        ),
        (
            preview.without_phone,
            "{n} kontragentdan telefon kaliti olinmadi — ular savdo "
            "nazoratiga kirmaydi (raqam yo'q, chet el yoki soxta)",
        ),
        (inactive, "{n} kontragent «Неактив» deb belgilangan"),
    )
    return preview


# ══════════════════════════════════════════════════════════════
#  Balans hisoboti
# ══════════════════════════════════════════════════════════════


async def _balance_preview(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> SalesPreview:
    """Balans hisoboti — undan FAQAT yetishmagan telefon olinadi.

    ⚠️ Bu yerda `new_rows` «yangi kontragent qo'shiladi» degani EMAS:
    balans faylidan kontragent YARATILMAYDI (unda `Код группы` yo'q).
    Kodi bazada bo'lmagan qatorlar shunchaki e'tiborsiz qoladi va
    ogohlantirish aynan shuni aytadi.
    """
    rows = parse_balance(book)
    preview = SalesPreview(
        kind=str(book.kind),
        filename=filename or "balans hisoboti",
        rows=len(rows),
    )

    # Bu faylda `Kod` NOYOB EMAS (qator = mijoz × filial × yo'nalish),
    # shuning uchun kesim BO'LIM bo'yicha olinadi — u qatorlarni
    # haqiqatan bo'lib beradi.
    preview.by_type = _label_rows(
        Counter(row.branch or _NO_GROUP for row in rows)
    )

    codes = {row.code for row in rows}
    known = await _existing(session, SalePartnerModel.code, codes)
    preview.existing_rows = len(known)
    preview.new_rows = len(codes) - len(known)

    unknown = sorted(codes - known)
    preview.unknown_partner_count = len(unknown)
    preview.unknown_partners = unknown[:MAX_UNKNOWN_PARTNERS]
    preview.without_phone = sum(1 for row in rows if row.phone_key is None)

    preview.warnings = _warnings(
        (
            len(unknown),
            "{n} ta kod katalogda yo'q — balans faylidan yangi "
            "kontragent yaratilmaydi, bu qatorlar o'tkazib yuboriladi",
        ),
        (
            preview.without_phone,
            "{n} qatordan telefon kaliti olinmadi — ulardan foyda yo'q",
        ),
    )
    return preview


# ══════════════════════════════════════════════════════════════
#  Bazaga so'rovlar — FAQAT O'QISH
# ══════════════════════════════════════════════════════════════


async def _existing(session: AsyncSession, column: Any, keys: set[str]) -> set[str]:
    """Fayldagi kalitlardan bazada BOR bo'lganlari.

    ⚠️ BITTA `SELECT`. Har kalit uchun alohida so'rov 2383 ta
    borish-kelish demak edi.
    """
    if not keys:
        return set()
    result = await session.execute(select(column).where(column.in_(list(keys))))
    return {row[0] for row in result.all()}


async def _partner_phones(
    session: AsyncSession, codes: set[str]
) -> dict[str, str | None]:
    """Fayldagi kodlar uchun `kod → phone_key`.

    Butun katalog emas, FAQAT fayldagi kodlar so'raladi: hisob-kitob
    oynasi tezkor bo'lishi kerak, importdan farqli o'laroq unda
    kutish sababsiz ko'rinadi.
    """
    if not codes:
        return {}
    result = await session.execute(
        select(SalePartnerModel.code, SalePartnerModel.phone_key).where(
            SalePartnerModel.code.in_(list(codes))
        )
    )
    return {code: key for code, key in result.all()}


async def _match_branches(
    session: AsyncSession, names: set[str]
) -> dict[str, UUID | None]:
    """Filial → xodim, LEKIN hech narsa yozmasdan.

    `importer._resolve_branches` bilan bir xil qoida (avval
    `sale_branches` dagi qaror, keyin nom normalizatsiyasi), faqat
    uchinchi qadami — topilmagan filialni jadvalga qo'shish — YO'Q.
    Aks holda «hech narsa yozilmaydi» va'dasi buzilardi: foydalanuvchi
    bekor qilsa ham `sale_branches` da yangi qatorlar qolib ketardi.
    """
    if not names:
        return {}

    existing = dict(
        (
            await session.execute(
                select(SaleBranchModel.branch, SaleBranchModel.agent_id).where(
                    SaleBranchModel.branch.in_(list(names))
                )
            )
        ).all()
    )

    agents = (
        await session.execute(
            select(AgentModel.id, AgentModel.full_name).where(
                AgentModel.archived_at.is_(None)
            )
        )
    ).all()
    by_name: dict[str, UUID | None] = {}
    for agent_id, full_name in agents:
        key = normalize_branch(full_name)
        by_name[key] = None if key in by_name else agent_id

    return {
        name: existing[name]
        if name in existing
        else by_name.get(normalize_branch(name))
        for name in names
    }


# ══════════════════════════════════════════════════════════════
#  Mayda yordamchilar
# ══════════════════════════════════════════════════════════════


def _money(value: Decimal | None) -> float | None:
    """Summani JSON uchun songa aylantiradi. Nol ham SON — `null` emas.

    ⚠️ `None` va `0` bu yerda har xil ma'no beradi: birinchisi «summa
    umuman yo'q» (to'lov qatorlari), ikkinchisi «nol summa». Ekranda
    ular boshqacha ko'rinadi.
    """
    return None if value is None else round(float(value), 2)


def _label_rows(counts: Counter[str]) -> list[PreviewTypeRow]:
    """Nomli kesim (guruh, bo'lim) — `by_type` shakliga soladi."""
    return [
        PreviewTypeRow(type=name, label=name, count=count)
        for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _warnings(*items: tuple[int, str]) -> list[str]:
    """Nolga teng ogohlantirish YOZILMAYDI.

    «0 qatorda sana o'qilmadi» degan qator foydali ma'lumot emas,
    lekin haqiqiy ogohlantirishni ko'zdan yashirardi.
    """
    return [text.format(n=count) for count, text in items if count > 0]
