"""Ichki suhbat BAHOLANMAYDI, lekin TRANSKRIPT oladi — quvur kafolati.

NEGA BU TEST BOR. Ish telefonlari faqat mijoz bilan ishlatilmaydi:
xodim viloyat skladi bilan yuk haqida, buxgalteriya bilan kassa haqida
gaplashadi. Savdo rubrikasi bunday suhbatga «ehtiyojni aniqladimi»
degan savolni beradi va tabiiy ravishda nol qo'yadi.

⚠️ TUR RAQAM BO'YICHA ANIQLANADI, transkript mazmuni bo'yicha emas.
Ilgari buni AI qilardi va yanglishardi: eski mijoz ham «qoldiq qancha,
narx qanaqa» deb qisqa gaplashadi — matn jihatidan bu hamkasb
suhbatidan farq qilmaydi. O'lchandi: tasniflangan 98 qo'ng'iroqdan 82
tasi «ichki» deb belgilangan, savdo esa atigi 9 ta. Ya'ni haqiqiy savdo
suhbatlarining ko'pi baholanmay qolgan va buni hech kim sezmagan.

Bu fayl to'rt narsani qulflaydi:
  1. suhbatdosh raqami kompaniya liniyalari ro'yxatida bo'lsa —
     `internal`, baho qatori UMUMAN yaratilmaydi va LLM chaqirilmaydi;
  2. tashqi raqam — `sales`, baholanadi;
  3. ichki suhbat ham TRANSKRIPT oladi (menejer o'qiy olishi kerak);
  4. tur aniqlash LLM chaqiruvi TALAB QILMAYDI (bepul bosqich).
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.application import internal_directory
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel
from src.modules.pipeline.application.deps import PipelineDeps
from src.modules.pipeline.application.orchestrator import PipelineOrchestrator
from src.modules.pipeline.tests.stubs import build_payload
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC
from src.modules.scoring.infrastructure.models import CallScoreModel

TRANSCRIPT = "\n".join(
    [
        "[00:00] SPEAKER_0: Assalomu alaykum aka.",
        "[00:03] SPEAKER_1: Vaalaykum assalom.",
        "[00:06] SPEAKER_0: Sklad qoldig'i qancha bo'ldi?",
        "[00:10] SPEAKER_1: Yigirma dona qoldi aka.",
    ]
)

#: Xodimning O'Z liniyasi — MoyZvonki `src_number` shu ko'rinishda keladi
BIZNING_RAQAM = "+998997938700"
#: Ikkinchi xodimning liniyasi — ichki suhbatda suhbatdosh shu bo'ladi
HAMKASB_RAQAMI = "+998997928700"
#: Tashqi mijoz raqami — kompaniya liniyalari ro'yxatida yo'q
MIJOZ_RAQAMI = "+998901234567"


@dataclass
class StubLLM:
    """Faqat BAHO qaytaradi.

    Chaqiruvlar sanaladi: ichki suhbatda bitta ham chaqiruv bo'lmasligi
    kerak — tur aniqlash endi LLM ga umuman bormaydi.
    """

    model: str = "stub-llm"
    provider_key: str = "stub"
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        self.calls += 1
        self.prompts.append(system)
        return json.dumps(
            build_payload(DEFAULT_RUBRIC["blocks"], DEFAULT_RUBRIC["red_flags"]),
            ensure_ascii=False,
        )


def _orchestrator(llm: StubLLM) -> PipelineOrchestrator:
    async def llm_factory(_session):
        return llm

    async def asr_factory(_session):  # pragma: no cover
        # Transkript allaqachon bor, `force` ham berilmaydi — ASR bosqichi
        # `SKIPPED` bo'ladi. Bu yerga yetib kelish testning o'zi buzilgani.
        raise AssertionError("transkript bor — ASR chaqirilmasligi kerak")

    return PipelineOrchestrator(
        deps=PipelineDeps(asr_factory=asr_factory, llm_factory=llm_factory)
    )


@pytest_asyncio.fixture
async def qongiroq_yasovchi():
    """Berilgan suhbatdosh raqami bilan transkriptli qo'ng'iroq yaratadi.

    Ikkita qator yoziladi: biri xodimning O'Z liniyasini bazaga
    o'rgatish uchun (`agent_number`), ikkinchisi — sinaladigan
    qo'ng'iroq. Kompaniya liniyalari ro'yxati aynan shu ustundan
    yig'ilgani uchun boshqacha «o'rgatish» yo'li yo'q.
    """
    yaratilgan: list[uuid.UUID] = []

    async def make(client_phone: str | None) -> uuid.UUID:
        async with SessionFactory() as session:
            agent = AgentModel(
                full_name=f"tur-{uuid.uuid4().hex[:8]}",
                region="Toshkent",
                is_active=True,
            )
            session.add(agent)
            await session.flush()

            # Kompaniya liniyalarini bazaga «o'rgatuvchi» qator
            session.add(
                CallModel(
                    external_id=f"tur-src-{uuid.uuid4().hex}",
                    agent_id=agent.id,
                    direction=CallDirection.OUTBOUND,
                    status=CallStatus.SKIPPED,
                    started_at=datetime.now(UTC),
                    duration_sec=5,
                    agent_number=HAMKASB_RAQAMI,
                )
            )

            call = CallModel(
                external_id=f"tur-{uuid.uuid4().hex}",
                agent_id=agent.id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.PENDING,
                started_at=datetime.now(UTC),
                duration_sec=300,
                audio_key="records/tur.mp3",
                transcript=TRANSCRIPT,
                agent_number=BIZNING_RAQAM,
                client_phone=client_phone,
            )
            session.add(call)
            await session.commit()
            yaratilgan.append(agent.id)
            # Ro'yxat keshlanadi — yangi raqam darhol ko'rinishi kerak
            internal_directory.reset()
            return call.id

    yield make

    async with SessionFactory() as session:
        for agent_id in yaratilgan:
            await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()
    internal_directory.reset()


async def _row(call_id):
    async with SessionFactory() as session:
        call = await session.get(CallModel, call_id)
        score = (
            await session.execute(
                select(CallScoreModel).where(CallScoreModel.call_id == call_id)
            )
        ).scalar_one_or_none()
        return call, score


# ══════════════════════════════════════════════════════════════
#  Tashqi raqam — savdo, baholanadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tashqi_raqam_savdo_deb_baholanadi(qongiroq_yasovchi) -> None:
    """⚠️ Transkript «sklad qoldig'i» haqida, lekin raqam TASHQI.

    Aynan shu holat ilgari xato ketardi: AI matnni o'qib «ichki» derdi,
    holbuki bu eski mijozning odatiy qisqa so'rovi."""
    call_id = await qongiroq_yasovchi(MIJOZ_RAQAMI)
    llm = StubLLM()
    outcome = await _orchestrator(llm).process_call(call_id)

    assert outcome.call_type == "sales"
    assert outcome.overall_score is not None, "savdo qo'ng'irog'i baholanishi kerak"
    assert llm.calls == 1, "faqat baholash chaqiruvi"

    call, score = await _row(call_id)
    assert call.call_type == "sales"
    assert score is not None


@pytest.mark.asyncio
async def test_raqamsiz_qongiroq_savdo_deb_qabul_qilinadi(qongiroq_yasovchi) -> None:
    """Noma'lum holatda BAHOLANADI — xato ko'rinadigan tomonga qarab.

    Noto'g'ri «ichki» degan qaror savdo suhbatini jimgina baholashdan
    chetlatardi va buni hech kim sezmasdi; noto'g'ri «savdo» esa
    menejerga ko'rinadi va tuzatiladi."""
    call_id = await qongiroq_yasovchi(None)
    outcome = await _orchestrator(StubLLM()).process_call(call_id)

    assert outcome.call_type == "sales"


# ══════════════════════════════════════════════════════════════
#  Kompaniya raqami — ichki, baholanmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hamkasb_raqami_ichki_deb_belgilanadi(qongiroq_yasovchi) -> None:
    """⚠️ ASOSIY KAFOLAT: baho qatori UMUMAN yaratilmaydi."""
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    llm = StubLLM()
    outcome = await _orchestrator(llm).process_call(call_id)

    assert outcome.call_type == "internal"
    assert outcome.overall_score is None
    assert outcome.scored is False
    # Bu XATO emas — quvur muvaffaqiyatli tugadi
    assert outcome.stage.value == "completed"
    assert outcome.error_code is None

    # Qimmat baholash chaqiruvi QILINMAYDI
    assert llm.calls == 0, "ichki suhbatda LLM umuman chaqirilmaydi"

    call, score = await _row(call_id)
    assert score is None, "baho qatori yaratilmasligi kerak"
    assert call.status is CallStatus.COMPLETED
    assert call.call_type == "internal"


@pytest.mark.asyncio
async def test_ats_ichki_raqami_ham_ichki(qongiroq_yasovchi) -> None:
    """Qisqa raqamga tashqaridan qo'ng'iroq qilib bo'lmaydi."""
    call_id = await qongiroq_yasovchi("1042")
    outcome = await _orchestrator(StubLLM()).process_call(call_id)

    assert outcome.call_type == "internal"


@pytest.mark.asyncio
async def test_tur_va_sababi_saqlanadi(qongiroq_yasovchi) -> None:
    """Qo'lda tuzatish yo'q — qaror TUSHUNTIRILGAN bo'lishi shart.

    Sabab endi tekshirib bo'ladigan FAKT: qaysi raqam va u ro'yxatda
    bormi. Menejer buni o'qib, raqam noto'g'ri tushgan bo'lsa
    sozlamada tuzatadi."""
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    await _orchestrator(StubLLM()).process_call(call_id)

    call, _ = await _row(call_id)
    assert call.call_type_reason
    assert HAMKASB_RAQAMI in call.call_type_reason
    # Ustun `NUMERIC` — SQLAlchemy `Decimal` qaytaradi
    assert float(call.call_type_confidence) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_ichki_suhbat_transkripti_saqlanadi(qongiroq_yasovchi) -> None:
    """⚠️ Ichki suhbat ham MATNGA aylanadi.

    Ball qo'yilmaydi, lekin transkript kerak: menejer suhbatni o'qiy
    olishi, qidiruvda topishi va «kim nima degan edi» degan savolga
    javob berishi kerak. Bu — hujjat, baho emas."""
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    await _orchestrator(StubLLM()).process_call(call_id)

    call, _ = await _row(call_id)
    assert call.transcript == TRANSCRIPT


# ══════════════════════════════════════════════════════════════
#  Tur o'zgarganda eski baho qoladimi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ichki_deb_aniqlangach_eski_baho_ochiriladi(qongiroq_yasovchi) -> None:
    """⚠️ Ro'yxat to'lgach tur o'zgarishi MUMKIN va bu normal.

    Yangi xodimning raqami birinchi sinxronizatsiyadan keyin paydo
    bo'ladi — o'shangacha uning bilan bo'lgan suhbat «savdo» deb
    baholangan bo'lishi mumkin. Eski ballni qoldirish tizimni
    o'z-o'ziga zid holatga solardi: ekranda «ichki, baholanmaydi»,
    analitikada esa ball turaverardi."""
    call_id = await qongiroq_yasovchi(MIJOZ_RAQAMI)
    await _orchestrator(StubLLM()).process_call(call_id)
    _, score = await _row(call_id)
    assert score is not None, "avval savdo sifatida baholandi"

    # Endi o'sha raqam kompaniya liniyasi bo'lib chiqdi
    async with SessionFactory() as session:
        call = await session.get(CallModel, call_id)
        session.add(
            CallModel(
                external_id=f"tur-src2-{uuid.uuid4().hex}",
                agent_id=call.agent_id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.SKIPPED,
                started_at=datetime.now(UTC),
                duration_sec=5,
                agent_number=MIJOZ_RAQAMI,
            )
        )
        await session.commit()
    internal_directory.reset()

    outcome = await _orchestrator(StubLLM()).process_call(call_id)

    assert outcome.call_type == "internal"
    _, score = await _row(call_id)
    assert score is None, "eski baho o'chirilishi kerak"


# ══════════════════════════════════════════════════════════════
#  Chaqiruvlar hisobi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tur_aniqlash_llm_hisobiga_kirmaydi(qongiroq_yasovchi) -> None:
    """Tur aniqlash BEPUL — hisobda ko'rinmasligi kerak.

    Aynan shu son bilan «bitta audio uchun nechta so'rov ketdi» degan
    savolga javob beriladi; bepul bosqichni sanash uni yolg'on qilardi.
    """
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    outcome = await _orchestrator(StubLLM()).process_call(call_id)

    assert outcome.route is not None, "bosqich ishladi"
    assert outcome.route.provider_calls == 0
    assert outcome.llm_calls == 0
    assert outcome.score is None, "baho bosqichi ishlamadi"


@pytest.mark.asyncio
async def test_hisob_baza_bilan_mos(qongiroq_yasovchi) -> None:
    """`CallOutcome` va `call_pipeline_state` BIR XIL sonni bermasa,
    hisobot va baza bir-biriga zid bo'ladi."""
    from src.modules.pipeline.infrastructure.models import CallPipelineStateModel

    call_id = await qongiroq_yasovchi(MIJOZ_RAQAMI)
    outcome = await _orchestrator(StubLLM()).process_call(call_id)

    async with SessionFactory() as session:
        state = (
            await session.execute(
                select(CallPipelineStateModel).where(
                    CallPipelineStateModel.call_id == call_id
                )
            )
        ).scalar_one()
        assert state.llm_calls == outcome.llm_calls == 1


@pytest.mark.asyncio
async def test_guruh_hisoboti_baholanganni_ajratadi(qongiroq_yasovchi) -> None:
    """⚠️ `completed` — «xatosiz tugadi», «baholandi» EMAS."""
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    report = await _orchestrator(StubLLM()).run_batch([call_id])

    assert report.total == 1
    assert report.completed == 1, "xatosiz tugadi"
    assert report.scored == 0, "baho yozilmadi"
    assert report.not_sales == 1
    assert report.failed == 0
    assert report.llm_calls == 0, "bepul bosqich hisobda ko'rinmaydi"


@pytest.mark.asyncio
async def test_takroriy_yurish_skipped_deb_sanaladi(qongiroq_yasovchi) -> None:
    """Ikkinchi yurishda hech qanday provayder chaqirilmaydi."""
    call_id = await qongiroq_yasovchi(HAMKASB_RAQAMI)
    orch = _orchestrator(StubLLM())
    await orch.process_call(call_id)

    report = await orch.run_batch([call_id])
    assert report.skipped == 1, "takroriy yurish sifatida sanalishi kerak"
    assert report.llm_calls == 0, "chaqiruv bo'lmasligi kerak"
