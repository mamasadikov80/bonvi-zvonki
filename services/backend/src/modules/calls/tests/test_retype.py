"""Ommaviy qayta tasniflash — sinxronizatsiyadan keyingi bosqich.

NEGA BU TEST BOR. Tur — qo'ng'iroqning xususiyati, baholash
jarayonining natijasi emas. Quvur esa hamma qatorga tegmaydi: audiosi
yo'q qo'ng'iroq (javobsizlar — hajmning ~35% i) navbatga umuman
tushmaydi, allaqachon baholangani esa qayta olinmaydi. Ya'ni faqat
quvurga tayanilsa, ro'yxatning katta qismi «aniqlanmagan» bo'lib
qolardi.

Ikkinchi vazifa: kompaniya liniyalari ro'yxati VAQT O'TIB to'ladi.
Yangi xodimning raqami birinchi sinxronizatsiyadan keyin paydo bo'ladi
va o'shanda uning hamkasblari bilan bo'lgan suhbatlari «savdo» dan
«ichki» ga o'tishi kerak — eski bahosi bilan birga.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.application import internal_directory
from src.modules.calls.application.retype import retype_calls
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.scoring.infrastructure.models import CallScoreModel

#: Kompaniya liniyasi — testda `agent_number` orqali «o'rgatiladi»
BIZNING_LINIYA = "+998977778700"
#: Tashqi mijoz — bu raqam hech qayerda kompaniya liniyasi sifatida yo'q
MIJOZ = "+998913334455"


@pytest_asyncio.fixture
async def qongiroqlar():
    """Uch qo'ng'iroq: tashqi, ichki (kompaniya liniyasi) va ATS raqami."""
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"retype-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(agent)
        await session.flush()

        ids: dict[str, uuid.UUID] = {}
        for nom, raqam in (
            ("tashqi", MIJOZ),
            ("ichki", BIZNING_LINIYA),
            ("ats", "1042"),
        ):
            call = CallModel(
                external_id=f"retype-{uuid.uuid4().hex}",
                agent_id=agent.id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.COMPLETED,
                started_at=datetime.now(UTC),
                duration_sec=120,
                client_phone=raqam,
                # ⚠️ Kompaniya liniyalari ro'yxati aynan shu ustundan
                # yig'iladi: shu tufayli `BIZNING_LINIYA` ro'yxatga
                # tushadi va ikkinchi qo'ng'iroq ichki bo'lib chiqadi.
                agent_number=BIZNING_LINIYA,
            )
            session.add(call)
            await session.flush()
            ids[nom] = call.id
        await session.commit()
        agent_id = agent.id

    internal_directory.reset()
    yield ids

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()
    internal_directory.reset()


async def _tur(call_id: uuid.UUID) -> str | None:
    async with SessionFactory() as session:
        call = await session.get(CallModel, call_id)
        return call.call_type


@pytest.mark.asyncio
async def test_raqam_boyicha_turlar_qoyiladi(qongiroqlar) -> None:
    async with SessionFactory() as session:
        await retype_calls(session)

    assert await _tur(qongiroqlar["tashqi"]) == "sales"
    assert await _tur(qongiroqlar["ichki"]) == "internal"
    assert await _tur(qongiroqlar["ats"]) == "internal", "ATS qisqa raqami"


@pytest.mark.asyncio
async def test_sabab_yoziladi(qongiroqlar) -> None:
    """Qo'lda tuzatish yo'q — qaror TEKSHIRIB bo'ladigan bo'lishi kerak."""
    async with SessionFactory() as session:
        await retype_calls(session)
        call = await session.get(CallModel, qongiroqlar["ichki"])

    assert call.call_type_reason
    assert BIZNING_LINIYA in call.call_type_reason
    assert float(call.call_type_confidence) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_takroriy_yurish_bazaga_tegmaydi(qongiroqlar) -> None:
    """Faqat O'ZGARADIGAN qatorlar yoziladi — sinxronizatsiya har kuni
    yuradi va u har safar butun jadvalni qayta yozmasligi kerak."""
    async with SessionFactory() as session:
        await retype_calls(session)
    async with SessionFactory() as session:
        ikkinchi = await retype_calls(session)

    assert ikkinchi.changed == 0


@pytest.mark.asyncio
async def test_ichkiga_otganda_eski_baho_ochiriladi(qongiroqlar) -> None:
    """⚠️ ASOSIY KAFOLAT.

    Yangi xodimning raqami ro'yxatga kechroq tushadi — o'shangacha
    uning bilan bo'lgan suhbat «savdo» sifatida baholangan bo'lishi
    mumkin. Eski ballni qoldirish tizimni o'z-o'ziga zid holatga
    solardi: ekranda «ichki suhbat, baholanmaydi», analitikada esa
    ball turaverardi va xodimning o'rtachasini pasaytiraverardi."""
    async with SessionFactory() as session:
        session.add(
            CallScoreModel(
                call_id=qongiroqlar["ichki"],
                model="test",
                rubric_version="v1",
                overall_score=43,
                blocks={},
                red_flags=[],
                confidence=0.9,
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        report = await retype_calls(session)

    assert report.scores_removed >= 1

    async with SessionFactory() as session:
        qolgan = (
            await session.execute(
                select(CallScoreModel).where(
                    CallScoreModel.call_id == qongiroqlar["ichki"]
                )
            )
        ).scalar_one_or_none()
    assert qolgan is None
