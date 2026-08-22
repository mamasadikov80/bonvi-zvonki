"""SAP eksportlarini bazaga yozish.

Uch kirish nuqtasi bor:
  · `import_file(...)`     — turini o'zi aniqlab keraklisiga uzatadi
                             (`POST /sales/import` shuni chaqiradi);
  · `import_register(...)` — operatsiyalar registri → `sales`;
  · `import_catalog(...)`  — kontragentlar katalogi (wb3) yoki balans
                             hisoboti (wb1/wb2) → `sale_partners`.

IDEMPOTENTLIK — asosiy talab. Foydalanuvchi bir faylni ikki marta
yuklashi (yoki kunlik eksportlar bir-birini qoplab ketishi) MUTLAQ
normal holat. Shuning uchun hamma narsa `ON CONFLICT DO UPDATE` ga
tushadi: `sales.external_id` va `sale_partners.code` bo'yicha.

⚠️ YO'QOTMASLIK QOIDASI. Upsert HECH QACHON to'ldirilgan maydonni
bo'sh qiymat bilan almashtirmaydi (`coalesce`). Sabab amaliy: fayllar
har xil to'liqlikda keladi — balans hisobotida telefon bor, katalogda
yo'q; katalog eski, registr yangi. Oddiy «ustidan yoz» qoidasi bilan
har import bir nima yo'qotardi va buni hech kim sezmasdi.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.sales.application.reader import (
    KIND_LABELS,
    SalesFileError,
    SalesFileKind,
    SalesWorkbook,
    parse_balance,
    parse_catalog,
    parse_register,
    read_workbook,
)
from src.modules.sales.domain.entities import SaleOpType, normalize_branch
from src.modules.sales.infrastructure.models import (
    SaleBranchModel,
    SaleModel,
    SalePartnerModel,
)

#: Bitta `INSERT` ga necha qator sig'adi.
#
# ⚠️ CHEGARA BAZANIKI: PostgreSQL protokoli bitta so'rovda 32 767
# parametrga ruxsat beradi. `sales` da 16 ustun bor, ya'ni 2384 qatorli
# kunlik eksport BITTA so'rovga solinsa 38 144 parametr chiqadi va
# import «too many arguments» bilan yiqilardi. Katalog (3746 × 10)
# ham chegaraga yaqin. 500 qator har qanday jadval uchun xavfsiz
# zaxira qoldiradi.
_CHUNK = 500


@dataclass(slots=True)
class ImportReport:
    """Import natijasi — foydalanuvchiga ko'rsatiladi.

    Har son ALOHIDA savolga javob beradi, shuning uchun ular
    qo'shilmaydi va bir-birini almashtirmaydi.
    """

    kind: SalesFileKind
    source: str

    read: int = 0
    """Fayldan o'qilgan ma'noli qatorlar soni."""

    created: int = 0
    updated: int = 0

    skipped: int = 0
    """Yozib bo'lmagan qatorlar: kod yoki sana yo'q.

    Bu XATO EMAS deb hisoblanmaydi — son noldan katta bo'lsa eksportda
    nuqson bor va foydalanuvchi buni ko'rishi kerak."""

    unknown_partner: int = 0
    """Kodi katalogda topilmagan qatorlar.

    ⚠️ Savdo baribir SAQLANADI, faqat `phone_key` siz qoladi va
    qoidalar uni tekshira olmaydi. Chora — katalogni qaytadan
    yuklash."""

    unknown_op_type: int = 0
    """SAP da tanilmagan `Тип`. Qator `op_type = other` bilan saqlanadi."""

    phones_filled: int = 0
    """Balans hisobotidan to'ldirilgan telefonlar (katalogda yo'q edi)."""

    linked_sales: int = 0
    """Katalog/filial yangilangach `sales` da tiklangan bog'lanishlar."""

    unmatched_branches: list[str] = field(default_factory=list)
    """Xodimga biriktirilmagan filiallar — rahbar qo'lda bog'lashi kerak.

    Ro'yxat ATAYLAB nomlar bilan qaytadi, son bilan emas: «7 ta filial
    biriktirilmadi» degan xabar bilan hech nima qilib bo'lmaydi,
    «Логистика, Маркетинг булими…» bilan esa darhol ish boshlanadi."""


# ══════════════════════════════════════════════════════════════
#  Kirish nuqtasi
# ══════════════════════════════════════════════════════════════


async def import_file(
    session: AsyncSession, source: Any, *, filename: str = ""
) -> ImportReport:
    """Faylni turiga qarab kerakli importga uzatadi.

    Tur SARLAVHA bo'yicha aniqlanadi — fayl nomiga tayanilmaydi.
    """
    book = read_workbook(source, filename=filename)
    if book.kind is SalesFileKind.REGISTER:
        return await _import_register(session, book, filename)
    if book.kind is SalesFileKind.CATALOG:
        return await _import_catalog(session, book, filename)
    return await _import_balance(session, book, filename)


async def import_register(
    session: AsyncSession, source: Any, *, filename: str = ""
) -> ImportReport:
    """`savdo kunlik.xlsx` → `sales`."""
    book = _expect(source, filename, SalesFileKind.REGISTER)
    return await _import_register(session, book, filename)


async def import_catalog(
    session: AsyncSession, source: Any, *, filename: str = ""
) -> ImportReport:
    """Kontragentlar katalogi (wb3) yoki balans hisoboti (wb1/wb2).

    Ikkalasi ham `sale_partners` ga yozadi, lekin BOSHQACHA:
      · katalog — to'liq upsert (nom, guruh, filial, telefon, faollik);
      · balans  — FAQAT yetishmagan telefonni to'ldiradi.

    Sabab: balans hisobotida `Kod` noyob emas (qator = mijoz × filial ×
    yo'nalish) va unda `Код группы` yo'q. Undan kontragent yaratish
    guruhi noma'lum qatorlarni tug'dirardi, guruh esa nazorat
    doirasini belgilaydi (yetkazib beruvchilar tekshirilmaydi).
    """
    book = _expect(source, filename, SalesFileKind.CATALOG, SalesFileKind.BALANCE)
    if book.kind is SalesFileKind.CATALOG:
        return await _import_catalog(session, book, filename)
    return await _import_balance(session, book, filename)


def _expect(source: Any, filename: str, *kinds: SalesFileKind) -> SalesWorkbook:
    """Faylni o'qiydi va turi kutilganidan bo'lishini tekshiradi.

    Xato xabari fayl NIMA ekanini ham aytadi — «noto'g'ri fayl» degan
    xabar bilan foydalanuvchi qaysi tugmani bosishni bilmaydi.
    """
    book = read_workbook(source, filename=filename)
    if book.kind not in kinds:
        kutilgan = " yoki ".join(KIND_LABELS[kind] for kind in kinds)
        raise SalesFileError(
            f"«{filename or 'fayl'}» — bu {KIND_LABELS[book.kind]}, "
            f"{kutilgan} emas. Faylni to'g'ri bo'limga yuklang."
        )
    return book


# ══════════════════════════════════════════════════════════════
#  Registr → `sales`
# ══════════════════════════════════════════════════════════════


async def _import_register(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> ImportReport:
    rows = parse_register(book)
    report = ImportReport(
        kind=book.kind, source=filename or "savdo registri", read=len(rows)
    )

    phones = await _partner_phones(session)
    branches = await _resolve_branches(session, {r.branch for r in rows if r.branch})

    now = datetime.now(UTC)
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.op_type is SaleOpType.OTHER:
            report.unknown_op_type += 1
        if not row.partner_code or row.occurred_on is None:
            # Kodsiz yoki sanasiz qator qoidalarga umuman kirmaydi va
            # `occurred_on` ustuni `NOT NULL` — yozib bo'lmaydi.
            report.skipped += 1
            continue

        key = phones.get(row.partner_code)
        if row.partner_code not in phones:
            report.unknown_partner += 1

        # ⚠️ Bir `Номер операции` faylda ikki marta uchraydi (o'lchandi:
        # 2384 qatorda 2383 noyob). PostgreSQL bitta `ON CONFLICT` da
        # bir qatorni ikki marta o'zgartira olmaydi — «cannot affect
        # row a second time» xatosi butun importni yiqitardi. Lug'at
        # oxirgi ko'rinishni qoldiradi.
        payload[row.external_id] = {
            "id": uuid4(),
            "external_id": row.external_id,
            "doc_number": row.doc_number,
            "op_type": str(row.op_type),
            "occurred_on": row.occurred_on,
            "branch": row.branch,
            "direction": row.direction,
            "partner_code": row.partner_code,
            "partner_name": row.partner_name,
            "amount": row.amount,
            "amount_usd": row.amount_usd,
            "currency": row.currency,
            "agent_id": branches.get(row.branch or ""),
            "phone_key": key,
            "source_file": (filename or "")[:255] or None,
            "imported_at": now,
        }

    created, updated = await _upsert_sales(session, list(payload.values()))
    report.created, report.updated = created, updated
    report.unmatched_branches = sorted(
        name for name, agent_id in branches.items() if agent_id is None
    )
    await session.commit()
    return report


async def _upsert_sales(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> tuple[int, int]:
    created = updated = 0
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        stmt = pg_insert(SaleModel).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SaleModel.external_id],
            set_={
                "doc_number": stmt.excluded.doc_number,
                "op_type": stmt.excluded.op_type,
                "occurred_on": stmt.excluded.occurred_on,
                "branch": stmt.excluded.branch,
                "direction": stmt.excluded.direction,
                "partner_code": stmt.excluded.partner_code,
                "partner_name": stmt.excluded.partner_name,
                "amount": stmt.excluded.amount,
                "amount_usd": stmt.excluded.amount_usd,
                "currency": stmt.excluded.currency,
                # ⚠️ `coalesce` — registr katalogdan OLDIN yuklangan
                # bo'lsa `phone_key` bo'sh keladi. Busiz keyingi
                # import allaqachon topilgan telefonni o'chirib
                # yuborardi va qoidalar mijozni «telefonsiz» deb
                # nazoratdan chiqarardi.
                "phone_key": func.coalesce(
                    stmt.excluded.phone_key, SaleModel.phone_key
                ),
                # Xuddi shu sabab: rahbar filialga xodim biriktirgan
                # bo'lsa, keyingi import uni bo'sh qiymat bilan
                # almashtirmasin.
                "agent_id": func.coalesce(stmt.excluded.agent_id, SaleModel.agent_id),
                "source_file": stmt.excluded.source_file,
                "imported_at": func.now(),
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))

        result = await session.execute(stmt)
        flags = [bool(row[0]) for row in result.all()]
        created += sum(flags)
        updated += len(flags) - sum(flags)
    return created, updated


# ══════════════════════════════════════════════════════════════
#  Katalog → `sale_partners`
# ══════════════════════════════════════════════════════════════


async def _import_catalog(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> ImportReport:
    rows = parse_catalog(book)
    report = ImportReport(
        kind=book.kind, source=filename or "kontragentlar katalogi", read=len(rows)
    )

    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload[row.code] = {
            "id": uuid4(),
            "code": row.code,
            "name": row.name,
            "group_name": row.group_name,
            "branch": row.branch,
            "phone": row.phone,
            "phone_key": row.phone_key,
            "is_active": row.is_active,
            "telegram_link": row.telegram_link,
        }

    for start in range(0, len(payload), _CHUNK):
        chunk = list(payload.values())[start : start + _CHUNK]
        stmt = pg_insert(SalePartnerModel).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SalePartnerModel.code],
            set_={
                "name": stmt.excluded.name,
                "group_name": stmt.excluded.group_name,
                "branch": stmt.excluded.branch,
                # ⚠️ `coalesce` — katalogda telefon 94.7% to'ldirilgan,
                # qolganini balans hisobotidan olamiz. Oddiy «ustidan
                # yoz» bilan har katalog importi o'sha to'ldirishni
                # o'chirib tashlardi.
                "phone": func.coalesce(stmt.excluded.phone, SalePartnerModel.phone),
                "phone_key": func.coalesce(
                    stmt.excluded.phone_key, SalePartnerModel.phone_key
                ),
                "is_active": stmt.excluded.is_active,
                "telegram_link": func.coalesce(
                    stmt.excluded.telegram_link, SalePartnerModel.telegram_link
                ),
                "updated_at": func.now(),
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))

        result = await session.execute(stmt)
        flags = [bool(row[0]) for row in result.all()]
        report.created += sum(flags)
        report.updated += len(flags) - sum(flags)

    report.linked_sales = await backfill_sale_links(session)
    await session.commit()
    return report


async def _import_balance(
    session: AsyncSession, book: SalesWorkbook, filename: str
) -> ImportReport:
    """Balans hisobotidan FAQAT yetishmagan telefonni oladi."""
    rows = parse_balance(book)
    report = ImportReport(
        kind=book.kind, source=filename or "balans hisoboti", read=len(rows)
    )

    known = dict(
        (
            await session.execute(
                select(SalePartnerModel.code, SalePartnerModel.phone_key)
            )
        ).all()
    )

    # Kod bo'yicha birinchi ma'noli raqam olinadi: bir kod bir necha
    # qatorda (filial × yo'nalish) takrorlanadi va ularda odatda bir
    # xil raqam turadi.
    fills: dict[str, tuple[str | None, str]] = {}
    seen: set[str] = set()
    for row in rows:
        if row.code not in known:
            if row.code not in seen:
                report.unknown_partner += 1
                seen.add(row.code)
            continue
        if known[row.code] is not None or row.phone_key is None:
            continue
        fills.setdefault(row.code, (row.phone, row.phone_key))

    codes = list(fills)
    for start in range(0, len(codes), _CHUNK):
        chunk = codes[start : start + _CHUNK]
        await session.execute(
            update(SalePartnerModel)
            .where(SalePartnerModel.code.in_(chunk))
            # ⚠️ `phone_key IS NULL` sharti SO'ROVDA ham takrorlanadi:
            # ro'yxat yuqorida tuzilgan, oradan vaqt o'tgan bo'lishi
            # mumkin va boshqa import shu paytda telefon yozib
            # ulgurgan bo'lsa uni bosib ketmaymiz.
            .where(SalePartnerModel.phone_key.is_(None))
            .values(
                phone=case(
                    {code: fills[code][0] for code in chunk},
                    value=SalePartnerModel.code,
                ),
                phone_key=case(
                    {code: fills[code][1] for code in chunk},
                    value=SalePartnerModel.code,
                ),
                updated_at=func.now(),
            )
        )
    report.phones_filled = len(fills)
    report.updated = len(fills)

    report.linked_sales = await backfill_sale_links(session)
    await session.commit()
    return report


# ══════════════════════════════════════════════════════════════
#  Bog'lanishlar: kod → telefon, filial → xodim
# ══════════════════════════════════════════════════════════════


async def _partner_phones(session: AsyncSession) -> dict[str, str | None]:
    """Katalogdagi `kod → phone_key` xaritasi.

    Butun katalog xotiraga olinadi (3746 qator — bir necha yuz kilobayt).
    Muqobil — har savdo uchun alohida so'rov, ya'ni 2384 ta borish-kelish.
    """
    rows = (
        await session.execute(
            select(SalePartnerModel.code, SalePartnerModel.phone_key)
        )
    ).all()
    return {code: key for code, key in rows}


async def _resolve_branches(
    session: AsyncSession, names: set[str]
) -> dict[str, UUID | None]:
    """Filial nomlarini xodimga bog'laydi va yangilarini ro'yxatga qo'shadi.

    Uch bosqich:
      1. `sale_branches` da qatori bor filial — O'SHA qaror ustun
         turadi (rahbar qo'lda qo'ygan bo'lishi mumkin);
      2. qolganlari nom normalizatsiyasi bilan `agents.full_name` ga
         solishtiriladi (`Навоий` → `Навои`, `Жиззах` → `Джиззах`);
      3. topilmagani ham `sale_branches` ga YOZILADI — `agent_id`
         bo'sh holda.

    ⚠️ 3-bosqich muhim: busiz rahbar qaysi filiallar biriktirilmaganini
    bilmasdi va admin panelida biriktirish uchun ro'yxat bo'sh bo'lardi.
    «Логистика», «Маркетинг булими» kabi bo'limlarda qo'ng'iroq yozuvi
    umuman yo'q va ular ataylab ko'rinib turishi kerak.
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
    # Bir xil normallashgan nomli ikki xodim bo'lsa — TAXMIN
    # QILMAYMIZ. Noto'g'ri xodimga savdo yozib qo'yish bo'sh
    # qoldirishdan yomonroq: keyin uni hech kim tekshirmaydi.
    by_name: dict[str, UUID | None] = {}
    for agent_id, full_name in agents:
        key = normalize_branch(full_name)
        by_name[key] = None if key in by_name else agent_id

    resolved: dict[str, UUID | None] = {}
    fresh: list[dict[str, Any]] = []
    for name in names:
        if name in existing:
            resolved[name] = existing[name]
            continue
        agent_id = by_name.get(normalize_branch(name))
        resolved[name] = agent_id
        fresh.append(
            {
                "branch": name,
                "agent_id": agent_id,
                "matched_automatically": agent_id is not None,
            }
        )

    for start in range(0, len(fresh), _CHUNK):
        chunk = fresh[start : start + _CHUNK]
        # ⚠️ `DO NOTHING`, `DO UPDATE` EMAS. Filial qatori allaqachon
        # bo'lsa (yuqorida `existing` ga tushmagan bo'lsa ham — parallel
        # import) rahbarning qo'lda biriktirgani saqlanib qolsin.
        await session.execute(
            pg_insert(SaleBranchModel)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=[SaleBranchModel.branch])
        )
    return resolved


async def backfill_sale_links(session: AsyncSession) -> int:
    """`sales` dagi bo'sh bog'lanishlarni joriy katalogdan tiklaydi.

    NEGA KERAK: import tartibi foydalanuvchi qo'lida. U avval savdo
    registrini, keyin katalogni yuklashi mumkin — o'shanda savdolar
    `phone_key` siz qolib ketardi va qoidalar butun kunni «telefonsiz»
    deb nazoratdan chiqarardi. Xato JIMGINA bo'lardi: ro'yxat bo'sh
    ko'rinardi, ya'ni «hammasi joyida» degan ma'no berardi.

    Shuning uchun katalog har yangilanganda bog'lanishlar qaytadan
    yoziladi. Faqat BO'SH maydonlar to'ldiriladi — mavjud qiymat
    tegilmaydi.

    Rahbar filialga xodim biriktirganda (2-bosqich, admin panel) ham
    shu funksiya chaqiriladi.
    """
    phone_result = await session.execute(
        update(SaleModel)
        .where(SaleModel.partner_code == SalePartnerModel.code)
        .where(SalePartnerModel.phone_key.is_not(None))
        .where(SaleModel.phone_key.is_(None))
        .values(phone_key=SalePartnerModel.phone_key)
    )
    agent_result = await session.execute(
        update(SaleModel)
        .where(SaleModel.branch == SaleBranchModel.branch)
        .where(SaleBranchModel.agent_id.is_not(None))
        .where(SaleModel.agent_id.is_(None))
        .values(agent_id=SaleBranchModel.agent_id)
    )
    return (phone_result.rowcount or 0) + (agent_result.rowcount or 0)
