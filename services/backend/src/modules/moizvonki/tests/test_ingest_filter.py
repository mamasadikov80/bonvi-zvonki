"""Sinxronizatsiya nimani oladi va nimani olmaydi.

Bu modulning asosiy va'dasi ikkita:

  1. BARCHA qo'ng'iroq saqlanadi — javobsizlari ham. Ular faollik
     hisoboti uchun kerak (javobsizlar soni, qaytib aloqaga chiqish).
     Audiosizlari `status = SKIPPED` bilan yoziladi va baholanmaydi.
     ⚠️ Ilgari ular BUTUNLAY tashlanardi. O'lchov shuni ko'rsatdi:
     javobsiz qo'ng'iroqda yozuv hech qachon bo'lmaydi (2030 dan 0
     tasida), ya'ni eski filtr javobsizlarni yo'q qilardi — 7 kunda
     2030 qo'ng'iroq, jamining 35% i.
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
async def test_audiosiz_qongiroq_ham_saqlanadi(xodim) -> None:
    """⚠️ ASOSIY KAFOLAT: audiosiz qo'ng'iroq YO'QOLMAYDI.

    Faollik hisoboti aynan shu qatorlarga tayanadi: javobsizlar soni,
    qaytib aloqaga chiqish darajasi. Ular tashlansa bu savollarga javob
    berish IMKONSIZ bo'lardi — MoyZvonki'da qayta so'rash ham yordam
    bermaydi, chunki hisobot bazadan hisoblanadi.
    """
    token = uuid.uuid4().hex[:8]
    report = await _run(
        SoxtaKlient(
            (
                _call(f"{token}-a", recording="records/a.mp3"),
                # Javobsiz: hujjatda bo'sh satr keladi deyilgan
                _call(f"{token}-b", recording="", answered=0),
                # Javob BERILGAN, lekin yozuv yo'q — o'lchandi: 3847
                # javobli qo'ng'iroqning 260 tasida yozuv bo'lmagan
                _call(f"{token}-c", recording="0", answered=1),
            ),
        )
    )

    assert report.fetched == 3
    assert report.created == 3, "uchalasi ham saqlanishi kerak"
    # Bu son «tashlandi» EMAS: nechtasi baholanmasligini bildiradi
    assert report.skipped_no_recording == 2
    # «Audiosi yo'q» — «xodimi topilmadi» EMAS: hisobotda ikkalasi
    # aralashib ketsa, admin haqiqiy muammoni shovqin ichida qidiradi
    assert report.skipped_no_agent == 0
    assert report.unmatched == []

    rows = {row.external_id: row for row in await _rows(xodim)}
    assert set(rows) == {f"{token}-a", f"{token}-b", f"{token}-c"}

    # Audiosi bor — navbatda
    assert rows[f"{token}-a"].status is CallStatus.PENDING
    assert rows[f"{token}-a"].audio_key == "records/a.mp3"

    # Audiosi yo'q — DARHOL `SKIPPED`. `PENDING` bo'lib turishi yolg'on
    # bo'lardi: interfeysda «navbatda kutmoqda» degan ma'no beradi va
    # admin nega baholanmayotganini kutib o'tirardi.
    for suffix in ("b", "c"):
        row = rows[f"{token}-{suffix}"]
        assert row.status is CallStatus.SKIPPED
        assert row.audio_key is None

    # Javobsizlik ALOHIDA maydonda — `status` dan mustaqil
    assert rows[f"{token}-b"].answered is False
    assert rows[f"{token}-c"].answered is True, (
        "audiosi yo'q, lekin javob berilgan — bu ikki xil narsa"
    )


@pytest.mark.asyncio
async def test_xodimi_topilmagan_qongiroq_saqlanmaydi(xodim) -> None:
    """Xodimi yo'q qo'ng'iroq saqlanmaydi — `agent_id` MAJBURIY.

    Audiosizlik va xodimsizlik ikki BOSHQA narsa va hisobotda ham
    alohida sanaladi: aralashib ketsa admin haqiqiy muammoni (xodim
    identifikatori to'ldirilmagani) shovqin ichida ko'rmay qolardi.
    """
    report = await _run(
        SoxtaKlient((_call(uuid.uuid4().hex[:8], user_id="notanish", recording=""),))
    )

    # ⚠️ Audio soniga TUSHMAYDI. `skipped_no_recording` «saqlandi,
    # lekin baholanmaydi» degani — bu qator esa umuman saqlanmadi.
    # Ikkalasiga qo'shish hisobot kataklarini `fetched` ga
    # yig'ilmaydigan qilardi.
    assert report.skipped_no_recording == 0
    # Saqlanmasligining sababi — xodim, audio emas
    assert report.skipped_no_agent == 1
    assert report.created == 0
    assert report.unmatched, "admin kimning identifikatorini to'ldirishni bilishi kerak"


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

    # Endi qator YANGILANADI (audiosizlar ham saqlanadi), lekin
    # havola O'CHMAYDI — buni `coalesce` ushlab turadi
    assert report.created == 0
    assert report.updated == 1
    assert report.skipped_no_recording == 1

    (row,) = await _rows(xodim)
    assert row.audio_key == "records/a.mp3", (
        "muddati o'tgan yozuv havolasi o'chib ketmasligi kerak — aks holda "
        "allaqachon baholangan qo'ng'iroqni tinglab bo'lmaydi"
    )
    # Holat ham qo'zg'atilmaydi: baholangan qo'ng'iroq `SKIPPED` ga
    # aylanib qolmasligi kerak
    assert row.status is CallStatus.PENDING


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


@pytest.mark.asyncio
async def test_answered_maydoni_kelmasa_NOMALUM_qoladi(xodim) -> None:
    """⚠️ Maydon kelmasa `False` EMAS, `NULL` yoziladi.

    Bu son shefga ko'rsatiladi: «nechta qo'ng'iroq javobsiz qoldi».
    Maydon kelmaganda «javobsiz» deb qabul qilish o'sha sonni oshirib
    yuboradi — ya'ni xato aynan eng yomon tomonga: kompaniya javob
    bergan qo'ng'iroqlar «o'tkazib yuborilgan» bo'lib chiqadi va
    xodimlar nohaq ayblanadi. Noto'g'ri raqamdan ko'ra kamroq raqam
    yaxshiroq."""
    token = uuid.uuid4().hex[:8]
    # `answered` UMUMAN berilmagan
    await _run(SoxtaKlient((_call(f"{token}-a", recording="records/a.mp3"),)))

    (row,) = await _rows(xodim)
    assert row.answered is None


@pytest.mark.asyncio
async def test_javobsiz_qongiroq_belgisi_saqlanadi(xodim) -> None:
    """Javobsizlik — TELEFONIYA fakti, ishlov holati emas.

    Ikkisi alohida maydonda turishi kerak: `status = SKIPPED`
    «baholanmadi» degani, `answered = false` esa «gaplashilmagan».
    Bittasi bilan ikkinchisini ifodalash mumkin emas — javob berilgan
    qo'ng'iroqning ham 7% ida yozuv bo'lmaydi."""
    token = uuid.uuid4().hex[:8]
    await _run(
        SoxtaKlient(
            (
                _call(f"{token}-a", recording="", answered=0, duration=0),
                _call(f"{token}-b", recording="records/b.mp3", answered=1),
            )
        )
    )

    rows = {r.external_id: r for r in await _rows(xodim)}
    assert rows[f"{token}-a"].answered is False
    assert rows[f"{token}-a"].duration_sec == 0
    assert rows[f"{token}-b"].answered is True


@pytest.mark.asyncio
async def test_qayta_sinxronizatsiya_answered_ni_OCHIRMAYDI(xodim) -> None:
    """⚠️ Bilingan javob holati `NULL` bilan bosib ketilmasligi kerak.

    MoyZvonki `answered` maydonini ba'zi davrlarda umuman bermaydi —
    bu haqiqiy ma'lumotda tasdiqlangan. `coalesce` bo'lmasa o'sha
    davrni qayta sinxronlash bilingan `false` ni `NULL` ga aylantirardi,
    hisobot esa `NULL` ni sanamaydi: javobsizlar soni JIMGINA kamayardi.

    Xato «yaxshi tomonga» qarab bo'lgani uchun uni hech kim sezmasdi —
    ko'rsatkich yaxshilangandek ko'rinardi."""
    token = uuid.uuid4().hex[:8]
    # Birinchi yurish: javobsiz ekani ANIQ
    await _run(
        SoxtaKlient((_call(f"{token}-a", recording="", answered=0, duration=0),))
    )
    (row,) = await _rows(xodim)
    assert row.answered is False

    # Ikkinchi yurish: MoyZvonki maydonni BERMADI
    await _run(SoxtaKlient((_call(f"{token}-a", recording=""),)))

    (row,) = await _rows(xodim)
    assert row.answered is False, (
        "bilingan qiymat saqlanishi kerak — `NULL` uni bosib ketmasin"
    )


@pytest.mark.asyncio
async def test_nomalum_qiymat_keyin_TOLDIRILADI(xodim) -> None:
    """Teskari yo'nalish ochiq qolishi kerak: `NULL` qator qayta
    sinxronlashda haqiqiy qiymat bilan to'ldirilsin."""
    token = uuid.uuid4().hex[:8]
    await _run(SoxtaKlient((_call(f"{token}-a", recording="records/a.mp3"),)))
    (row,) = await _rows(xodim)
    assert row.answered is None

    await _run(
        SoxtaKlient((_call(f"{token}-a", recording="records/a.mp3", answered=1),))
    )
    (row,) = await _rows(xodim)
    assert row.answered is True


@pytest.mark.asyncio
async def test_hisobot_sonlari_IKKI_MARTA_sanamaydi(xodim) -> None:
    """⚠️ Audiosi ham, xodimi ham yo'q qo'ng'iroq BITTA songa tushadi.

    Ilgari audio hisobi xodim tekshiruvidan OLDIN turardi va bunday
    qator ikkala songa birdan qo'shilardi — hisobotdagi kataklar
    `fetched` ga yig'ilmay qolardi va admin sonlar nega mos
    kelmayotganini tushunmasdi."""
    report = await _run(
        SoxtaKlient(
            (
                # Xodimi yo'q + audiosi yo'q
                _call(uuid.uuid4().hex[:8], user_id="notanish", recording=""),
                # Xodimi bor + audiosi yo'q
                _call(uuid.uuid4().hex[:8], recording="", answered=0),
                # Xodimi bor + audiosi bor
                _call(uuid.uuid4().hex[:8], recording="records/a.mp3"),
            )
        )
    )

    assert report.fetched == 3
    assert report.skipped_no_agent == 1
    assert report.skipped_no_recording == 1, (
        "faqat SAQLANGAN, lekin baholanmaydigan qator sanalishi kerak"
    )
    assert report.created == 2
    # Kataklar `fetched` ga yig'iladi
    assert report.created + report.skipped_no_agent == report.fetched - 0
