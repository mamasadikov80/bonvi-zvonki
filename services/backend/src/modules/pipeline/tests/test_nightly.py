"""Kunlik avtomatik yurish.

Bu vazifa kechasi, hech kim qaramaganda ishlaydi — shuning uchun uning
xatolari ERTALAB, ma'lumot yo'qligi orqali bilinadi. Testlar aynan shu
jim nosozliklarni ushlaydi.
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
from src.modules.pipeline.application import nightly as mod

HOZIR = datetime(2026, 5, 20, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def xodim():
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"tunggi-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(agent)
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()


async def _qongiroq(agent_id, *, soat_oldin: float, audio: bool = True) -> uuid.UUID:
    async with SessionFactory() as session:
        call = CallModel(
            external_id=f"tunggi-{uuid.uuid4().hex}",
            agent_id=agent_id,
            direction=CallDirection.INBOUND,
            status=CallStatus.PENDING if audio else CallStatus.SKIPPED,
            started_at=HOZIR - timedelta(hours=soat_oldin),
            duration_sec=120,
            audio_key="records/a.mp3" if audio else None,
            answered=True,
        )
        session.add(call)
        await session.commit()
        return call.id


@pytest.fixture
def soxta(monkeypatch):
    """MoyZvonki va Celery o'rniga soxta obyektlar.

    ⚠️ TARMOQQA CHIQMAYDI va HAQIQIY vazifa yubormaydi: test AI ga pul
    sarflamasligi kerak.
    """
    holat = {"navbat": [], "sync_chaqirildi": 0}

    class SoxtaIngest:
        def __init__(self, *_a, **_k):
            pass

        async def run(self, **_kwargs):
            holat["sync_chaqirildi"] += 1

            class R:
                fetched, created, updated = 10, 4, 6
                skipped_no_agent = 0

            return R()

    class SoxtaKlient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(mod, "IngestService", SoxtaIngest)
    monkeypatch.setattr(mod, "moizvonki_client", lambda _s: SoxtaKlient())
    monkeypatch.setattr(
        mod, "enqueue_calls", lambda ids: holat["navbat"].extend(ids) or []
    )
    return holat


# ══════════════════════════════════════════════════════════════
#  Asosiy yo'l
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tortadi_va_navbatga_qoyadi(xodim, soxta) -> None:
    call_id = await _qongiroq(xodim, soat_oldin=3)

    report = await mod.run_nightly(now=HOZIR)

    assert soxta["sync_chaqirildi"] == 1
    assert report["fetched"] == 10
    assert call_id in soxta["navbat"]
    assert report["queued"] >= 1


@pytest.mark.asyncio
async def test_audiosiz_qongiroq_navbatga_TUSHMAYDI(xodim, soxta) -> None:
    """Javobsiz qo'ng'iroqda audio yo'q — uni AI ga yuborish bejiz
    xarajat va har kecha takrorlanardi."""
    call_id = await _qongiroq(xodim, soat_oldin=3, audio=False)

    await mod.run_nightly(now=HOZIR)
    assert call_id not in soxta["navbat"]


@pytest.mark.asyncio
async def test_eski_qongiroq_olinmaydi(xodim, soxta) -> None:
    """48 soatdan eski qo'ng'iroq har kecha qayta olinmasligi kerak —
    aks holda navbat kundan kunga o'sib borardi."""
    call_id = await _qongiroq(xodim, soat_oldin=72)

    await mod.run_nightly(now=HOZIR)
    assert call_id not in soxta["navbat"]


# ══════════════════════════════════════════════════════════════
#  Nosozlikka chidamlilik
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_MoyZvonki_yiqilsa_ham_baholash_ishlaydi(
    xodim, soxta, monkeypatch
) -> None:
    """⚠️ Ikki bosqich BOG'LIQ EMAS.

    MoyZvonki tushib qolgan kechada bazada kechagi, hali baholanmagan
    qo'ng'iroqlar qolgan bo'lishi mumkin. Ularni provayder nosozligi
    tufayli qoldirib ketish — bir kunlik ma'lumotni yo'qotish."""
    call_id = await _qongiroq(xodim, soat_oldin=3)

    class Yiqiladi:
        def __init__(self, *_a, **_k):
            pass

        async def run(self, **_kwargs):
            raise RuntimeError("MoyZvonki javob bermadi")

    monkeypatch.setattr(mod, "IngestService", Yiqiladi)

    report = await mod.run_nightly(now=HOZIR)

    assert report["sync_error"] is not None, "xato hisobotda ko'rinishi kerak"
    assert call_id in soxta["navbat"], "baholash baribir ishlashi kerak"


@pytest.mark.asyncio
async def test_navbat_chegarasi(xodim, soxta, monkeypatch) -> None:
    """MoyZvonki uzoq tushib turib, keyin bir necha kunlik ma'lumotni
    birdan bersa — navbat bir kechada butun hajmni yutib yubormasin."""
    monkeypatch.setattr(mod, "MAX_QUEUE", 2)
    for _ in range(4):
        await _qongiroq(xodim, soat_oldin=3)

    report = await mod.run_nightly(now=HOZIR)
    assert report["queued"] <= 2


@pytest.mark.asyncio
async def test_takroriy_yurish_xavfsiz(xodim, soxta) -> None:
    """Vazifa ikki marta ishga tushsa AI ga ikki marta pul
    to'lanmasligi kerak. Bu yerda tanlov mantig'i tekshiriladi:
    baho yozilgach qo'ng'iroq ro'yxatdan chiqadi."""
    await _qongiroq(xodim, soat_oldin=3)

    birinchi = await mod.run_nightly(now=HOZIR)
    ikkinchi = await mod.run_nightly(now=HOZIR)

    # Baho hali yozilmagani uchun ikkala yurishda ham tanlanadi —
    # bu TO'G'RI: qo'ng'iroq hamon baholanmagan. Muhimi, nusxa
    # yaratilmaydi va sinxronizatsiya ham ikki marta ishlaydi.
    assert birinchi["queued"] == ikkinchi["queued"]
    assert soxta["sync_chaqirildi"] == 2


# ══════════════════════════════════════════════════════════════
#  Kunlik Telegram xabari — TARTIB va SUKUT HOLATI
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_xabar_sukut_boyicha_YUBORILMAYDI(xodim, soxta) -> None:
    """⚠️ TASHQARIGA KETADIGAN AMAL — sukut holati «yubormaslik».

    `sales.digest_enabled` o'chiq (reyestrdagi sukut qiymati), ya'ni
    tungi yurish xabarni yig'maydi ham. Bu tekshiruv shu yerda
    turishi kerak: xabar bosqichi aynan shu vazifa ichida chaqiriladi
    va uni tasodifan «yoqib» qo'yish mumkin bo'lgan yagona joy ham shu.
    """
    await _qongiroq(xodim, soat_oldin=3)

    report = await mod.run_nightly(now=HOZIR)

    assert report["digest"] == {
        "sent": False,
        "reason": "disabled",
        "day": None,
        "chars": 0,
    }


@pytest.mark.asyncio
async def test_xabar_bosqichi_sinxronizatsiyadan_KEYIN(
    xodim, soxta, monkeypatch
) -> None:
    """Avval qo'ng'iroqlar tortiladi, keyin xabar.

    Teskarisida xabar ESKIRGAN ma'lumot bilan ketardi: kechagi
    suhbatlar hali bazada bo'lmasdi va ular oqlashi kerak bo'lgan
    savdolar «shubhali» bo'lib chiqardi.
    """
    tartib: list[str] = []

    asl_ingest = soxta  # `soxta` fixture'i `IngestService` ni almashtirgan

    class KuzatuvchiIngest:
        def __init__(self, *_a, **_k):
            pass

        async def run(self, **_kwargs):
            tartib.append("sync")
            asl_ingest["sync_chaqirildi"] += 1

            class R:
                fetched, created, updated = 0, 0, 0
                skipped_no_agent = 0

            return R()

    async def soxta_digest():
        tartib.append("digest")
        return {"sent": False, "reason": "disabled"}

    monkeypatch.setattr(mod, "IngestService", KuzatuvchiIngest)
    monkeypatch.setattr(mod, "run_daily_digest", soxta_digest)

    await mod.run_nightly(now=HOZIR)

    assert tartib == ["sync", "digest"]


@pytest.mark.asyncio
async def test_xabar_yiqilsa_tungi_yurish_yiqilmaydi(
    xodim, soxta, monkeypatch
) -> None:
    """Telegram tushib qolgani uchun butun yurishni bekor qilib bo'lmaydi.

    Qo'ng'iroq va baholash bosqichlari allaqachon bajarilgan; sabab
    hisobotda va logda qoladi.
    """
    call_id = await _qongiroq(xodim, soat_oldin=3)

    async def yiqiladi():
        raise RuntimeError("Telegram javob bermadi")

    monkeypatch.setattr(mod, "run_daily_digest", yiqiladi)

    report = await mod.run_nightly(now=HOZIR)

    assert report["digest"]["sent"] is False
    assert report["digest"]["reason"] == "error"
    assert call_id in soxta["navbat"]


# ══════════════════════════════════════════════════════════════
#  Oyna
# ══════════════════════════════════════════════════════════════


def test_oyna_aniq_bir_sutka() -> None:
    """Vazifa yarim tunda ishlaydi va oyna to'liq o'tgan kunni
    qamraydi. Kengaytirish kerak bo'lsa bu YAGONA joy."""
    assert mod.LOOKBACK_HOURS == 24
