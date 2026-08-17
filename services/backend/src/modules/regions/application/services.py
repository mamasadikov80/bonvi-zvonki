"""Hudud servisi — ro'yxat, qo'shish, kaskad nom o'zgartirish, o'chirish.

Bu modulning butun mavjudlik sababi bitta qoidada: hudud nomi uch jadvalda
MATN bo'lib takrorlanadi, shuning uchun nomni faqat `regions` jadvalida
o'zgartirish — ma'lumotni yetim qoldirish demak. `update()` nomni o'zgartirsa,
`agents.region`, `clients.region`, `telegram_groups.region` ni O'SHA
tranzaksiyada yangilaydi. Ikkalasidan biri bajarilmasa — ikkalasi ham
bajarilmaydi.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.groups.application.agent_regions import agent_region_names
from src.modules.groups.infrastructure.models import TelegramGroupModel
from src.modules.regions.domain.entities import (
    REGION_NAME_MAX,
    SORT_ORDER_STEP,
    normalize_region_name,
    usage_phrase_uz,
)
from src.modules.regions.infrastructure.models import RegionModel

# (javobdagi kalit, model) — ishlatilish hisobi ham, kaskad yangilash ham
# shu bitta ro'yxatdan yuradi. Yangi jadvalda `region` paydo bo'lsa,
# uni faqat shu yerga qo'shish kifoya.
REGION_HOLDERS: tuple[tuple[str, Any], ...] = (
    ("agents", AgentModel),
    ("clients", ClientModel),
    ("groups", TelegramGroupModel),
)

EMPTY_USAGE: dict[str, int] = {key: 0 for key, _ in REGION_HOLDERS}


class RegionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Ichki yordamchilar ────────────────────────────────────

    async def _get(self, region_id: UUID) -> RegionModel:
        region = await self._session.get(RegionModel, region_id)
        if region is None:
            raise NotFoundError("Hudud topilmadi")
        return region

    async def _usage_map(self) -> dict[str, dict[str, int]]:
        """Nom → {agents, clients, groups} — hamma hudud uchun bir marta.

        Uchta `GROUP BY`, har hudud uchun alohida `COUNT` emas: ro'yxat
        13 qatordan iborat bo'lsa ham 39 ta so'rov yubormaymiz.
        """
        usage: dict[str, dict[str, int]] = {}
        for key, model in REGION_HOLDERS:
            rows = await self._session.execute(
                select(model.region, func.count())
                .where(model.region.isnot(None))
                .group_by(model.region)
            )
            for name, count in rows:
                usage.setdefault(name, dict(EMPTY_USAGE))[key] = count
        return usage

    async def _usage_of(self, name: str) -> dict[str, int]:
        """Bitta hudud bo'yicha ishlatilish — o'chirishdan oldin tekshirish."""
        counts = dict(EMPTY_USAGE)
        for key, model in REGION_HOLDERS:
            counts[key] = (
                await self._session.execute(
                    select(func.count()).select_from(model).where(model.region == name)
                )
            ).scalar_one()
        return counts

    async def _assert_name_free(self, name: str, *, exclude: UUID | None = None) -> None:
        """Nom band bo'lsa 409. Unique indeks ham bor, lekin xato xabari
        `IntegrityError` dan ko'ra tushunarli bo'lishi kerak."""
        stmt = select(RegionModel.id).where(func.lower(RegionModel.name) == name.lower())
        if exclude is not None:
            stmt = stmt.where(RegionModel.id != exclude)
        if (await self._session.execute(stmt)).first() is not None:
            raise ConflictError(
                f"«{name}» nomli hudud allaqachon mavjud",
                code="region_exists",
            )

    @staticmethod
    def _clean_name(raw: str) -> str:
        name = normalize_region_name(raw)
        if not name:
            raise ValidationError("Hudud nomi bo'sh bo'lishi mumkin emas")
        if len(name) > REGION_NAME_MAX:
            raise ValidationError(
                f"Hudud nomi {REGION_NAME_MAX} belgidan uzun bo'lmasin"
            )
        return name

    @staticmethod
    def _to_dict(region: RegionModel, usage: dict[str, int]) -> dict[str, Any]:
        return {
            "id": region.id,
            "name": region.name,
            "is_active": region.is_active,
            "sort_order": region.sort_order,
            "note": region.note,
            "usage": usage,
        }

    # ── Ro'yxat ───────────────────────────────────────────────

    async def list_regions(
        self,
        include_inactive: bool = False,
        only_for_agent: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Hududlar + qayerda ishlatilayotgani.

        Ishlatilish soni ro'yxatning bir qismi: admin o'chirish tugmasini
        bosishdan OLDIN oqibatini ko'rishi kerak.

        `only_for_agent` — savdo xodimi uchun ro'yxat SHU xodimning
        hududlari bilan cheklanadi. Sabab: xodim faqat o'z ma'lumotini
        ko'radi, filtrda esa butun kompaniyaning hududlari turardi.
        Ularning ko'pini tanlash bo'sh jadval berardi — filtr «buzuq»
        ko'rinardi. Hududlar `agent_regions.py` dagi YAGONA qoida bo'yicha
        olinadi: faqat faol, hududi to'ldirilgan biriktirilgan guruhlar.
        """
        stmt = select(RegionModel).order_by(RegionModel.sort_order, RegionModel.name)
        if not include_inactive:
            stmt = stmt.where(RegionModel.is_active.is_(True))

        if only_for_agent is not None:
            stmt = stmt.where(RegionModel.name.in_(agent_region_names(only_for_agent)))

        regions = (await self._session.execute(stmt)).scalars().all()
        usage = await self._usage_map()
        return [
            self._to_dict(region, usage.get(region.name, dict(EMPTY_USAGE)))
            for region in regions
        ]

    async def names(self, include_inactive: bool = True) -> list[str]:
        """Faqat nomlar — eski `GET /groups/regions` aliasi uchun."""
        stmt = select(RegionModel.name).order_by(
            RegionModel.sort_order, RegionModel.name
        )
        if not include_inactive:
            stmt = stmt.where(RegionModel.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_one(self, region_id: UUID) -> dict[str, Any]:
        region = await self._get(region_id)
        return self._to_dict(region, await self._usage_of(region.name))

    # ── Qo'shish ──────────────────────────────────────────────

    async def create(
        self,
        name: str,
        sort_order: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        clean = self._clean_name(name)
        await self._assert_name_free(clean)

        if sort_order is None:
            # Ro'yxat oxiriga — mavjud tartib buzilmasin
            last = (
                await self._session.execute(
                    select(func.coalesce(func.max(RegionModel.sort_order), 0))
                )
            ).scalar_one()
            sort_order = last + SORT_ORDER_STEP

        region = RegionModel(
            name=clean,
            is_active=True,
            sort_order=sort_order,
            note=note.strip() or None if note else None,
        )
        self._session.add(region)
        await self._session.flush()

        # Yangi hudud hali hech kimga biriktirilmagan — hisoblash shart emas
        return self._to_dict(region, dict(EMPTY_USAGE))

    # ── Tahrirlash + KASKAD nom o'zgartirish ──────────────────

    async def update(self, region_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
        """Faqat yuborilgan maydonlarni o'zgartiradi.

        ⚠️ Nom o'zgarsa — `agents.region`, `clients.region`,
        `telegram_groups.region` dagi eski nom SHU YERDA yangisiga
        almashtiriladi. Hammasi bitta sessiya (= bitta tranzaksiya) ichida:
        so'rov o'rtasida uzilsa hech narsa yozilmaydi, hudud yarim
        o'zgargan holatda qolmaydi.
        """
        region = await self._get(region_id)
        renamed = dict(EMPTY_USAGE)

        if "name" in fields:
            clean = self._clean_name(str(fields["name"]))
            if clean != region.name:
                await self._assert_name_free(clean, exclude=region.id)
                renamed = await self._cascade_rename(region.name, clean)
                region.name = clean

        was_active = region.is_active

        for key in ("is_active", "sort_order"):
            if key in fields and fields[key] is not None:
                setattr(region, key, fields[key])

        if "note" in fields:
            note = fields["note"]
            region.note = note.strip() or None if note else None

        # Arxivlashda guruhlarni uzish. Standart — UZISH; guruhlar eski
        # hududda qolishi kerak bo'lsa chaqiruvchi `detach_groups=False`
        # yuboradi. Maydon umuman berilmasa ham uziladi: qoida serverda
        # turishi kerak, aks holda eski klient jimgina boshqacha
        # natija berardi.
        detached = 0
        if (
            was_active
            and not region.is_active
            and fields.get("detach_groups", True)
        ):
            detached = await self._detach_active_groups(region.name)

        await self._session.flush()

        return {
            **self._to_dict(region, await self._usage_of(region.name)),
            "renamed": renamed,
            "detached_groups": detached,
        }

    async def active_group_count(self, name: str) -> int:
        """Shu hududdagi FAOL guruhlar soni — arxivlashdan oldin ogohlantirish.

        Admin tugmani bosishdan oldin nima to'xtashini bilishi kerak.
        """
        return (
            await self._session.execute(
                select(func.count())
                .select_from(TelegramGroupModel)
                .where(
                    TelegramGroupModel.region == name,
                    TelegramGroupModel.is_active.is_(True),
                )
            )
        ).scalar_one()

    async def _detach_active_groups(self, name: str) -> int:
        """Arxivlanayotgan hududni FAOL guruhlardan uzadi.

        ⚠️ NEGA BU XAVFSIZ (va ilgari xavfsiz emas edi).
        Hisobot hududni ilgari tirik `telegram_groups.region` dan
        o'qirdi, shuning uchun uzish o'tgan oylarning bahosini
        hisobotdan o'chirib yuborardi. Endi har so'rovnoma o'z hudud
        NUSXASINI saqlaydi (`surveys.region`), demak uzish faqat
        KELAJAKKA ta'sir qiladi: tarix joyida qoladi.

        ⚠️ NIMA O'ZGARADI. Hududsiz guruh so'rovnoma OLMAYDI
        (`_structural_block`) va daraxtdagi «Hududsiz» tugunida
        ko'rinadi. Ya'ni bu — «bu hududga endi xizmat ko'rsatmaymiz»
        degan qaror, va u ko'rinadigan holatda qoladi, jimgina emas.

        ⚠️ NEGA FAQAT GURUHLAR. `agents.region` — xodim YASHAYDIGAN
        joy, xizmat topshirig'i emas (u `NOT NULL` ham). Xodimning
        hududlari esa guruhlaridan hisoblanadi, shuning uchun guruh
        uzilishi bilan xodim ham bu hududdan barcha ekranlarda
        avtomatik chiqib ketadi.

        Faolsiz guruhlarga tegilmaydi: ular allaqachon ishlamayapti va
        ularning hududini o'chirish tarixdagi izni yo'qotardi.
        """
        result = await self._session.execute(
            update(TelegramGroupModel)
            .where(
                TelegramGroupModel.region == name,
                TelegramGroupModel.is_active.is_(True),
            )
            .values(region=None, bound_at=None)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    async def _cascade_rename(self, old_name: str, new_name: str) -> dict[str, int]:
        """Uchala jadvaldagi eski nomni yangisiga almashtiradi.

        Qaytaradi: jadval → nechta qator yangilangani. Bu son javobga
        chiqadi — admin «nima o'zgardi» degan savolga darhol javob olsin,
        keyin hisobotdan qidirib yurmasin.
        """
        counts = dict(EMPTY_USAGE)
        for key, model in REGION_HOLDERS:
            result = await self._session.execute(
                update(model)
                .where(model.region == old_name)
                .values(region=new_name)
                .execution_options(synchronize_session=False)
            )
            counts[key] = result.rowcount or 0
        return counts

    # ── O'chirish ─────────────────────────────────────────────

    async def delete(self, region_id: UUID) -> None:
        """Hududni o'chiradi — faqat hech qayerda ishlatilmasa.

        Ishlatilayotganini o'chirish `agents.region` ni ro'yxatdan tashqarida
        qoldiradi (FK yo'q, baza to'xtatmaydi), keyin xodim formasi qiymatni
        yo'qotadi. Shuning uchun 409 va faolsizlantirish taklifi.
        """
        region = await self._get(region_id)
        usage = await self._usage_of(region.name)

        if any(usage.values()):
            raise ConflictError(
                f"Bu hudud {usage_phrase_uz(**usage)}da ishlatilmoqda. "
                "O'chirish o'rniga faolsizlantiring.",
                code="region_in_use",
            )

        await self._session.delete(region)
        await self._session.flush()
