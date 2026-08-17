"""Xodimni o'chirish — nima o'chadi va nima HIMOYALANADI.

NEGA BU TESTLAR BOR. MoyZvonki'dan barcha xodim tortiladi, keyin
ortiqchasi olib tashlanadi. `calls.agent_id` va `surveys.agent_id` da
`ON DELETE CASCADE` turibdi — ya'ni xodim qatori o'chsa, uning
transkriptlari, BAHOLARI va mijoz javoblari ham o'chib ketardi.

Shuning uchun tizimda MA'LUMOT YO'QOTADIGAN YO'L UMUMAN YO'Q.
Qaror avtomatik:

  · bo'sh xodim        → qatori butunlay o'chadi (yo'qotadigan narsa yo'q);
  · ma'lumoti bor xodim → ARXIVGA o'tadi. Ekranlardan yo'qoladi, qatori
    qoladi, qo'ng'iroqlari va baholari joyida turadi.

Bu testlar aynan shuni qulflaydi: hech qanday chaqiruv ma'lumotni
o'chira olmasligi kerak.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.database import SessionFactory
from src.main import app
from src.modules.agents.infrastructure.models import AgentModel
from src.modules.calls.domain.entities import CallDirection, CallStatus
from src.modules.calls.infrastructure.models import CallModel

API = "/api/v1/agents"


@pytest_asyncio.fixture
async def manager_client() -> AsyncIterator[httpx.AsyncClient]:
    """MANAGER roli — unda `agents:sync` bo'lishi mumkin, lekin
    o'chirish ADMINniki. Aynan shu chegara tekshiriladi."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "manager@zvonki.uz", "password": "manager12345"},
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


@pytest_asyncio.fixture
async def bosh_xodim():
    """Hech qanday bog'liq ma'lumoti yo'q xodim."""
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"ochirish-{uuid.uuid4().hex[:8]}",
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


@pytest_asyncio.fixture
async def qongirogli_xodim():
    """Bitta qo'ng'irog'i bor xodim — o'chirilsa qo'ng'iroq ham ketadi."""
    async with SessionFactory() as session:
        agent = AgentModel(
            full_name=f"ochirish-{uuid.uuid4().hex[:8]}",
            region="Toshkent",
            is_active=True,
        )
        session.add(agent)
        await session.flush()
        session.add(
            CallModel(
                external_id=f"del-{uuid.uuid4().hex}",
                agent_id=agent.id,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.PENDING,
                started_at=datetime.now(UTC),
                duration_sec=120,
            )
        )
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with SessionFactory() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))
        await session.commit()


async def _mavjudmi(agent_id) -> bool:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(AgentModel.id).where(AgentModel.id == agent_id)
            )
        ).scalar_one_or_none() is not None


# ══════════════════════════════════════════════════════════════
#  Ruxsat — FAQAT ADMIN
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_menejer_ochira_olmaydi(manager_client, bosh_xodim) -> None:
    """Menejerda `agents:sync` bo'lishi mumkin, lekin o'chirish — adminniki."""
    response = await manager_client.post(
        f"{API}/delete", json={"agent_ids": [str(bosh_xodim)]}
    )
    assert response.status_code == 403, response.text
    assert await _mavjudmi(bosh_xodim)


@pytest.mark.asyncio
async def test_menejer_tasirni_ham_kora_olmaydi(manager_client, bosh_xodim) -> None:
    response = await manager_client.post(
        f"{API}/deletion-impact", json={"agent_ids": [str(bosh_xodim)]}
    )
    assert response.status_code == 403, response.text


# ══════════════════════════════════════════════════════════════
#  Bo'sh xodim — bemalol o'chadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bosh_xodim_ochadi(admin_client, bosh_xodim) -> None:
    response = await admin_client.post(
        f"{API}/delete", json={"agent_ids": [str(bosh_xodim)]}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["deleted"] == [str(bosh_xodim)]
    assert body["archived"] == []
    assert not await _mavjudmi(bosh_xodim)


@pytest.mark.asyncio
async def test_bosh_xodim_tasiri_xavfsiz_deb_belgilanadi(
    admin_client, bosh_xodim
) -> None:
    response = await admin_client.post(
        f"{API}/deletion-impact", json={"agent_ids": [str(bosh_xodim)]}
    )
    assert response.status_code == 200, response.text
    (impact,) = response.json()

    assert impact["safe"] is True
    assert impact["blockers"] == []
    assert impact["calls"] == 0


# ══════════════════════════════════════════════════════════════
#  Ma'lumoti bor xodim — himoyalanadi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qongirogli_xodim_arxivga_otadi_ochmaydi(
    admin_client, qongirogli_xodim
) -> None:
    """ENG MUHIM TEST: qo'ng'iroq va baho HECH QACHON yo'qolmaydi."""
    response = await admin_client.post(
        f"{API}/delete", json={"agent_ids": [str(qongirogli_xodim)]}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["deleted"] == [], "ma'lumoti bor xodim o'chirilmasligi kerak"
    assert len(body["archived"]) == 1
    assert body["kept_calls"] == 1

    arxiv = body["archived"][0]
    assert arxiv["safe"] is False
    assert any("qo'ng'iroq" in reason for reason in arxiv["blockers"])

    # Qator ham, qo'ng'iroq ham JOYIDA
    assert await _mavjudmi(qongirogli_xodim)
    async with SessionFactory() as session:
        agent = (
            await session.execute(
                select(AgentModel).where(AgentModel.id == qongirogli_xodim)
            )
        ).scalar_one()
        assert agent.archived_at is not None, "arxiv belgisi qo'yilishi kerak"
        assert agent.is_active is False

        qongiroqlar = (
            await session.execute(
                select(CallModel.id).where(CallModel.agent_id == qongirogli_xodim)
            )
        ).all()
    assert len(qongiroqlar) == 1, "qo'ng'iroq saqlanishi SHART"


@pytest.mark.asyncio
async def test_arxivlangan_xodim_royxatda_korinmaydi(
    admin_client, qongirogli_xodim
) -> None:
    """Arxiv «o'chirilgandek» ko'rinishi kerak — hatto `include_inactive` da ham."""
    await admin_client.post(f"{API}/delete", json={"agent_ids": [str(qongirogli_xodim)]})

    for params in ("", "?include_inactive=true"):
        response = await admin_client.get(f"{API}{params}")
        ids = [row["id"] for row in response.json()]
        assert str(qongirogli_xodim) not in ids, f"«{params}» da ko'rinmasligi kerak"

    # Ataylab so'ralsa — ko'rinadi
    response = await admin_client.get(f"{API}?include_archived=true&include_inactive=true")
    ids = [row["id"] for row in response.json()]
    assert str(qongirogli_xodim) in ids


@pytest.mark.asyncio
async def test_arxivdan_qaytarish(admin_client, qongirogli_xodim) -> None:
    """Xato bosilgan bo'lsa — qaytarib olsa bo'ladi."""
    await admin_client.post(f"{API}/delete", json={"agent_ids": [str(qongirogli_xodim)]})

    response = await admin_client.post(
        f"{API}/restore", json={"agent_ids": [str(qongirogli_xodim)]}
    )
    assert response.status_code == 200, response.text

    response = await admin_client.get(f"{API}")
    ids = [row["id"] for row in response.json()]
    assert str(qongirogli_xodim) in ids


# ══════════════════════════════════════════════════════════════
#  Aralash partiya — QISMAN bajariladi
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aralash_royxatda_xavfsizlari_ochadi(
    admin_client, bosh_xodim, qongirogli_xodim
) -> None:
    """Bir partiyada ikkalasi ham bo'lishi mumkin: biri o'chadi, biri arxivga."""
    response = await admin_client.post(
        f"{API}/delete",
        json={"agent_ids": [str(bosh_xodim), str(qongirogli_xodim)]},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["deleted"] == [str(bosh_xodim)]
    assert [r["agent_id"] for r in body["archived"]] == [str(qongirogli_xodim)]

    assert not await _mavjudmi(bosh_xodim), "bo'sh xodim o'chishi kerak"
    assert await _mavjudmi(qongirogli_xodim), "ma'lumotlisi saqlanishi kerak"


# ══════════════════════════════════════════════════════════════
#  «Hammasini olish» — IDEMPOTENTLIK
#
#  MoyZvonki'dagi barcha xodim bitta tugma bilan tushadi. Eng muhim
#  va'da: MAVJUDLARGA TEGILMAYDI. Admin xodimning ismini tuzatgan,
#  hududini qo'ygan, rasm yuklagan bo'lishi mumkin — takroriy import
#  bularning hech birini qayta yozmasligi kerak.
# ══════════════════════════════════════════════════════════════


class SoxtaXodim:
    """`MoizvonkiEmployee` o'rniga yetarli minimal obyekt."""

    def __init__(self, ident: str, name: str) -> None:
        self.id = ident
        self.display_name = name
        self.email = f"{ident}@example.test"
        self.group_name = "Savdo"
        self.role = 4


@pytest_asyncio.fixture
def soxta_moizvonki(monkeypatch):
    """MoyZvonki o'rniga tayyor ro'yxat — tarmoqqa chiqilmaydi."""
    from contextlib import asynccontextmanager

    from src.modules.agents.presentation import router as agents_router

    holder: dict[str, list] = {"employees": []}

    class Klient:
        async def list_employees(self):
            return holder["employees"]

    @asynccontextmanager
    async def soxta_client(_session):
        yield Klient()

    monkeypatch.setattr(agents_router, "moizvonki_client", soxta_client)
    return holder


@pytest_asyncio.fixture
async def import_tozalash():
    """Test yaratgan xodimlarni oxirida o'chiradi."""
    markerlar: list[str] = []
    yield markerlar
    async with SessionFactory() as session:
        await session.execute(
            delete(AgentModel).where(AgentModel.external_id.in_(markerlar))
        )
        await session.commit()


@pytest.mark.asyncio
async def test_hammasini_olish_yetishmaganini_yaratadi(
    admin_client, soxta_moizvonki, import_tozalash
) -> None:
    token = uuid.uuid4().hex[:8]
    markerlar = [f"mz-{token}-1", f"mz-{token}-2"]
    import_tozalash.extend(markerlar)
    soxta_moizvonki["employees"] = [
        SoxtaXodim(markerlar[0], f"Xodim A {token}"),
        SoxtaXodim(markerlar[1], f"Xodim B {token}"),
    ]

    response = await admin_client.post(
        f"{API}/moizvonki/import-all", json={"detect_phones": False}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 2
    assert body["created"] == 2
    assert body["skipped"] == 0


@pytest.mark.asyncio
async def test_takroriy_import_hech_narsani_qayta_yozmaydi(
    admin_client, soxta_moizvonki, import_tozalash
) -> None:
    """Ikkinchi bosishda `created` NOL bo'lishi kerak."""
    token = uuid.uuid4().hex[:8]
    marker = f"mz-{token}-1"
    import_tozalash.append(marker)
    soxta_moizvonki["employees"] = [SoxtaXodim(marker, f"Xodim {token}")]

    await admin_client.post(f"{API}/moizvonki/import-all", json={"detect_phones": False})

    # Admin xodimni tahrirlaydi — hudud va ism o'zgaradi
    async with SessionFactory() as session:
        agent = (
            await session.execute(
                select(AgentModel).where(AgentModel.external_id == marker)
            )
        ).scalar_one()
        agent.full_name = "Admin tuzatgan ism"
        agent.region = "Samarqand"
        await session.commit()

    response = await admin_client.post(
        f"{API}/moizvonki/import-all", json={"detect_phones": False}
    )
    body = response.json()
    assert body["created"] == 0
    assert body["skipped"] == 1

    # ⚠️ ENG MUHIM TEKSHIRUV: adminning tahriri saqlanib qolgan
    async with SessionFactory() as session:
        agent = (
            await session.execute(
                select(AgentModel).where(AgentModel.external_id == marker)
            )
        ).scalar_one()
        assert agent.full_name == "Admin tuzatgan ism"
        assert agent.region == "Samarqand"


@pytest.mark.asyncio
async def test_ismi_mos_xodimga_boglanadi_dublikat_yaratmaydi(
    admin_client, soxta_moizvonki, import_tozalash
) -> None:
    """Qo'lda kiritilgan xodim ikkinchi nusxa bo'lib ketmasligi kerak."""
    token = uuid.uuid4().hex[:8]
    name = f"Qo'lda kiritilgan {token}"
    marker = f"mz-{token}-9"
    import_tozalash.append(marker)

    async with SessionFactory() as session:
        session.add(AgentModel(full_name=name, region="Toshkent", is_active=True))
        await session.commit()

    soxta_moizvonki["employees"] = [SoxtaXodim(marker, name)]
    response = await admin_client.post(
        f"{API}/moizvonki/import-all", json={"detect_phones": False}
    )
    body = response.json()

    assert body["created"] == 0
    assert body["linked"] == 1

    async with SessionFactory() as session:
        topilgan = (
            await session.execute(
                select(AgentModel).where(AgentModel.full_name == name)
            )
        ).scalars().all()
    assert len(topilgan) == 1, "dublikat yaratilmasligi kerak"
    assert topilgan[0].external_id == marker


@pytest.mark.asyncio
async def test_menejer_hammasini_ola_olmaydi(manager_client, soxta_moizvonki) -> None:
    """Bu amal o'nlab xodim yaratadi — faqat admin."""
    response = await manager_client.post(
        f"{API}/moizvonki/import-all", json={"detect_phones": False}
    )
    assert response.status_code == 403, response.text
