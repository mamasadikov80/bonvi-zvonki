"""Savdo bo'lmagan qo'ng'iroq BAHOLANMAYDI — quvur darajasidagi kafolat.

NEGA BU TEST BOR. Ish telefonlari faqat savdo uchun ishlatilmaydi:
xodim viloyat skladi bilan yuk haqida, buxgalteriya bilan kassa
haqida gaplashadi, ba'zan uyiga qo'ng'iroq qiladi. Savdo rubrikasi
bunday suhbatga «ehtiyojni aniqladimi», «mahsulotni taqdim etdimi»
degan savolni beradi va tabiiy ravishda nol qo'yadi.

Haqiqiy ma'lumotda o'lchandi: baholangan 69 qo'ng'iroqdan 14 tasi
(20%) ichki suhbat edi. Muloqot bali 17/25 — suhbat yaxshi o'tgan.
Savdo bali 6/25, umumiy ball 43. Ya'ni yaxshi bajarilgan ish suhbati
xodimning o'rtachasini pasaytirgan.

Bu fayl uchta narsani qulflaydi:
  1. `sales` — baholanadi, ball yoziladi;
  2. boshqa tur — baho qatori UMUMAN yaratilmaydi va LLM ikkinchi
     marta chaqirilmaydi (qimmat chaqiruv tejaladi);
  3. tur va SABABI saqlanadi — qo'lda tuzatish yo'q, shuning uchun
     qaror hech bo'lmasa tushuntirilgan bo'lishi kerak.
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


@dataclass
class StubLLM:
    """Birinchi chaqiruv — TUR, ikkinchisi — BAHO.

    Chaqiruvlar sanaladi: savdo bo'lmagan qo'ng'iroqda ikkinchi
    chaqiruv BO'LMASLIGI kerak va test aynan shuni tekshiradi.
    """

    call_type: str
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

        # Tur so'ralayotganini tizim ko'rsatmasidan bilamiz
        if "TURLAR" in system:
            return json.dumps(
                {
                    "call_type": self.call_type,
                    "confidence": 0.93,
                    "reason": "Ikki tomon ham xodim, sklad qoldig'i muhokama qilindi",
                    "misconduct": False,
                },
                ensure_ascii=False,
            )
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
async def transkriptli_qongiroq():
    """Transkripti BOR qo'ng'iroq — ASR bosqichi o'tkazib yuboriladi."""
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"tur-{uuid.uuid4().hex[:8]}", region="Toshkent", is_active=True
        )
        session.add(agent)
        await session.flush()
        call = CallModel(
            external_id=f"tur-{uuid.uuid4().hex}",
            agent_id=agent.id,
            direction=CallDirection.OUTBOUND,
            status=CallStatus.PENDING,
            started_at=datetime.now(UTC),
            duration_sec=300,
            audio_key="records/tur.mp3",
            transcript=TRANSCRIPT,
        )
        session.add(call)
        await session.commit()
        ids = (agent.id, call.id)

    yield ids[1]

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == ids[0]))
        await session.commit()


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
#  Savdo — baholanadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_savdo_qongirogi_baholanadi(transkriptli_qongiroq) -> None:
    llm = StubLLM(call_type="sales")
    outcome = await _orchestrator(llm).process_call(transkriptli_qongiroq)

    assert outcome.call_type == "sales"
    assert outcome.overall_score is not None, "savdo qo'ng'irog'i baholanishi kerak"
    assert llm.calls == 2, "tur + baho = ikki chaqiruv"

    call, score = await _row(transkriptli_qongiroq)
    assert call.call_type == "sales"
    assert score is not None


# ══════════════════════════════════════════════════════════════
#  Savdo emas — baholanmaydi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("tur", ["internal", "service", "personal", "unclear"])
async def test_savdo_bolmagan_qongiroq_baholanmaydi(
    transkriptli_qongiroq, tur
) -> None:
    """⚠️ ASOSIY KAFOLAT: baho qatori UMUMAN yaratilmaydi."""
    llm = StubLLM(call_type=tur)
    outcome = await _orchestrator(llm).process_call(transkriptli_qongiroq)

    assert outcome.call_type == tur
    assert outcome.overall_score is None
    assert outcome.scored is False
    # Bu XATO emas — quvur muvaffaqiyatli tugadi
    assert outcome.stage.value == "completed"
    assert outcome.error_code is None

    # Qimmat baholash chaqiruvi QILINMAYDI
    assert llm.calls == 1, "faqat tur so'raladi, baho so'ralmaydi"

    call, score = await _row(transkriptli_qongiroq)
    assert score is None, "baho qatori yaratilmasligi kerak"
    assert call.status is CallStatus.COMPLETED
    assert call.call_type == tur


@pytest.mark.asyncio
async def test_tur_va_sababi_saqlanadi(transkriptli_qongiroq) -> None:
    """Qo'lda tuzatish yo'q — qaror TUSHUNTIRILGAN bo'lishi shart.

    Menejer sababni o'qib, xato bo'lsa «Qayta baholash» ni bosadi.
    Sabab bo'lmasa u nima uchun baholanmaganini bilmaydi."""
    llm = StubLLM(call_type="internal")
    await _orchestrator(llm).process_call(transkriptli_qongiroq)

    call, _ = await _row(transkriptli_qongiroq)
    assert call.call_type_reason
    assert "sklad" in call.call_type_reason.lower()
    # Ustun `NUMERIC` — SQLAlchemy `Decimal` qaytaradi, `float` bilan
    # to'g'ridan-to'g'ri solishtirib bo'lmaydi
    assert float(call.call_type_confidence) == pytest.approx(0.93, abs=0.01)


@pytest.mark.asyncio
async def test_transkript_saqlanib_qoladi(transkriptli_qongiroq) -> None:
    """Baholanmagan qo'ng'iroq YO'QOLMAYDI — menejer o'qishi mumkin."""
    llm = StubLLM(call_type="personal")
    await _orchestrator(llm).process_call(transkriptli_qongiroq)

    call, _ = await _row(transkriptli_qongiroq)
    assert call.transcript == TRANSCRIPT


# ══════════════════════════════════════════════════════════════
#  Idempotentlik
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_takroriy_yurish_turni_qayta_soramaydi(transkriptli_qongiroq) -> None:
    """Tur allaqachon aniqlangan bo'lsa LLM bejiz chaqirilmaydi."""
    llm = StubLLM(call_type="internal")
    orch = _orchestrator(llm)

    await orch.process_call(transkriptli_qongiroq)
    assert llm.calls == 1

    # Ikkinchi yurish — mavjud natijalar qayta so'ralmaydi
    await orch.process_call(transkriptli_qongiroq)
    assert llm.calls == 1, "ikkinchi yurishda chaqiruv bo'lmasligi kerak"


# ══════════════════════════════════════════════════════════════
#  Chaqiruvlar hisobi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tasnif_chaqiruvi_hisobga_kiradi(transkriptli_qongiroq) -> None:
    """⚠️ Savdo bo'lmagan qo'ng'iroqda ham LLM chaqiruvi SANALADI.

    Ilgari `CallOutcome.llm_calls` faqat baho bosqichini sanardi. Savdo
    bo'lmaganida baho bosqichi umuman ishlamaydi, tur aniqlash esa
    ishlaydi — hisob NOL deb ko'rsatardi. Ma'lumotning 96% i savdo emas,
    ya'ni guruh yakunidagi son deyarli butunlay xato bo'lardi. Aynan shu
    son bilan «vendor chegarasi nega to'ldi» degan savolga javob
    beriladi."""
    llm = StubLLM(call_type="internal")
    outcome = await _orchestrator(llm).process_call(transkriptli_qongiroq)

    assert llm.calls == 1, "faqat tur so'raldi"
    assert outcome.score is None, "baho bosqichi ishlamadi"
    assert outcome.llm_calls == 1, "tur chaqiruvi hisobdan tushib qolmasligi kerak"


@pytest.mark.asyncio
async def test_savdoda_ikkala_chaqiruv_sanaladi(transkriptli_qongiroq) -> None:
    llm = StubLLM(call_type="sales")
    outcome = await _orchestrator(llm).process_call(transkriptli_qongiroq)

    assert llm.calls == 2, "tur + baho"
    assert outcome.llm_calls == 2


@pytest.mark.asyncio
async def test_hisob_baza_bilan_mos(transkriptli_qongiroq) -> None:
    """`CallOutcome` va `call_pipeline_state` BIR XIL sonni bermasa,
    hisobot va baza bir-biriga zid bo'ladi."""
    from src.modules.pipeline.infrastructure.models import CallPipelineStateModel

    llm = StubLLM(call_type="internal")
    outcome = await _orchestrator(llm).process_call(transkriptli_qongiroq)

    async with SessionFactory() as session:
        state = (
            await session.execute(
                select(CallPipelineStateModel).where(
                    CallPipelineStateModel.call_id == transkriptli_qongiroq
                )
            )
        ).scalar_one()
        assert state.llm_calls == outcome.llm_calls


@pytest.mark.asyncio
async def test_guruh_hisoboti_baholanganni_ajratadi(transkriptli_qongiroq) -> None:
    """⚠️ `completed` — «xatosiz tugadi», «baholandi» EMAS.

    Ikkisini ajratmaslik hisobotni yolg'onchi qiladi: «completed: 63»
    degan qator 63 ta qo'ng'iroq baholanganini bildirardi, aslida
    hammasi baholanmagan."""
    llm = StubLLM(call_type="internal")
    report = await _orchestrator(llm).run_batch([transkriptli_qongiroq])

    assert report.total == 1
    assert report.completed == 1, "xatosiz tugadi"
    assert report.scored == 0, "baho yozilmadi"
    assert report.not_sales == 1
    assert report.failed == 0
    assert report.llm_calls == 1, "tur chaqiruvi hisobda"


@pytest.mark.asyncio
async def test_takroriy_yurish_skipped_deb_sanaladi(transkriptli_qongiroq) -> None:
    """Ikkinchi yurishda hech qanday provayder chaqirilmaydi.

    Ilgari bu shart `score is not None` ga tayanardi — savdo bo'lmagan
    qo'ng'iroqda baho bosqichi umuman ishlamagani uchun takroriy yurish
    ham «yangi ish» deb sanalardi."""
    llm = StubLLM(call_type="internal")
    orch = _orchestrator(llm)
    await orch.process_call(transkriptli_qongiroq)

    report = await orch.run_batch([transkriptli_qongiroq])
    assert report.skipped == 1, "takroriy yurish sifatida sanalishi kerak"
    assert report.llm_calls == 0, "chaqiruv bo'lmasligi kerak"
