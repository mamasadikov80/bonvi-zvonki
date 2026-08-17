"""Sinxronizatsiya nimani oladi va nimani olmaydi.

Bu modulning asosiy va'dasi ikkita:

  1. AUDIOSI BOR qo'ng'iroq olinadi, qolgani BAZAGA UMUMAN TUSHMAYDI.
     Ilgari javobsiz qo'ng'iroqlar ham `status='skipped'` bilan
     saqlanardi va ro'yxatning katta qismini 0:00 li, bahosiz, mijozsiz
     qatorlar egallab olardi.
  2. Bir marta olingan yozuv havolasi qayta sinxronlashda YO'QOLMAYDI.
     MoyZvonki yozuvni cheklangan muddat saqlaydi; muddat o'tgach `recording`
     bo'shaydi. Havola to'g'ridan-to'g'ri yozilsa, eski davrni qayta
     tortish allaqachon baholangan qo'ng'iroqni tinglab bo'lmaydigan
     holga keltirardi.

⚠️ TARMOQQA CHIQMAYDI. `MoizvonkiClient` o'rniga soxta obyekt qo'yilgan:
MoyZvonki'ga bitta ham so'rov ketmaydi.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.moizvonki.application.ingest import IngestService
from src.modules.moizvonki.domain.entities import CallPage, MoizvonkiCall

BOSHLANISH = datetime(2026, 8, 1, tzinfo=UTC)


class SoxtaKlient:
    """`iter_calls` ni taqlid qiladi — boshqa hech narsa kerak emas."""

    def __init__(self, *pages: tuple[MoizvonkiCall, ...]) -> None:
        self._pages = pages

    async def iter_calls(self, **_: object) -> AsyncIterator[tuple[int, CallPage]]:
        for number, calls in enumerate(self._pages, start=1):
            yield number, CallPage(
                calls=calls, next_offset=0, remains=0, total_in_page=len(calls)
            )


def _call(marker: str, **payload: object) -> MoizvonkiCall:
    return MoizvonkiCall.from_api(
        {
            "db_call_id": marker,
            "start_time": int(BOSHLANISH.timestamp()),
            "duration": 180,
            "user_id": "mz-1",
            **payload,
        }
    )


@pytest_asyncio.fixture
async def xodim() -> AsyncIterator[uuid.UUID]:
    """MoyZvonki `user_id` ga bog'langan xodim. Test oxirida o'chadi."""
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"ingest-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            external_id="mz-1",
            is_active=True,
        )
        session.add(agent)
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with SessionFactory() as session:
        # Qo'ng'iroqlar kaskad bilan ketadi
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()


async def _run(client: SoxtaKlient) -> object:
    async with SessionFactory() as session:
        return await IngestService(session, client).run(  # type: ignore[arg-type]
            since=BOSHLANISH - timedelta(days=1),
            until=BOSHLANISH + timedelta(days=1),
        )


async def _rows(agent_id: uuid.UUID) -> list[CallModel]:
    async with SessionFactory() as session:
        result = await session.execute(
            select(CallModel)
            .where(CallModel.agent_id == agent_id)
            .order_by(CallModel.external_id)
        )
        return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════
#  Audio filtri
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_audiosiz_qongiroq_bazaga_tushmaydi(xodim) -> None:
    """Uch qo'ng'iroqdan faqat bittasida audio bor — bittasi saqlanadi."""
    token = uuid.uuid4().hex[:8]
    report = await _run(
        SoxtaKlient(
            (
                _call(f"{token}-a", recording="records/a.mp3"),
                # Javobsiz: hujjatda bo'sh satr keladi deyilgan
                _call(f"{token}-b", recording="", answered=0),
                # Ba'zi o'rnatmalarda joy egallovchi qiymat keladi
                _call(f"{token}-c", recording="0"),
            ),
        )
    )

    assert report.fetched == 3
    assert report.created == 1
    assert report.skipped_no_recording == 2
    # «Audiosi yo'q» — «xodimi topilmadi» EMAS: hisobotda ikkalasi
    # aralashib ketsa, admin haqiqiy muammoni shovqin ichida qidiradi
    assert report.skipped_no_agent == 0
    assert report.unmatched == []

    rows = await _rows(xodim)
    assert [row.external_id for row in rows] == [f"{token}-a"]
    assert rows[0].status is CallStatus.PENDING
    assert rows[0].audio_key == "records/a.mp3"


@pytest.mark.asyncio
async def test_audiosiz_qongiroq_xodimsiz_deb_belgilanmaydi(xodim) -> None:
    """Bizda xodimi yo'q, audiosi ham yo'q — «audiosiz» deb sanaladi.

    Tartib muhim: agar xodim tekshiruvi oldinda tursa, har bir javobsiz
    qo'ng'iroq «xodimga bog'lanmadi» ro'yxatiga tushib, admin yo'q
    muammoni tuzatishga urinardi.
    """
    report = await _run(
        SoxtaKlient((_call(uuid.uuid4().hex[:8], user_id="notanish", recording=""),))
    )

    assert report.skipped_no_recording == 1
    assert report.skipped_no_agent == 0
    assert report.created == 0


# ══════════════════════════════════════════════════════════════
#  Mijoz nomi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mijoz_nomi_va_raqami_saqlanadi(xodim) -> None:
    """Katalogimizda bunday mijoz yo'q, lekin ustun bo'sh qolmaydi."""
    token = uuid.uuid4().hex[:8]
    await _run(
        SoxtaKlient(
            (
                _call(
                    f"{token}-a",
                    recording="records/a.mp3",
                    client_name="Anvar aka",
                    client_number="+998901234567",
                ),
            ),
        )
    )

    (row,) = await _rows(xodim)
    assert row.client_name == "Anvar aka"
    assert row.client_phone == "+998901234567"
    # Katalogda mos raqam yo'q — bog'lanish qilinmaydi, taxmin ham
    assert row.client_id is None


# ══════════════════════════════════════════════════════════════
#  Qayta sinxronlash
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_muddati_otgan_yozuv_havolasini_ochirmaydi(xodim) -> None:
    """Muddat o'tib `recording` bo'shasa, olingan havola JOYIDA qoladi.

    Eski davrni qayta tortish odatiy ish (masalan yangi xodim
    biriktirilgach). Agar bo'sh `recording` mavjud qatorga yozilsa,
    allaqachon baholangan qo'ng'iroqni tinglab bo'lmay qolardi.
    """
    token = uuid.uuid4().hex[:8]
    await _run(
        SoxtaKlient((_call(f"{token}-a", recording="records/a.mp3"),))
    )

    report = await _run(SoxtaKlient((_call(f"{token}-a", recording=""),)))

    # Qator YANGILANMAYDI ham — u filtrga tushmay o'tib ketadi
    assert report.created == 0
    assert report.updated == 0
    assert report.skipped_no_recording == 1

    (row,) = await _rows(xodim)
    assert row.audio_key == "records/a.mp3"


@pytest.mark.asyncio
async def test_qayta_yurish_mijoz_nomini_ochirmaydi(xodim) -> None:
    """MoyZvonki bu safar nomni bermasa — o'tgan safargisi qoladi."""
    token = uuid.uuid4().hex[:8]
    await _run(
        SoxtaKlient(
            (
                _call(
                    f"{token}-a",
                    recording="records/a.mp3",
                    client_name="Anvar aka",
                    client_number="+998901234567",
                ),
            ),
        )
    )

    report = await _run(
        SoxtaKlient((_call(f"{token}-a", recording="records/a.mp3"),))
    )

    assert report.created == 0
    assert report.updated == 1

    (row,) = await _rows(xodim)
    assert row.client_name == "Anvar aka"
    assert row.client_phone == "+998901234567"
