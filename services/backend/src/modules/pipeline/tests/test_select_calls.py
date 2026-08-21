"""«Baholanmaganlar» tanlovi — natijasi ma'lum bo'lganlarni QAYTA OLMAYDI.

NEGA BU TEST BOR. Savdo bo'lmagan qo'ng'iroqda baho qatori ATAYLAB
yozilmaydi. Shuning uchun «bahosi bo'lmaganlar» degan yagona shart
ularni HAR SAFAR qaytadan tanlaydi — o'lchandi: 114 ta tanlanganning
63 tasi shunday edi.

Zarari pul emas (tur idempotent, LLM qayta chaqirilmaydi), balki
ishonch: admin «Baholanmaganlarni baholash» ni bosadi, progress 114 ta
deb sanaydi, tugagach son yana 114 bo'lib turadi. Buni nosozlik deb
o'qish to'g'ri bo'lardi — shuning uchun shart ikkita.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.orchestrator import select_calls

#: Testda yaratilgan qo'ng'iroqlar oynasi — mavjud ma'lumotga tegmasin
BOSHLANISH = datetime(2019, 6, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def turli_turdagi_qongiroqlar():
    """Har tur uchun bittadan bahosiz qo'ng'iroq."""
    # Oxirgisi — ATAYLAB buzuq qiymat (ustun `varchar`, cheklanmagan)
    turlar = [None, "sales", "internal", "service", "personal", "unclear", "xato"]
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"tanlov-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(agent)
        await session.flush()

        ids: dict[str, uuid.UUID] = {}
        for index, tur in enumerate(turlar):
            call = CallModel(
                external_id=f"tanlov-{uuid.uuid4().hex}",
                agent_id=agent.id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.COMPLETED if tur else CallStatus.PENDING,
                started_at=BOSHLANISH + timedelta(minutes=index),
                duration_sec=300,
                audio_key=f"records/tanlov-{index}.mp3",
                call_type=tur,
            )
            session.add(call)
            await session.flush()
            ids[tur or "none"] = call.id
        await session.commit()
        agent_id = agent.id

    yield ids

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()


async def _tanlangan(**kwargs) -> set[uuid.UUID]:
    async with SessionFactory() as session:
        return set(
            await select_calls(
                session,
                date_from=BOSHLANISH - timedelta(days=1),
                date_to=BOSHLANISH + timedelta(days=1),
                min_duration_sec=10,
                **kwargs,
            )
        )


@pytest.mark.asyncio
async def test_savdo_va_aniqlanmaganlar_tanlanadi(turli_turdagi_qongiroqlar) -> None:
    """Ishlanishi KERAK bo'lganlar: turi yo'q va savdo."""
    tanlangan = await _tanlangan()
    assert turli_turdagi_qongiroqlar["none"] in tanlangan, "turi yo'q — aniqlash kerak"
    assert turli_turdagi_qongiroqlar["sales"] in tanlangan, "savdo, bahosi yo'q"


@pytest.mark.asyncio
async def test_ichki_suhbat_qayta_tanlanmaydi(turli_turdagi_qongiroqlar) -> None:
    """⚠️ ASOSIY KAFOLAT: ichki suhbatda baho qatori HECH QACHON paydo
    bo'lmaydi, demak «bahosi yo'q» sharti uni abadiy tanlaganda edi."""
    tanlangan = await _tanlangan()
    assert turli_turdagi_qongiroqlar["internal"] not in tanlangan


@pytest.mark.asyncio
@pytest.mark.parametrize("tur", ["service", "personal", "unclear"])
async def test_eski_turlar_qaytadan_aniqlanadi(
    turli_turdagi_qongiroqlar, tur
) -> None:
    """Eski AI tasnifidan qolgan qiymatlar QAYTA ISHLANADI.

    ⚠️ Bu ataylab shunday. «Xizmat» yoki «shaxsiy» deb belgilangan
    qo'ng'iroq endi katta ehtimol bilan SAVDO: o'sha tasnif transkript
    mazmuniga qarab qo'yilgan va yanglishgan. Ularni «aniqlangan» deb
    qoldirish — xatoni abadiylashtirish bo'lardi."""
    tanlangan = await _tanlangan()
    assert turli_turdagi_qongiroqlar[tur] in tanlangan


@pytest.mark.asyncio
async def test_force_bilan_hammasi_tanlanadi(turli_turdagi_qongiroqlar) -> None:
    """Qayta ko'rish yo'li YO'QOLMASLIGI kerak.

    Tur xato aniqlangan bo'lishi mumkin — qo'lda tuzatish yo'q, shuning
    uchun yagona yo'l `only_unscored=False` (router `force` da shuni
    yuboradi). U to'silsa xato tur abadiy qolib ketardi."""
    tanlangan = await _tanlangan(only_unscored=False)
    assert set(turli_turdagi_qongiroqlar.values()) <= tanlangan


@pytest.mark.asyncio
async def test_buzuq_qiymat_tanlanadi_tizim_ozini_tuzatadi(
    turli_turdagi_qongiroqlar,
) -> None:
    """⚠️ Notanish tur navbatdan TUSHIB QOLMASLIGI kerak.

    Shart «savdo yoki bo'sh» deb yozilsa, buzuq qiymat ikkalasiga ham
    tushmaydi va qo'ng'iroq abadiy ko'rinmas bo'lib qolardi — buni hech
    kim sezmasdi. Endi u tanlanadi, `RouteStage` esa turni raqam bo'yicha
    qaytadan aniqlaydi."""
    tanlangan = await _tanlangan()
    assert turli_turdagi_qongiroqlar["xato"] in tanlangan


def test_baholanmaydigan_turlar_enumdan_olinadi() -> None:
    """Ro'yxat QO'LDA sanalmasligi kerak.

    Yangi tur qo'shilib bu ro'yxatga tushmasa, u baholanadigan deb
    qabul qilinardi va savdo rubrikasi bilan nol olardi."""
    from src.modules.calls.domain.entities import CallType
    from src.modules.pipeline.application.orchestrator import NOT_SCORABLE_TYPES

    assert set(NOT_SCORABLE_TYPES) == {
        tur.value for tur in CallType
    } - {CallType.SALES.value}
