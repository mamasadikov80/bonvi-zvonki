"""MoyZvonki → `calls` jadvali.

Nima saqlanadi: qo'ng'iroq metadatasi va MoyZvonki'dagi yozuv
identifikatori (`calls.audio_key`). **Audio saqlanmaydi** — bu servis
audio baytlariga umuman tegmaydi, `recording` maydonini matn sifatida
ko'chiradi xolos.

FILTR: faqat AUDIOSI BOR qo'ng'iroqlar ko'chiriladi. Javobsiz
qo'ng'iroq, muddati o'tgan yozuv va xizmat qo'ng'iroqlari bazaga
umuman tushmaydi — ular baholanmaydi, ya'ni ro'yxatda faqat shovqin
bo'lardi. Nechtasi shu sababdan tashlanganini hisobot aytadi
(`skipped_no_recording`).

Idempotentlik: `calls.external_id` — MoyZvonki'dagi `db_call_id`.
Ustunda UNIQUE indeks bor, shuning uchun qayta yurish `ON CONFLICT DO
UPDATE` ga tushadi va nusxa qator paydo bo'lmaydi. Qayta ishlash
natijalari (`status`, `transcript`) YANGILANMAYDI — sinxronizatsiya
transkriptni o'chirib yuborishi mumkin emas.

🔒 MoyZvonki tomoniga HECH NARSA yozilmaydi. Bu yerdagi barcha
o'zgarishlar BIZNING bazamizda: MoyZvonki'dan faqat `calls.list`
o'qiladi (`MoizvonkiClient.READ_ONLY_ACTIONS`).
"""

import re
from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.clients.infrastructure.models import ClientModel
from src.modules.moizvonki.domain.entities import IngestReport, MoizvonkiCall
from src.modules.moizvonki.infrastructure.client import MoizvonkiClient

# Telefon raqamlarini solishtirish uchun — mamlakat kodi va formatlash
# har xil bo'lishi mumkin, oxirgi 9 raqam O'zbekistonda yagona
_PHONE_TAIL = 9
_NON_DIGIT = re.compile(r"\D+")


def _phone_key(value: str | None) -> str | None:
    digits = _NON_DIGIT.sub("", value or "")
    if len(digits) < _PHONE_TAIL:
        return None
    return digits[-_PHONE_TAIL:]


@dataclass(slots=True)
class _Directory:
    """Mos keltirish uchun keshlangan jadvallar."""

    agent_by_external: dict[str, object]
    client_by_phone: dict[str, object]

    def agent_for(self, call: MoizvonkiCall) -> object | None:
        """MoyZvonki xodimini bizning `agents.external_id` ga bog'laydi.

        Admin `external_id` ga MoyZvonki'dagi `user_id` (raqam) yoki
        `user_account` (email) dan istalganini yozishi mumkin —
        ikkalasi ham qidiriladi, chunki hujjatda ikkalasi ham qaytadi.
        """
        for candidate in (call.user_id, call.user_account):
            if not candidate:
                continue
            agent = self.agent_by_external.get(candidate.strip().lower())
            if agent is not None:
                return agent
        return None


class IngestService:
    """Qo'ng'iroqlarni sana oralig'i bo'yicha tortib oladi."""

    def __init__(self, session: AsyncSession, client: MoizvonkiClient) -> None:
        self._session = session
        self._client = client

    async def _directory(self) -> _Directory:
        agents = (
            await self._session.execute(
                select(AgentModel.id, AgentModel.external_id).where(
                    AgentModel.external_id.is_not(None)
                )
            )
        ).all()

        clients = (
            await self._session.execute(
                select(ClientModel.id, ClientModel.phone).where(
                    ClientModel.phone.is_not(None)
                )
            )
        ).all()

        by_phone: dict[str, object] = {}
        for client_id, phone in clients:
            key = _phone_key(phone)
            if key is None:
                continue
            # Bir raqam ikki mijozda bo'lsa — taxmin qilmaymiz, tashlab
            # ketamiz. Noto'g'ri mijozga bog'lash bo'shdan yomonroq.
            by_phone[key] = None if key in by_phone else client_id

        return _Directory(
            agent_by_external={
                str(ext).strip().lower(): agent_id for agent_id, ext in agents
            },
            client_by_phone={k: v for k, v in by_phone.items() if v is not None},
        )

    async def run(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        supervised: bool = True,
        max_calls: int = 20_000,
        page_size: int = 100,
        agent_ids: Iterable[UUID] | None = None,
    ) -> IngestReport:
        """Sana oralig'idagi qo'ng'iroqlarni ko'chiradi.

        Saqlanish sharti uchta: audiosi bor + xodimi topilgan + admin
        tanlagan ro'yxatda. Uchalasi ham hisobotda alohida sanaladi.

        `agent_ids` — FAQAT shu xodimlarning qo'ng'iroqlari saqlanadi.
        Berilmasa — `external_id` si bor barcha xodimlarniki.

        ⚠️ Filtrlash BIZNING tomonda bajariladi: MoyZvonki'ning
        `calls.list` metodida xodim bo'yicha parametr yo'q, faqat sana
        oralig'i bor. Ya'ni sahifalar baribir to'liq o'qiladi, lekin
        keraksizlari bazaga yozilmaydi. MoyZvonki'ga qo'shimcha yoki
        boshqacha so'rov YUBORILMAYDI.
        """
        report = IngestReport(since=since, until=until)
        directory = await self._directory()
        wanted = set(agent_ids) if agent_ids is not None else None

        async for page_number, page in self._client.iter_calls(
            since=since, until=until, supervised=supervised, page_size=page_size
        ):
            report.pages = page_number
            report.fetched += len(page.calls)

            rows: dict[str, dict[str, object]] = {}
            for call in page.calls:
                # ── Audio bor-yo'qligi BIRINCHI tekshiriladi ──────
                #
                # Bu ro'yxatning asosiy filtri: baholash audiodan
                # boshlanadi, audiosi yo'q qo'ng'iroq esa hech qachon
                # baholanmaydi. Uni saqlash ro'yxatni 0:00 li, bahosiz
                # qatorlar bilan to'ldiradi xolos.
                #
                # Tartib ham ataylab shunday: agar xodim tekshiruvi
                # oldinda tursa, javobsiz qo'ng'iroqlar «xodimga
                # bog'lanmadi» ro'yxatiga tushib, admin haqiqiy
                # muammoni shovqin ichida qidirardi.
                if not call.has_recording:
                    report.skipped_no_recording += 1
                    continue

                agent_id = directory.agent_for(call)
                if agent_id is None:
                    # JIMGINA tashlab ketilmaydi — hisobotga tushadi
                    report.skipped_no_agent += 1
                    report.note_unmatched(call)
                    continue

                # Admin aniq xodimlarni tanlagan bo'lsa — qolganlari
                # o'tkazib yuboriladi. Bu «xodimi topilmadi» EMAS,
                # shuning uchun `skipped_no_agent` ga qo'shilmaydi:
                # hisobotda ikkalasi aralashib ketmasin.
                if wanted is not None and agent_id not in wanted:
                    report.skipped_not_selected += 1
                    continue

                # Bir sahifada bir `db_call_id` ikki marta kelsa,
                # PostgreSQL «ON CONFLICT ... bir qatorni ikki marta
                # o'zgartira olmaydi» deb xato beradi — oldini olamiz
                rows[call.db_call_id] = self._row(call, agent_id, directory)

            if rows:
                created, updated = await self._upsert(list(rows.values()))
                report.created += created
                report.updated += updated

            if report.fetched >= max_calls:
                report.truncated = True
                break

        await self._session.commit()
        return report

    @staticmethod
    def _row(
        call: MoizvonkiCall, agent_id: object, directory: _Directory
    ) -> dict[str, object]:
        return {
            "id": uuid4(),
            "external_id": call.db_call_id,
            "agent_id": agent_id,
            "client_id": directory.client_by_phone.get(
                _phone_key(call.client_number) or ""
            ),
            # MoyZvonki'dagi mijoz — katalogimizga bog'lanmagan bo'lsa
            # ham ismi ko'rinsin. `client_id` topilishi kamdan-kam:
            # u faqat raqam bizning `clients` da bo'lganda to'ladi.
            "client_name": call.client_name,
            "client_phone": call.client_number,
            "direction": (
                CallDirection.OUTBOUND if call.is_outbound else CallDirection.INBOUND
            ),
            # Yangi qator uchun boshlang'ich holat. Bu yergacha faqat
            # yozuvi BOR qo'ng'iroq yetib keladi, shuning uchun har doim
            # `PENDING`. Mavjud qatorda `status` TEGILMAYDI (pastdagi
            # `set_` ga kirmagan).
            "status": CallStatus.PENDING,
            "started_at": call.start_time,
            "duration_sec": call.duration_sec,
            # ⚠️ Faqat MANZIL saqlanadi, audio emas.
            "audio_key": call.recording,
        }

    async def _upsert(self, rows: list[dict[str, object]]) -> tuple[int, int]:
        stmt = pg_insert(CallModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CallModel.external_id],
            set_={
                "agent_id": stmt.excluded.agent_id,
                "client_id": func.coalesce(
                    stmt.excluded.client_id, CallModel.client_id
                ),
                # `coalesce` — MoyZvonki bu safar nomni bermasa,
                # o'tgan safar olingani o'chib ketmasin
                "client_name": func.coalesce(
                    stmt.excluded.client_name, CallModel.client_name
                ),
                "client_phone": func.coalesce(
                    stmt.excluded.client_phone, CallModel.client_phone
                ),
                "direction": stmt.excluded.direction,
                "started_at": stmt.excluded.started_at,
                "duration_sec": stmt.excluded.duration_sec,
                # Muddati o'tgan yozuv havolasini saqlab qolishning
                # ASOSIY kafolati — yuqoridagi filtr: `recording` si
                # bo'sh qo'ng'iroq bu yergacha yetib kelmaydi, ya'ni
                # mavjud qator umuman qo'zg'atilmaydi. `coalesce` esa
                # ikkinchi qator himoya: filtr kelajakda o'zgarsa ham
                # allaqachon olingan havola o'chib ketmaydi.
                "audio_key": func.coalesce(
                    stmt.excluded.audio_key, CallModel.audio_key
                ),
                "updated_at": func.now(),
                # `status` va `transcript` ATAYLAB yo'q:
                # sinxronizatsiya baholash natijasini yo'q qilmasin.
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))

        result = await self._session.execute(stmt)
        flags = [bool(row[0]) for row in result.all()]
        created = sum(flags)
        return created, len(flags) - created
